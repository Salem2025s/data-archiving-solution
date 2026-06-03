"""Cost & ROI analytics (section E).

Upserts cost parameters, refreshes the per-domain cost analysis MV, persists a
per-run cost/volume **snapshot** (basis for a REAL N-1 comparison, section E2),
and computes a multi-year ROI projection by **Monte Carlo** with uncertainty
intervals (section E3). Devise : USD.

E2 — comparaison N-1 réelle : chaque run écrit un snapshot dans
``serving.fact_cost_snapshot`` ; les runs historiques sont *backfillés* depuis
``processed.features_asset``. ``v_n1_comparison`` compare alors le dernier run au
précédent (delta réel), sans simulation.

E3 — projection ROI : le taux de croissance annuel est traité comme une
distribution (moyenne ± écart-type). La moyenne est estimée sur l'historique des
snapshots quand il est exploitable (CAGR observé > 0), sinon c'est l'hypothèse
configurée. Une simulation Monte Carlo (N tirages) propage l'incertitude → on
publie P10/P50/P90 des économies cumulées et la **probabilité de rentabilité**.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import numpy as np
from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

UPSERT_PARAM_SQL = """
INSERT INTO serving.dim_cost_params (param_name, param_value, unit, description)
VALUES (:name, :value, :unit, :description)
ON CONFLICT (param_name) DO UPDATE SET
    param_value = EXCLUDED.param_value,
    unit        = EXCLUDED.unit,
    description = EXCLUDED.description,
    updated_at  = now()
"""

# Paramètres par défaut — AWS S3 Standard / Glacier Deep Archive (USD).
COST_PARAMS: list[dict[str, object]] = [
    {
        "name": "storage_cost_per_gb_per_year",
        "value": 0.276,
        "unit": "USD/Go/an",
        "description": "Stockage actif — AWS S3 Standard (0,023 $/Go/mois)",
    },
    {
        "name": "cold_storage_cost_per_gb_year",
        "value": 0.048,
        "unit": "USD/Go/an",
        "description": "Stockage froid — AWS Glacier Deep Archive (~0,004 $/Go/mois)",
    },
    {
        "name": "compression_ratio",
        "value": 0.5,
        "unit": "ratio",
        "description": "Taux de taille résiduelle après compression (0.5 = -50%)",
    },
    {
        "name": "data_growth_rate_pct_per_year",
        "value": 15.0,
        "unit": "%/an",
        "description": "Croissance annuelle moyenne du volume (hypothèse — moyenne du Monte Carlo)",
    },
    {
        "name": "data_growth_std_pct_per_year",
        "value": 5.0,
        "unit": "%/an",
        "description": "Écart-type de la croissance annuelle (incertitude du Monte Carlo)",
    },
    {
        "name": "implementation_cost_one_shot",
        "value": 0.0,
        "unit": "USD",
        "description": "Coût one-shot de mise en place (tiering cloud = 0 par défaut)",
    },
]

PROJECTION_YEARS = 5
N_SIMULATIONS = 2000
SEED = 42

RUN_ID_SQL = "SELECT MAX(run_id) AS run_id FROM processed.dim_asset"

SUMMARY_SQL = """
SELECT
    COALESCE(SUM(total_size_gb), 0)      AS total_gb,
    COALESCE(SUM(archivable_size_gb), 0) AS archivable_gb
FROM serving.mv_cost_analysis
"""

# --- E2 : snapshots -------------------------------------------------------
DELETE_SNAPSHOT_SQL = "DELETE FROM serving.fact_cost_snapshot WHERE run_id = :run_id"
INSERT_SNAPSHOT_SQL = """
INSERT INTO serving.fact_cost_snapshot (run_id, domain_label, total_size_gb, current_cost_usd_year)
VALUES (:run_id, :domain_label, :total_size_gb, :current_cost_usd_year)
"""
SNAPSHOT_DOMAIN_SQL = """
SELECT p.business_domain_predicted AS domain_label,
       SUM(f.size_mb) / 1024.0 AS total_size_gb
