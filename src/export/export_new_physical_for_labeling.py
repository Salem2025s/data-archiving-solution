"""Export NEW physical tables (absent from the gold AND the human-eval set) to an annotable CSV.

Targets the gap surfaced by the physical-subset analysis: only ~28 % of the
~16.8 k physical tables (the decision-relevant perimeter for archiving) carry a
gold label today, and the classifier is directionally weaker there. This script
selects the physical tables that are NOT yet annotated — neither in the LLM gold
(``..._enriched_business_domain_v4.csv``) nor in the human-eval samples — so they
can be LLM-annotated and folded back into training.

Selection:
- run = latest by default (``--run-id`` to override),
- physical = ``size_mb > 0 OR row_count > 0`` (same perimeter as the archiving MV),
- annotable = ``field_count > 0``,
- excluded = any ``technical_name`` already present in the gold or human-eval CSVs.

Output schema == the gold v4 *pre-annotation* schema (``EXPORT_COLUMNS``), so once
``LLM/annotate_assets_llm.py`` fills ``business_domain`` + consensus columns, the
file concatenates directly with the 20 k gold for retraining via
``src/ml/train_production_classifier.py``.

Observed Oracle enrichment (real column samples) is OFF by default — it needs the
VPN/Oracle and only enriches the first ~120 assets. Metadata-derived semantics
(column names/types) are always populated, which is the same baseline the gold
relied on before the observed bonus.

Usage:
    python -m src.export.export_new_physical_for_labeling
    python -m src.export.export_new_physical_for_labeling --run-id 6 --limit 4000
    python -m src.export.export_new_physical_for_labeling --with-observed   # needs VPN
"""

from __future__ import annotations

import argparse
import csv
import glob
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.export.export_dataset_asset_ml_for_labeling import (
    EXPORT_COLUMNS,
    SOURCE_COLUMNS,
    _build_enriched_row,
    _build_observed_enrichment,
)
from src.utils.logging_utils import configure_logging

DEFAULT_GOLD = (
    "exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_business_domain_v4.csv"
)
DEFAULT_HUMAN_GLOBS: tuple[str, ...] = ("artifacts/human_eval_sample*.csv",)

PHYSICAL_SQL = f"""
SELECT {", ".join(SOURCE_COLUMNS)}
FROM processed.dataset_asset_ml
WHERE run_id = :run_id
  AND (COALESCE(size_mb, 0) > 0 OR COALESCE(row_count, 0) > 0)
  AND field_count > 0
ORDER BY source_system, asset_type, technical_name
"""


def _latest_run(pg: PostgresClient) -> int:
    row = pg.fetch_one("SELECT MAX(run_id) AS r FROM processed.dataset_asset_ml")
    if not row or row.get("r") is None:
        raise RuntimeError("processed.dataset_asset_ml is empty — run the pipeline first.")
    return int(row["r"])


def _names_from_csv(path: str, encoding: str = "utf-8") -> set[str]:
    """Return the set of technical_name values from a CSV (empty set if missing)."""
    p = Path(path)
    if not p.exists():
        logger.warning("Exclusion source introuvable (ignorée): {}", path)
        return set()
    df = pd.read_csv(p, usecols=lambda c: c == "technical_name", encoding=encoding, low_memory=False)
    if "technical_name" not in df.columns:
        logger.warning("Pas de colonne technical_name dans {} (ignorée)", path)
        return set()
    return set(df["technical_name"].dropna().astype(str).str.strip())


def _excluded_names(gold_path: str, human_globs: tuple[str, ...]) -> tuple[set[str], int, int]:
    """Union of technical_names from the gold + all human-eval CSVs."""
    gold_names = _names_from_csv(gold_path)  # gold v4 is plain utf-8
    human_names: set[str] = set()
    for pattern in human_globs:
        for f in sorted(glob.glob(pattern)):
            human_names |= _names_from_csv(f, encoding="utf-8-sig")  # human CSVs have a BOM
    return gold_names | human_names, len(gold_names), len(human_names)


