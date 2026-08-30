"""Evaluate model predictions against HUMAN-annotated gold labels (#5).

Consumes the CSV produced by ``build_human_eval_sample.py`` once a human has
filled the ``human_label`` column. Computes the metrics that the LLM-labelled
holdout cannot give:

- accuracy / macro-F1 / weighted-F1 + per-class report (vs reference labels),
- Cohen's kappa (human vs model),
- accuracy by ``confidence_band`` (is ``confidence`` calibrated?),
- accuracy on ``review_required`` rows vs the rest (does the review flag catch
  the errors?).

Model-agnostic: it only needs ``human_label`` + ``business_domain_predicted``.
For a head-to-head, re-score the same ``asset_id`` set with another model, drop
its predictions into ``business_domain_predicted`` and re-run.

Usage:
    python -m src.ml.evaluate_human_gold
    python -m src.ml.evaluate_human_gold --input artifacts/human_eval_sample.csv --pred-col business_domain_predicted
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
)

AMBIGUOUS = "Ambigu/Inconnu"


def _acc_by(df: pd.DataFrame, col: str, true_col: str, pred_col: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if col not in df.columns:
        return out
    for value, group in df.groupby(col):
        if len(group):
            out[str(value)] = {
                "n": int(len(group)),
                "accuracy": round(float(accuracy_score(group[true_col], group[pred_col])), 4),
            }
    return out


def evaluate(
    input_path: str = "artifacts/human_eval_sample.csv",
    pred_col: str = "business_domain_predicted",
    output_path: str = "artifacts/human_eval_report.json",
) -> dict[str, Any]:
    """Compute metrics vs reference labels from an annotated sample."""
    in_file = Path(input_path)
    if not in_file.exists():
        raise FileNotFoundError(f"Annotated sample introuvable: {in_file}")

    df = pd.read_csv(in_file, encoding="utf-8-sig")
    if "human_label" not in df.columns or pred_col not in df.columns:
        raise ValueError(f"Colonnes requises absentes: human_label et {pred_col}")

    df["human_label"] = df["human_label"].astype("string").fillna("").str.strip()
    total_rows = len(df)
    annotated = df[df["human_label"] != ""].copy()
    n_annotated = len(annotated)
    if n_annotated == 0:
        raise ValueError("Aucune ligne annotée (colonne human_label vide partout).")

    n_ambiguous = int((annotated["human_label"] == AMBIGUOUS).sum())
    scored = annotated[annotated["human_label"] != AMBIGUOUS].copy()
    n_scored = len(scored)
    if n_scored == 0:
        raise ValueError("Toutes les lignes annotées sont 'Ambigu/Inconnu' — rien à scorer.")

    y_true = scored["human_label"].astype(str)
    y_pred = scored[pred_col].astype(str)
    labels = sorted(set(y_true) | set(y_pred))

    report: dict[str, Any] = {
        "input": str(in_file),
        "pred_col": pred_col,
        "rows_total": total_rows,
        "rows_annotated": n_annotated,
        "rows_ambiguous": n_ambiguous,
        "rows_scored": n_scored,
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_weighted": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
        "cohen_kappa_human_vs_model": round(float(cohen_kappa_score(y_true, y_pred)), 4),
        "per_class": classification_report(y_true, y_pred, output_dict=True, zero_division=0),
        "confusion_matrix": {
            "labels": labels,
            "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        },
        "accuracy_by_confidence_band": _acc_by(scored, "confidence_band", "human_label", pred_col),
        "accuracy_by_review_required": _acc_by(scored, "review_required", "human_label", pred_col),
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("=== Reference-label evaluation ({} scored / {} annotated / {} total) ===",
                n_scored, n_annotated, total_rows)
    logger.info("Accuracy={accuracy}  macro-F1={f1_macro}  weighted-F1={f1_weighted}  kappa={k}",
                accuracy=report["accuracy"], f1_macro=report["f1_macro"],
                f1_weighted=report["f1_weighted"], k=report["cohen_kappa_human_vs_model"])
    logger.info("Accuracy by confidence_band: {}", report["accuracy_by_confidence_band"])
    logger.info("Accuracy by review_required: {}", report["accuracy_by_review_required"])
    logger.info("Report saved: {}", out_file)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate predictions vs reference labels.")
    parser.add_argument("--input", default="artifacts/human_eval_sample.csv", help="Annotated CSV.")
    parser.add_argument("--pred-col", default="business_domain_predicted", help="Prediction column to score.")
    parser.add_argument("--output", default="artifacts/human_eval_report.json", help="Report JSON path.")
    args = parser.parse_args()

    configure_logging_safe()
    evaluate(input_path=args.input, pred_col=args.pred_col, output_path=args.output)


def configure_logging_safe() -> None:
    try:
        from src.utils.logging_utils import configure_logging
        configure_logging()
    except Exception:
        pass


if __name__ == "__main__":
    main()
