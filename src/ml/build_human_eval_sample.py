"""Build a stratified sample of predictions for HUMAN annotation (gold test).

Why: the production labels are LLM-generated, so the reported macro-F1 (~0.89)
measures agreement with the LLM, not real business correctness. This script
extracts a balanced sample of scored assets so a human can assign the true
domain, after which ``evaluate_human_gold.py`` computes a human-validated
accuracy and a circularity estimate.

Sampling strategy (where human effort is most informative):
- equal quota per PREDICTED domain  -> over-represents rare classes (RH, Ventes)
  relative to the population (they are tiny but error-prone);
- within each domain, bias toward ``review_required`` / low-confidence rows
  (errors concentrate there) while keeping some confident rows to check the
  easy cases and the confidence calibration.

Output: ``artifacts/human_eval_sample.csv`` (utf-8-sig, Excel-friendly) with an
empty ``human_label`` column to fill, plus a ``human_eval_labels.txt`` reference.

Usage:
    python -m src.ml.build_human_eval_sample
    python -m src.ml.build_human_eval_sample --run-id 6 --size 300 --review-ratio 0.6
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.transform.score_business_domain import (
    READ_SQL,
    _build_feature_matrix,
    _build_prediction_rows,
    _keyword_classify,
    _load_scoring_artifacts,
)
from src.utils.logging_utils import configure_logging

VALID_LABELS: tuple[str, ...] = (
    "Finance & Contrôle",
    "RH",
    "IT & Sécurité",
    "Achats & Fournisseurs",
    "Supply Chain / Logistique / Production",
    "Ventes & Clients",
    "Other",
)
ANNOTATION_HELP = "Ambigu/Inconnu"  # allowed extra value when the human is unsure

LATEST_RUN_SQL = "SELECT MAX(run_id) AS run_id FROM serving.asset_business_domain_prediction"

SAMPLE_SQL = """
SELECT
    s.asset_id,
    s.technical_name,
    s.source_ref,
    left(d.column_names_text, 300)            AS column_names,
    left(d.column_value_semantics_text, 300)  AS column_semantics,
    s.business_domain_predicted,
    s.business_domain_alt,
    round(s.confidence::numeric, 3)           AS confidence,
    s.confidence_band,
    s.review_required,
    s.model_version
FROM serving.v_asset_business_domain_scored s
LEFT JOIN processed.dataset_asset_ml d
  ON d.run_id = s.run_id AND d.asset_id = s.asset_id