FROM processed.features_asset f
JOIN serving.asset_business_domain_prediction p
  ON p.run_id = f.run_id AND p.asset_id = f.asset_id
WHERE f.run_id = :run_id AND COALESCE(f.size_mb, 0) > 0
GROUP BY p.business_domain_predicted
"""
SNAPSHOT_TOTAL_SQL = """
SELECT COALESCE(SUM(size_mb) / 1024.0, 0) AS total_size_gb
FROM processed.features_asset
WHERE run_id = :run_id AND COALESCE(size_mb, 0) > 0
"""
RUNS_WITH_FEATURES_SQL = "SELECT DISTINCT run_id FROM processed.features_asset ORDER BY run_id"
RUNS_WITH_SNAPSHOT_SQL = "SELECT DISTINCT run_id FROM serving.fact_cost_snapshot"
SNAPSHOT_TOTAL_SERIES_SQL = """
SELECT run_id, total_size_gb FROM serving.fact_cost_snapshot
WHERE domain_label = 'TOTAL' ORDER BY run_id
"""

# --- E3 : projection ------------------------------------------------------
DELETE_PROJECTION_SQL = "DELETE FROM serving.roi_projection WHERE run_id = :run_id"
INSERT_PROJECTION_SQL = """
INSERT INTO serving.roi_projection (
    computed_at, run_id, year_offset,
    volume_no_action_gb, cost_no_action_usd, cumul_cost_no_action_usd,
    volume_active_gb, volume_cold_gb,
    cost_with_archiving_usd, cumul_cost_with_archiving_usd,
    net_savings_usd, roi_pct, breakeven,
    net_savings_p10_usd, net_savings_p90_usd, breakeven_probability,
    growth_mean_pct, growth_std_pct, growth_source, n_simulations
) VALUES (
    :computed_at, :run_id, :year_offset,
    :vol_no, :cost_no, :cumul_no,
    :vol_active, :vol_cold,
    :cost_with, :cumul_with,
    :net, :roi_pct, :breakeven,
    :net_p10, :net_p90, :breakeven_probability,
    :growth_mean_pct, :growth_std_pct, :growth_source, :n_simulations
)
"""


def _fetch_params(pg: PostgresClient) -> dict[str, float]:
    rows = pg.fetch_all("SELECT param_name, param_value FROM serving.dim_cost_params")
    return {r["param_name"]: float(r["param_value"]) for r in rows}


# --- E2 : snapshots --------------------------------------------------------

def _persist_snapshot(pg: PostgresClient, run_id: int, rate: float) -> int:
    """Write the per-domain + TOTAL cost/volume snapshot for one run (idempotent)."""
    pg.execute(DELETE_SNAPSHOT_SQL, {"run_id": run_id})
    written = 0
    for row in pg.fetch_all(SNAPSHOT_DOMAIN_SQL, {"run_id": run_id}):
        gb = float(row["total_size_gb"] or 0.0)
        pg.execute(INSERT_SNAPSHOT_SQL, {
            "run_id": run_id, "domain_label": row["domain_label"],
            "total_size_gb": round(gb, 6), "current_cost_usd_year": round(gb * rate, 4),
        })
        written += 1
    total = pg.fetch_one(SNAPSHOT_TOTAL_SQL, {"run_id": run_id}) or {}
    gb = float(total.get("total_size_gb") or 0.0)
    pg.execute(INSERT_SNAPSHOT_SQL, {
        "run_id": run_id, "domain_label": "TOTAL",
        "total_size_gb": round(gb, 6), "current_cost_usd_year": round(gb * rate, 4),
    })
    return written + 1


def backfill_cost_snapshots(pg: PostgresClient, rate: float) -> int:
    """Create snapshots for historical runs that don't have one yet (real N-1 history)."""
    have = {int(r["run_id"]) for r in pg.fetch_all(RUNS_WITH_SNAPSHOT_SQL)}
    runs = [int(r["run_id"]) for r in pg.fetch_all(RUNS_WITH_FEATURES_SQL)]
    backfilled = 0
    for run_id in runs:
        if run_id in have:
            continue
        _persist_snapshot(pg, run_id, rate)
        backfilled += 1
    if backfilled:
        logger.info("Backfilled cost snapshots for {} historical run(s)", backfilled)
    return backfilled


