"""Cost & ROI analytics (section E).

Upserts cost parameters, refreshes the per-domain cost analysis MV, and
computes a multi-year ROI projection (two scenarios: with vs without
archiving). Devise : USD.

The archiving cost model reuses the section D recommendations:
  - ARCHIVAGE_FROID / ARCHIVAGE_CHIFFRE → cold storage rate
  - COMPRESSION                          → active rate × compression_ratio
  - autres                               → active rate (inchangé)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

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
        "description": "Taux de croissance annuel du volume de données",
    },
    {
        "name": "implementation_cost_one_shot",
        "value": 0.0,
        "unit": "USD",
        "description": "Coût one-shot de mise en place (tiering cloud = 0 par défaut)",
    },
]

PROJECTION_YEARS = 5

RUN_ID_SQL = "SELECT MAX(run_id) AS run_id FROM processed.dim_asset"

SUMMARY_SQL = """
SELECT
    COALESCE(SUM(total_size_gb), 0)      AS total_gb,
    COALESCE(SUM(archivable_size_gb), 0) AS archivable_gb
FROM serving.mv_cost_analysis
"""

DELETE_PROJECTION_SQL = "DELETE FROM serving.roi_projection WHERE run_id = :run_id"

INSERT_PROJECTION_SQL = """
INSERT INTO serving.roi_projection (
    computed_at, run_id, year_offset,
    volume_no_action_gb, cost_no_action_usd, cumul_cost_no_action_usd,
    volume_active_gb, volume_cold_gb,
    cost_with_archiving_usd, cumul_cost_with_archiving_usd,
    net_savings_usd, roi_pct, breakeven
) VALUES (
    :computed_at, :run_id, :year_offset,
    :vol_no, :cost_no, :cumul_no,
    :vol_active, :vol_cold,
    :cost_with, :cumul_with,
    :net, :roi_pct, :breakeven
)
"""


def _fetch_params(pg: PostgresClient) -> dict[str, float]:
    rows = pg.fetch_all("SELECT param_name, param_value FROM serving.dim_cost_params")
    return {r["param_name"]: float(r["param_value"]) for r in rows}


def _compute_projection(
    run_id: int,
    total_gb: float,
    archivable_gb: float,
    params: dict[str, float],
    years: int,
) -> list[dict[str, object]]:
    cost_active = params["storage_cost_per_gb_per_year"]
    cost_cold = params["cold_storage_cost_per_gb_year"]
    growth = params["data_growth_rate_pct_per_year"] / 100.0
    impl = params["implementation_cost_one_shot"]

    non_archivable_gb = max(total_gb - archivable_gb, 0.0)
    computed_at = datetime.now(timezone.utc)

    rows: list[dict[str, object]] = []
    cumul_no = 0.0
    cumul_with = impl
    for k in range(years + 1):
        gf_active = (1 + growth) ** k
        gf_cold = (1 + growth / 2) ** k  # les archives croissent 2x moins vite

        vol_no = total_gb * gf_active
        cost_no = vol_no * cost_active
        cumul_no += cost_no

        vol_active = non_archivable_gb * gf_active
        vol_cold = archivable_gb * gf_cold
        cost_with = vol_active * cost_active + vol_cold * cost_cold
        cumul_with += cost_with

        net = cumul_no - cumul_with
        roi_pct = round(net / impl * 100, 1) if impl > 0 else None

        rows.append(
            {
                "computed_at": computed_at,
                "run_id": run_id,
                "year_offset": k,
                "vol_no": round(vol_no, 4),
                "cost_no": round(cost_no, 2),
                "cumul_no": round(cumul_no, 2),
                "vol_active": round(vol_active, 4),
                "vol_cold": round(vol_cold, 4),
                "cost_with": round(cost_with, 2),
                "cumul_with": round(cumul_with, 2),
                "net": round(net, 2),
                "roi_pct": roi_pct,
                "breakeven": net > 0,
            }
        )
    return rows


def build_cost_analysis(
    years: int = PROJECTION_YEARS,
    upsert_defaults: bool = True,
) -> dict[str, object]:
    """Upsert cost params, refresh cost MV, compute ROI projection.

    Args:
        years: ROI projection horizon.
        upsert_defaults: when True (canonical rebuild), (re)writes the default
            cost parameters into ``serving.dim_cost_params``. Set to False to
            preserve user-customized parameters (what-if scenarios) and only
            refresh the MV + recompute the projection.
    """
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    try:
        logger.info("Building cost analysis (upsert_defaults={})", upsert_defaults)

        if upsert_defaults:
            logger.info("Step 1/3 — upserting serving.dim_cost_params")
            for param in COST_PARAMS:
                pg.execute(UPSERT_PARAM_SQL, param)
        else:
            logger.info("Step 1/3 — skipped (paramètres personnalisés préservés)")

        logger.info("Step 2/3 — refreshing serving.mv_cost_analysis")
        pg.execute("REFRESH MATERIALIZED VIEW serving.mv_cost_analysis")

        logger.info("Step 3/3 — computing ROI projection ({} years)", years)
        run_row = pg.fetch_one(RUN_ID_SQL)
        run_id = int(run_row["run_id"]) if run_row and run_row.get("run_id") else 0

        summary = pg.fetch_one(SUMMARY_SQL) or {}
        total_gb = float(summary.get("total_gb") or 0.0)
        archivable_gb = float(summary.get("archivable_gb") or 0.0)

        params = _fetch_params(pg)
        projection = _compute_projection(run_id, total_gb, archivable_gb, params, years)

        pg.execute(DELETE_PROJECTION_SQL, {"run_id": run_id})
        for row in projection:
            pg.execute(INSERT_PROJECTION_SQL, row)

        final = projection[-1] if projection else {}
        logger.info(
            "cost analysis built: patrimoine={:.3f} Go, archivable={:.3f} Go, "
            "economies cumulees {} ans = {} USD",
            total_gb,
            archivable_gb,
            years,
            final.get("net"),
        )
        return {
            "total_gb": round(total_gb, 4),
            "archivable_gb": round(archivable_gb, 4),
            "projection_years": years,
            "cumulative_net_savings_usd": final.get("net"),
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