WHERE s.run_id = :run_id
"""


def _excluded_asset_ids(exclude_paths: list[str]) -> set[int]:
    """Collect asset_ids already annotated in prior sample CSV(s), to avoid re-labeling."""
    excluded: set[int] = set()
    for path in exclude_paths:
        p = Path(path)
        if not p.exists():
            logger.warning("Exclude file not found, ignored: {}", p)
            continue
        prior = pd.read_csv(p, encoding="utf-8-sig")
        if "asset_id" in prior.columns:
            excluded.update(int(a) for a in pd.to_numeric(prior["asset_id"], errors="coerce").dropna())
    return excluded


def _disagreement_asset_ids(pg: PostgresClient, run_id: int, baseline_path: str) -> set[int]:
    """asset_ids where a baseline model disagrees with the deployed predictions.

    The deployed (current ``latest``) predictions are read from the DB; the
    baseline model is scored in-memory via the production path. Keyword-pass rows
    are model-independent, so only ML-routed rows can differ — exactly the
    contested, most-informative cases to annotate next (active learning).
    """
    deployed = {
        int(r["asset_id"]): r["business_domain_predicted"]
        for r in pg.fetch_all(
            "SELECT asset_id, business_domain_predicted "
            "FROM serving.asset_business_domain_prediction WHERE run_id = :run_id",
            {"run_id": run_id},
        )
    }
    rows = pg.fetch_all(READ_SQL, {"run_id": run_id})
    ml_rows = [r for r in rows if _keyword_classify(r) is None]
    art = _load_scoring_artifacts(baseline_path)
    matrix = _build_feature_matrix(ml_rows, art)
    preds = _build_prediction_rows(ml_rows, matrix, art, run_id=run_id)
    baseline = {
        int(p["asset_id"]): p["business_domain_predicted"]
        for p in preds if p.get("asset_id") is not None
    }
    diff = {aid for aid, lbl in baseline.items() if deployed.get(aid) != lbl}
    logger.info("Disagreement vs {}: {} contested asset(s)", Path(baseline_path).name, len(diff))
    return diff


def build_sample(
    run_id: int,
    size: int = 300,
    review_ratio: float = 0.6,
    seed: int = 42,
    output: str = "artifacts/human_eval_sample.csv",
    exclude: list[str] | None = None,
    disagreement_vs: str | None = None,
) -> dict[str, object]:
    """Build and export the stratified human-evaluation sample.

    If ``disagreement_vs`` (a baseline artifact path) is given, the candidate
    pool is restricted to assets where that baseline disagrees with the deployed
    model — the contested zone, most informative for the next annotation batch.
    """
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    if run_id is None:
        row = pg.fetch_one(LATEST_RUN_SQL, {})
        run_id = int(row["run_id"]) if row and row["run_id"] else 6

    logger.info("Fetching scored assets for run_id={}", run_id)
    rows = pg.fetch_all(SAMPLE_SQL, {"run_id": run_id})
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"No scored rows for run_id={run_id}")

    excluded = _excluded_asset_ids(exclude or [])
    if excluded:
        before = len(df)
        df = df[~df["asset_id"].astype("int64").isin(excluded)].reset_index(drop=True)
        logger.info("Excluded {} already-annotated asset(s); {} -> {} candidates",
                    len(excluded), before, len(df))

    if disagreement_vs:
        contested = _disagreement_asset_ids(pg, run_id, disagreement_vs)
        before = len(df)
        df = df[df["asset_id"].astype("int64").isin(contested)].reset_index(drop=True)
        logger.info("Restricted to disagreement zone; {} -> {} candidates", before, len(df))

    logger.info("Population: {} scored assets", len(df))

    domains = sorted(df["business_domain_predicted"].dropna().unique())
    per_domain = max(size // len(domains), 1)
    logger.info("{} predicted domains, target ~{}/domain", len(domains), per_domain)

    parts: list[pd.DataFrame] = []
    for domain, group in df.groupby("business_domain_predicted"):
        take = min(per_domain, len(group))
        review = group[group["review_required"] == True]  # noqa: E712
        confident = group[group["review_required"] == False]  # noqa: E712

        n_review = min(len(review), round(take * review_ratio))
        n_conf = take - n_review
        if n_conf > len(confident):  # not enough confident rows -> backfill from review
            n_conf = len(confident)
            n_review = min(len(review), take - n_conf)

        picks = []
        if n_review > 0:
            picks.append(review.sample(n_review, random_state=seed))
        if n_conf > 0:
            picks.append(confident.sample(n_conf, random_state=seed))
        if picks:
            parts.append(pd.concat(picks))

    sample = pd.concat(parts).sample(frac=1, random_state=seed).reset_index(drop=True)

    # Annotation columns
    sample["human_label"] = ""
    sample["human_notes"] = ""

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(out_path, index=False, encoding="utf-8-sig")

    # Reference of allowed labels for the annotator
    ref_path = out_path.with_name("human_eval_labels.txt")
    ref_path.write_text(
        "Valeurs autorisées pour la colonne 'human_label' :\n"
        + "\n".join(f"  - {label}" for label in VALID_LABELS)
        + f"\n  - {ANNOTATION_HELP}   (si réellement indécidable)\n\n"
        "Consigne : ignore la colonne 'business_domain_predicted' (c'est la prédiction\n"
        "du modèle à évaluer), juge le domaine d'après technical_name / source_ref /\n"
        "column_names / column_semantics, puis lance evaluate_human_gold.py.\n",
        encoding="utf-8",
    )

    dist = sample["business_domain_predicted"].value_counts().to_dict()
    review_n = int((sample["review_required"] == True).sum())  # noqa: E712
    logger.info("Sample written: {} rows -> {}", len(sample), out_path)
    logger.info("Per predicted domain: {}", dist)
    logger.info("review_required rows: {} / {}", review_n, len(sample))
    logger.info("Labels reference: {}", ref_path)

    return {
        "run_id": run_id,
        "sample_size": int(len(sample)),
        "output": str(out_path),
        "per_domain": dist,
        "review_required": review_n,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a stratified human-evaluation sample.")
    parser.add_argument("--run-id", type=int, default=None, help="Run id (default: latest).")
    parser.add_argument("--size", type=int, default=300, help="Target total sample size.")
    parser.add_argument("--review-ratio", type=float, default=0.6,
                        help="Fraction of each domain quota drawn from review_required rows.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--output", type=str, default="artifacts/human_eval_sample.csv",
                        help="Output CSV path.")
    parser.add_argument("--exclude", action="append", default=None,
                        help="Prior annotated CSV whose asset_ids to exclude (repeatable).")
    parser.add_argument("--disagreement-vs", default=None,
                        help="Baseline artifact path; restrict to assets where it disagrees with the deployed model.")
    args = parser.parse_args()

    configure_logging()
    result = build_sample(
        run_id=args.run_id,
        size=args.size,
        review_ratio=args.review_ratio,
        seed=args.seed,
        output=args.output,
        exclude=args.exclude,
        disagreement_vs=args.disagreement_vs,
    )
    logger.info("Done: {}", result)


if __name__ == "__main__":
    main()
