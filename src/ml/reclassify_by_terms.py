"""
Reclassify all data assets using the domain term base only.

Existing business_domain values are ignored — every row is classified
from scratch based on DOMAIN_TERMS keyword matching.

The script focuses output on four domains of interest:
  supply_chain, procurement, risk, marketing

It produces three CSV exports:
  exports/reclassified/<source>_all.csv           — all rows with new labels
  exports/reclassified/<source>_focus_domains.csv — rows matching the 4 domains
  exports/reclassified/<source>_unclassified.csv  — rows with no clear match

Usage:
    python -m src.ml.reclassify_by_terms --csv exports/my_enriched.csv
    python -m src.ml.reclassify_by_terms --run-id 5        (reads from DB)
    python -m src.ml.reclassify_by_terms                   (latest run from DB)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.ml.domain_term_base import DOMAIN_TERMS, KEYWORD_TO_LABEL

FOCUS_DOMAINS: frozenset[str] = frozenset(
    {"supply_chain", "procurement", "risk", "marketing"}
)

MIN_KEYWORD_HITS: int = 2
KEYWORD_DOMINANCE_RATIO: float = 3.0
KEYWORD_RULE_CONFIDENCE: float = 0.95

OUTPUT_DIR = Path("exports/reclassified")

# Pre-compile one pattern per domain — built once at import time
_PATTERNS: dict[str, re.Pattern[str]] = {
    domain: re.compile(
        r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b",
        flags=re.IGNORECASE,
    )
    for domain, terms in DOMAIN_TERMS.items()
}

# SQL to read the asset ML dataset from DB
_READ_SQL = """
SELECT
    run_id, asset_id, source_system, asset_type,
    technical_name, source_ref,
    column_names_text, column_value_semantics_text
FROM processed.dataset_asset_ml
WHERE run_id = :run_id
ORDER BY asset_id
"""
_LATEST_RUN_SQL = "SELECT MAX(run_id) AS run_id FROM processed.dataset_asset_ml"


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def _combined_text(row: dict[str, Any]) -> str:
    return " ".join([
        str(row.get("technical_name") or ""),
        str(row.get("source_ref") or ""),
        str(row.get("column_names_text") or ""),
        str(row.get("column_value_semantics_text") or ""),
    ]).lower()


def _hit_counts(combined: str) -> dict[str, int]:
    return {
        domain: len(pattern.findall(combined))
        for domain, pattern in _PATTERNS.items()
    }


def classify_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return classification result dict for one row."""
    combined = _combined_text(row)
    hits = _hit_counts(combined)

    sorted_hits = sorted(
        ((d, c) for d, c in hits.items() if c > 0),
        key=lambda x: x[1],
        reverse=True,
    )

    kw_domain: str = ""
    kw_label: str = "Inconnu"
    kw_confidence: float | None = None
    classified: bool = False

    if sorted_hits:
        top_domain, top_count = sorted_hits[0]
        if top_count >= MIN_KEYWORD_HITS:
            dominates = True
            if len(sorted_hits) > 1:
                _, second_count = sorted_hits[1]
                if top_count < KEYWORD_DOMINANCE_RATIO * second_count:
                    dominates = False
            if dominates:
                kw_domain = top_domain
                kw_label = KEYWORD_TO_LABEL.get(top_domain, "Inconnu")
                kw_confidence = KEYWORD_RULE_CONFIDENCE
                classified = True

    # Matched terms snapshot (up to 10) for the top domain
    matched_terms: str = ""
    if kw_domain:
        pattern = _PATTERNS[kw_domain]
        matched_terms = ", ".join(sorted(set(
            m.lower() for m in pattern.findall(combined)
        ))[:10])

    col_names_preview = str(row.get("column_names_text") or "")[:180]

    return {
        "asset_id":          row.get("asset_id", ""),
        "source_system":     row.get("source_system", ""),
        "asset_type":        row.get("asset_type", ""),
        "technical_name":    row.get("technical_name", ""),
        "source_ref":        row.get("source_ref", ""),
        "column_names_preview": col_names_preview,
        # classification result
        "kw_domain":         kw_domain,
        "kw_label":          kw_label,
        "kw_confidence":     kw_confidence if kw_confidence is not None else "",
        "classified":        classified,
        "is_focus_domain":   kw_domain in FOCUS_DOMAINS,
        "matched_terms":     matched_terms,
        # per-domain hit counts (raw)
        **{f"hits_{d}": hits.get(d, 0) for d in DOMAIN_TERMS},
    }