def export_new_physical_for_labeling(
    run_id: int | None = None,
    output_path: str | None = None,
    gold_path: str = DEFAULT_GOLD,
    human_globs: tuple[str, ...] = DEFAULT_HUMAN_GLOBS,
    with_observed: bool = False,
    limit: int | None = None,
    seed: int = 42,
) -> str:
    """Export the not-yet-annotated physical tables to an annotable CSV."""
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    run_id = run_id if run_id is not None else _latest_run(pg)
    output_file = (
        Path(output_path)
        if output_path is not None
        else Path("exports") / f"dataset_asset_ml_run_{run_id}_new_physical_for_labeling.csv"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Selecting physical, annotable tables for run_id={}", run_id)
    rows = pg.fetch_all(PHYSICAL_SQL, {"run_id": run_id})
    n_physical = len(rows)

    excluded, n_gold, n_human = _excluded_names(gold_path, human_globs)
    logger.info(
        "Exclusion set: {} technical_names ({} gold + {} human, dédupliqués)",
        len(excluded), n_gold, n_human,
    )

    new_rows = [r for r in rows if str(r.get("technical_name") or "").strip() not in excluded]
    n_after_exclusion = len(new_rows)

    if limit is not None and n_after_exclusion > limit:
        # échantillon aléatoire reproductible, stratifié par asset_type
        df = pd.DataFrame(new_rows)
        frac = limit / n_after_exclusion
        sampled = (
            df.groupby("asset_type", group_keys=False)
            .apply(lambda g: g.sample(n=max(1, round(len(g) * frac)), random_state=seed))
        )
        if len(sampled) > limit:
            sampled = sampled.sample(n=limit, random_state=seed)
        new_rows = sampled.to_dict("records")
        logger.info("Échantillonné {} -> {} lignes (--limit, stratifié asset_type)", n_after_exclusion, len(new_rows))

    observed_enrichment, _ = _build_observed_enrichment(
        run_id=run_id,
        rows=new_rows,
        settings=settings,
        postgres_client=pg,
        enable_observed_values=with_observed,
    )

    export_rows: list[dict[str, Any]] = []
    for row in new_rows:
        try:
            asset_id = int(row.get("asset_id"))
        except (TypeError, ValueError):
            asset_id = -1
        export_rows.append(_build_enriched_row(row=row, observed_map=observed_enrichment.get(asset_id)))

    with output_file.open(mode="w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(EXPORT_COLUMNS))
        writer.writeheader()
        writer.writerows(export_rows)

    # split physique par asset_type pour le rapport
    by_type: dict[str, int] = {}
    for r in export_rows:
        by_type[str(r.get("asset_type"))] = by_type.get(str(r.get("asset_type")), 0) + 1

    logger.info("=== Export nouvelles tables physiques à annoter ===")
    logger.info("Univers physique (run {}): {}", run_id, n_physical)
    logger.info("  - deja annotees (gold + humain): {}", n_physical - n_after_exclusion)
    logger.info("  - NOUVELLES à annoter: {} {}", len(export_rows), by_type)
    logger.info("Fichier généré: {}", output_file)
    return str(output_file)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export physical tables absent from gold AND human-eval, for LLM annotation."
    )
    parser.add_argument("--run-id", type=int, default=None, help="Run to export (default: latest).")
    parser.add_argument("--output-path", default=None, help="Output CSV path.")
    parser.add_argument("--gold", default=DEFAULT_GOLD, help="Gold v4 CSV to exclude.")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of rows (stratified sample).")
    parser.add_argument("--with-observed", action="store_true", help="Enrich with real Oracle column samples (needs VPN).")
    args = parser.parse_args()

    configure_logging()
    out = export_new_physical_for_labeling(
        run_id=args.run_id,
        output_path=args.output_path,
        gold_path=args.gold,
        with_observed=args.with_observed,
        limit=args.limit,
    )
    logger.info("CSV prêt pour annotation LLM: {}", out)


if __name__ == "__main__":
    main()