def _estimate_growth(pg: PostgresClient, params: dict[str, float]) -> tuple[float, float, str]:
    """Growth distribution (mean, std, source) for the Monte Carlo.

    Uses the OBSERVED CAGR from the TOTAL snapshot series when it spans >=2 runs
    and is positive; otherwise the configured assumption (a short, non-monotonic
    history is not a reliable forward signal).
    """
    assumed_mean = params.get("data_growth_rate_pct_per_year", 15.0) / 100.0
    assumed_std = params.get("data_growth_std_pct_per_year", 5.0) / 100.0

    rows = pg.fetch_all(SNAPSHOT_TOTAL_SERIES_SQL)
    sizes = [float(r["total_size_gb"]) for r in rows if r.get("total_size_gb")]
    if len(sizes) >= 2 and sizes[0] > 0:
        periods = len(sizes) - 1
        cagr = (sizes[-1] / sizes[0]) ** (1.0 / periods) - 1.0
        if cagr > 0:
            if len(sizes) >= 3:
                ratios = np.array(sizes[1:]) / np.array(sizes[:-1]) - 1.0
                std = max(float(np.std(ratios)), 0.01)
            else:
                std = assumed_std
            return cagr, std, "observed"
    return assumed_mean, assumed_std, "assumption"


def _compute_projection(
    run_id: int,
    total_gb: float,
    archivable_gb: float,
    params: dict[str, float],
    years: int,
    growth_mean: float,
    growth_std: float,
    source: str,
) -> list[dict[str, object]]:
    """Monte Carlo ROI projection: each simulation draws one annual growth scenario."""
    cost_active = params["storage_cost_per_gb_per_year"]
    cost_cold = params["cold_storage_cost_per_gb_year"]
    impl = params.get("implementation_cost_one_shot", 0.0)
    non_archivable_gb = max(total_gb - archivable_gb, 0.0)
    computed_at = datetime.now(timezone.utc)

    rng = np.random.default_rng(SEED)
    # One growth scenario per simulation (a shrink beyond -90%/yr is implausible).
    g = np.clip(rng.normal(growth_mean, growth_std, N_SIMULATIONS), -0.9, None)

    rows: list[dict[str, object]] = []
    cumul_no = np.zeros(N_SIMULATIONS)
    cumul_with = np.full(N_SIMULATIONS, impl, dtype=float)
    for k in range(years + 1):
        gf_active = (1 + g) ** k
        gf_cold = (1 + g / 2) ** k  # les archives croissent 2x moins vite

        vol_no = total_gb * gf_active
        cost_no = vol_no * cost_active
        cumul_no = cumul_no + cost_no

        vol_active = non_archivable_gb * gf_active
        vol_cold = archivable_gb * gf_cold
        cost_with = vol_active * cost_active + vol_cold * cost_cold
        cumul_with = cumul_with + cost_with

        net = cumul_no - cumul_with
        p10, p50, p90 = (float(x) for x in np.percentile(net, [10, 50, 90]))
        breakeven_prob = float(np.mean(net > 0))

        rows.append({
            "computed_at": computed_at, "run_id": run_id, "year_offset": k,
            "vol_no": round(float(np.median(vol_no)), 4),
            "cost_no": round(float(np.median(cost_no)), 2),
            "cumul_no": round(float(np.median(cumul_no)), 2),
            "vol_active": round(float(np.median(vol_active)), 4),
            "vol_cold": round(float(np.median(vol_cold)), 4),
            "cost_with": round(float(np.median(cost_with)), 2),
            "cumul_with": round(float(np.median(cumul_with)), 2),
            "net": round(p50, 2),
            "net_p10": round(p10, 2),
            "net_p90": round(p90, 2),
            "breakeven_probability": round(breakeven_prob, 3),
            "roi_pct": round(p50 / impl * 100, 1) if impl > 0 else None,
            "breakeven": bool(p50 > 0),
            "growth_mean_pct": round(growth_mean * 100, 2),
            "growth_std_pct": round(growth_std * 100, 2),
            "growth_source": source,
            "n_simulations": N_SIMULATIONS,
        })
    return rows