def classify_all(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [classify_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: list[dict[str, Any]]) -> None:
    total = len(results)
    classified_rows = [r for r in results if r["classified"]]
    n_classified = len(classified_rows)
    n_unclassified = total - n_classified

    domain_counts: dict[str, int] = defaultdict(int)
    for r in classified_rows:
        domain_counts[r["kw_domain"]] += 1

    lines = [
        "",
        "=" * 64,
        "  RECLASSIFICATION — term base only (existing labels ignored)",
        "=" * 64,
        f"  Total rows        : {total:>6}",
        f"  Classified        : {n_classified:>6}  ({100*n_classified/max(total,1):.1f}%)",
        f"  Unclassified      : {n_unclassified:>6}  ({100*n_unclassified/max(total,1):.1f}%)",
        "-" * 64,
        "  Domain breakdown (by term-base key):",
    ]
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        label = KEYWORD_TO_LABEL.get(domain, domain)
        focus = " ★ FOCUS" if domain in FOCUS_DOMAINS else ""
        lines.append(f"    {domain:<28} {count:>5}  → {label}{focus}")
    lines += [
        "-" * 64,
    ]
    focus_total = sum(c for d, c in domain_counts.items() if d in FOCUS_DOMAINS)
    lines.append(f"  Focus-domain total (★) : {focus_total:>5}")
    lines.append("=" * 64)
    lines.append("")

    for line in lines:
        print(line, file=sys.stderr)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_csv(results: list[dict[str, Any]], path: Path) -> None:
    if not results:
        print(f"[skip] No rows for {path.name}", file=sys.stderr)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"[ok]   {len(results):>5} rows → {path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_from_csv(path: str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {p}")
    with p.open(encoding="utf-8") as f:
        sample = f.read(4096)
    sep = ";" if sample.count(";") > sample.count(",") else ","
    with p.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=sep)
        rows = [dict(r) for r in reader]
    print(f"[ok]   {len(rows)} rows loaded from {p.name}", file=sys.stderr)
    return rows


def _load_from_db(run_id: int | None) -> list[dict[str, Any]]:
    from src.config.settings import get_settings
    from src.connectors.postgres_client import PostgresClient
    from src.utils.logging_utils import configure_logging
    configure_logging()

    settings = get_settings()
    client = PostgresClient(settings=settings)

    if run_id is None:
        row = client.fetch_one(_LATEST_RUN_SQL, {})
        run_id = int(row["run_id"]) if row and row["run_id"] else 1
        print(f"[ok]   Using latest run_id={run_id}", file=sys.stderr)

    rows = client.fetch_all(_READ_SQL, {"run_id": run_id})
    print(f"[ok]   {len(rows)} rows loaded from DB (run_id={run_id})", file=sys.stderr)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reclassify data assets using the domain term base only."
    )
    parser.add_argument("--run-id", type=int, default=None,
                        help="DB run_id (default: latest)")
    parser.add_argument("--csv", type=str, default=None,
                        help="Path to enriched CSV instead of DB")
    args = parser.parse_args()

    if args.csv:
        rows = _load_from_csv(args.csv)
        source_label = Path(args.csv).stem
    else:
        rows = _load_from_db(args.run_id)
        source_label = f"run{args.run_id or 'latest'}"

    results = classify_all(rows)
    print_summary(results)

    export_csv(results, OUTPUT_DIR / f"{source_label}_all.csv")
    export_csv(
        [r for r in results if r["is_focus_domain"]],
        OUTPUT_DIR / f"{source_label}_focus_domains.csv",
    )
    export_csv(
        [r for r in results if not r["classified"]],
        OUTPUT_DIR / f"{source_label}_unclassified.csv",
    )


if __name__ == "__main__":
    main()