def build_cost_analysis(
    years: int = PROJECTION_YEARS,
    upsert_defaults: bool = True,
) -> dict[str, object]:
    """Upsert params, refresh cost MV, persist snapshot (E2) + Monte Carlo ROI (E3).

    Args:
        years: ROI projection horizon.
        upsert_defaults: when True, (re)writes the default cost parameters. Set to
            False to preserve user-customized (what-if) parameters.
    """
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    try:
        logger.info("Building cost analysis (upsert_defaults={})", upsert_defaults)

        if upsert_defaults:
            logger.info("Step 1/4 — upserting serving.dim_cost_params")
            for param in COST_PARAMS:
                pg.execute(UPSERT_PARAM_SQL, param)
        else:
            logger.info("Step 1/4 — skipped (paramètres personnalisés préservés)")

        logger.info("Step 2/4 — refreshing serving.mv_cost_analysis")
        pg.execute("REFRESH MATERIALIZED VIEW serving.mv_cost_analysis")

        run_row = pg.fetch_one(RUN_ID_SQL)
        run_id = int(run_row["run_id"]) if run_row and run_row.get("run_id") else 0
        params = _fetch_params(pg)
        rate = params["storage_cost_per_gb_per_year"]

        logger.info("Step 3/4 — persisting cost snapshot (E2) + backfilling history")
        _persist_snapshot(pg, run_id, rate)
        backfill_cost_snapshots(pg, rate)

        summary = pg.fetch_one(SUMMARY_SQL) or {}
        total_gb = float(summary.get("total_gb") or 0.0)
        archivable_gb = float(summary.get("archivable_gb") or 0.0)

        logger.info("Step 4/4 — Monte Carlo ROI projection ({} years, {} sims)", years, N_SIMULATIONS)
        growth_mean, growth_std, source = _estimate_growth(pg, params)
        logger.info("Growth distribution: mean={:.1%} std={:.1%} (source={})",
                    growth_mean, growth_std, source)
        projection = _compute_projection(
            run_id, total_gb, archivable_gb, params, years, growth_mean, growth_std, source
        )

        pg.execute(DELETE_PROJECTION_SQL, {"run_id": run_id})
        for row in projection:
            pg.execute(INSERT_PROJECTION_SQL, row)

        final = projection[-1] if projection else {}
        logger.info(
            "cost analysis built: patrimoine={:.3f} Go, archivable={:.3f} Go, "
            "économies cumulées {} ans = P50 {} USD [P10 {} ; P90 {}], P(rentable)={}",
            total_gb, archivable_gb, years,
            final.get("net"), final.get("net_p10"), final.get("net_p90"),
            final.get("breakeven_probability"),
        )
        return {
            "total_gb": round(total_gb, 4),
            "archivable_gb": round(archivable_gb, 4),
            "projection_years": years,
            "growth_mean_pct": round(growth_mean * 100, 2),
            "growth_source": source,
            "net_savings_p50_usd": final.get("net"),
            "net_savings_p10_usd": final.get("net_p10"),
            "net_savings_p90_usd": final.get("net_p90"),
            "breakeven_probability": final.get("breakeven_probability"),
        }

    except Exception:
        logger.exception("Failed building cost analysis")
        raise


def main() -> None:
    """CLI entrypoint for cost analysis."""
    parser = argparse.ArgumentParser(description="Build cost & ROI analytics (section E)")
    parser.add_argument("--years", type=int, default=PROJECTION_YEARS, help="Projection horizon")
    args = parser.parse_args()

    configure_logging()
    result = build_cost_analysis(years=args.years)
    logger.info("Manual run successful. result={}", result)


if __name__ == "__main__":
    main()
