"""Analyze baseline business-domain classifier errors and export diagnostics."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_CLEAN_PATH = "artifacts/labeled_dataset_clean.csv"
DEFAULT_PREDICTIONS_PATH = "artifacts/business_domain_test_predictions.csv"
DEFAULT_METRICS_PATH = "artifacts/business_domain_metrics.json"

DEFAULT_ERRORS_ALL_PATH = "artifacts/errors_all.csv"
DEFAULT_ERRORS_TF_PATH = "artifacts/errors_true_technique_pred_finance.csv"
DEFAULT_ERRORS_RF_PATH = "artifacts/errors_true_rh_pred_finance.csv"
DEFAULT_CORRECT_TECH_PATH = "artifacts/correct_technique.csv"
DEFAULT_ERROR_STATS_PATH = "artifacts/business_domain_error_stats.json"

MANDATORY_OUTPUTS: tuple[str, ...] = (
    DEFAULT_ERRORS_ALL_PATH,
    DEFAULT_ERRORS_TF_PATH,
    DEFAULT_ERRORS_RF_PATH,
    DEFAULT_CORRECT_TECH_PATH,
)

PREFERRED_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "technical_name",
    "source_ref",
    "asset_type",
    "label_normalized",
    "predicted_label",
    "prediction_confidence",
)


def _detect_true_pred_columns(df: pd.DataFrame) -> tuple[str, str]:
    true_candidates = ("label_normalized", "y_true", "true_label", "label_true")
    pred_candidates = ("predicted_label", "y_pred", "pred_label", "prediction")

    true_column = next((column for column in true_candidates if column in df.columns), None)
    pred_column = next((column for column in pred_candidates if column in df.columns), None)

    if true_column is None or pred_column is None:
        raise ValueError(
            "Impossible de détecter les colonnes true/pred dans le fichier de prédictions. "
            f"Colonnes disponibles: {list(df.columns)}"
        )

    return true_column, pred_column


def _build_text_combined(df: pd.DataFrame) -> pd.Series:
    text_columns = [column for column in ("technical_name", "source_ref", "asset_type") if column in df.columns]
    if not text_columns:
        return pd.Series([""] * len(df), index=df.index, dtype="string")

    combined = df[text_columns[0]].astype("string").fillna("").str.strip()
    for column in text_columns[1:]:
        part = df[column].astype("string").fillna("").str.strip()
        combined = combined.str.cat(part, sep=" ", na_rep="")
    return combined.str.replace(r"\s+", " ", regex=True).str.strip()


def load_predictions(
    clean_path: str,
    predictions_path: str,
    metrics_path: str,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Load predictions and enrich with clean dataset columns when possible."""
    clean_file = Path(clean_path)
    predictions_file = Path(predictions_path)
    metrics_file = Path(metrics_path)

    if not predictions_file.exists():
        raise FileNotFoundError(f"Fichier de prédictions introuvable: {predictions_file}")
    if not clean_file.exists():
        raise FileNotFoundError(f"Fichier clean introuvable: {clean_file}")
    if not metrics_file.exists():
        raise FileNotFoundError(f"Fichier métriques introuvable: {metrics_file}")

    predictions_df = pd.read_csv(predictions_file, encoding="utf-8")
    clean_df = pd.read_csv(clean_file, encoding="utf-8")
    with metrics_file.open("r", encoding="utf-8") as handle:
        metrics = json.load(handle)

    true_column, pred_column = _detect_true_pred_columns(predictions_df)
    predictions_df["label_normalized"] = predictions_df[true_column].astype("string").str.strip()
    predictions_df["predicted_label"] = predictions_df[pred_column].astype("string").str.strip()

    enrichable_columns = {
        "asset_id",
        "technical_name",
        "source_ref",
        "asset_type",
        "label_normalized",
        "label_raw",
        "has_profile_data",
    }
    enrichable_columns = enrichable_columns.intersection(set(clean_df.columns))

    merge_debug: dict[str, Any] = {
        "enriched": False,
        "merge_keys": [],
        "unmatched_rows": None,
    }

    if "text_combined" in predictions_df.columns:
        clean_with_text = clean_df.copy()
        clean_with_text["text_combined"] = _build_text_combined(clean_with_text)

        numeric_merge_keys = [
            column
            for column in (
                "field_count",
                "nullable_field_count",
                "non_nullable_field_count",
                "numeric_field_count",
                "date_field_count",
                "text_field_count",
                "large_text_field_count",
                "avg_data_length",
                "max_data_length",
                "row_count",
                "size_bytes",
                "size_mb",
            )
            if column in predictions_df.columns and column in clean_with_text.columns
        ]

        merge_keys = ["text_combined", *numeric_merge_keys]

        merge_reference = (
            clean_with_text[merge_keys + sorted(enrichable_columns)]
            .drop_duplicates(subset=merge_keys, keep="first")
            .copy()
        )

        before_columns = set(predictions_df.columns)
        predictions_df = predictions_df.merge(
            merge_reference,
            how="left",
            on=merge_keys,
            suffixes=("", "_clean"),
        )
        after_columns = set(predictions_df.columns)

        merge_debug["enriched"] = len(after_columns - before_columns) > 0
        merge_debug["merge_keys"] = merge_keys
        if "asset_id" in predictions_df.columns:
            merge_debug["unmatched_rows"] = int(predictions_df["asset_id"].isna().sum())

    return predictions_df, metrics, merge_debug


def _columns_for_export(df: pd.DataFrame) -> list[str]:
    preferred_present = [column for column in PREFERRED_COLUMNS if column in df.columns]

    excluded = {
        "y_true",
        "y_pred",
        "true_label",
        "pred_label",
        "prediction",
        "label_true",
    }
    feature_like_columns = [
        column
        for column in df.columns
        if column not in preferred_present and column not in excluded
    ]

    ordered_columns = [*preferred_present, *feature_like_columns]
    # preserve order and remove duplicates
    return list(dict.fromkeys(ordered_columns))


def build_error_exports(predictions_df: pd.DataFrame, artifacts_dir: str = "artifacts") -> dict[str, Any]:
    """Build error-focused CSV exports from predictions dataframe."""
    output_dir = Path(artifacts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    working_df = predictions_df.copy()
    working_df["is_correct"] = working_df["label_normalized"] == working_df["predicted_label"]

    errors_df = working_df[~working_df["is_correct"]].copy()
    correct_df = working_df[working_df["is_correct"]].copy()

    errors_tf = errors_df[
        (errors_df["label_normalized"] == "Technique")
        & (errors_df["predicted_label"] == "Finance")
    ].copy()

    errors_rf = errors_df[
        (errors_df["label_normalized"] == "RH")
        & (errors_df["predicted_label"] == "Finance")
    ].copy()

    correct_tech = correct_df[
        (correct_df["label_normalized"] == "Technique")
        & (correct_df["predicted_label"] == "Technique")
    ].copy()

    export_columns = _columns_for_export(working_df)

    paths = {
        "errors_all": output_dir / "errors_all.csv",
        "errors_true_technique_pred_finance": output_dir / "errors_true_technique_pred_finance.csv",
        "errors_true_rh_pred_finance": output_dir / "errors_true_rh_pred_finance.csv",
        "correct_technique": output_dir / "correct_technique.csv",
    }

    errors_df[export_columns].to_csv(paths["errors_all"], index=False, encoding="utf-8")
    errors_tf[export_columns].to_csv(
        paths["errors_true_technique_pred_finance"],
        index=False,
        encoding="utf-8",
    )
    errors_rf[export_columns].to_csv(
        paths["errors_true_rh_pred_finance"],
        index=False,
        encoding="utf-8",
    )
    correct_tech[export_columns].to_csv(paths["correct_technique"], index=False, encoding="utf-8")

    return {
        "paths": {key: str(value) for key, value in paths.items()},
        "counts": {
            "total_predictions": int(len(working_df)),
            "total_errors": int(len(errors_df)),
            "errors_true_technique_pred_finance": int(len(errors_tf)),
            "errors_true_rh_pred_finance": int(len(errors_rf)),
            "correct_technique": int(len(correct_tech)),
        },
    }


def build_error_stats(
    predictions_df: pd.DataFrame,
    metrics: dict[str, Any],
    exports_info: dict[str, Any],
    merge_debug: dict[str, Any],
    stats_path: str = DEFAULT_ERROR_STATS_PATH,
) -> dict[str, Any]:
    """Compute and persist error statistics as JSON."""
    working_df = predictions_df.copy()
    working_df["is_correct"] = working_df["label_normalized"] == working_df["predicted_label"]

    errors_df = working_df[~working_df["is_correct"]].copy()

    errors_by_true = errors_df["label_normalized"].value_counts().to_dict()
    errors_by_pair_series = (
        errors_df.groupby(["label_normalized", "predicted_label"]).size().sort_values(ascending=False)
    )
    errors_by_pair = [
        {
            "true_label": true_label,
            "predicted_label": predicted_label,
            "count": int(count),
        }
        for (true_label, predicted_label), count in errors_by_pair_series.items()
    ]

    stats: dict[str, Any] = {
        "total_predictions": int(len(working_df)),
        "total_errors": int(len(errors_df)),
        "error_rate": float(len(errors_df) / len(working_df)) if len(working_df) else 0.0,
        "errors_by_true_class": errors_by_true,
        "errors_by_true_pred_pair": errors_by_pair,
        "model_metrics_snapshot": {
            "accuracy": metrics.get("accuracy"),
            "f1_macro": metrics.get("f1_macro"),
            "f1_weighted": metrics.get("f1_weighted"),
        },
        "exports": exports_info,
        "merge_debug": merge_debug,
    }

    stats_file = Path(stats_path)
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    with stats_file.open("w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze business-domain classifier errors")
    parser.add_argument("--clean-path", default=DEFAULT_CLEAN_PATH, type=str)
    parser.add_argument("--predictions-path", default=DEFAULT_PREDICTIONS_PATH, type=str)
    parser.add_argument("--metrics-path", default=DEFAULT_METRICS_PATH, type=str)
    parser.add_argument("--stats-path", default=DEFAULT_ERROR_STATS_PATH, type=str)
    parser.add_argument("--artifacts-dir", default="artifacts", type=str)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    try:
        predictions_df, metrics, merge_debug = load_predictions(
            clean_path=args.clean_path,
            predictions_path=args.predictions_path,
            metrics_path=args.metrics_path,
        )

        exports_info = build_error_exports(predictions_df=predictions_df, artifacts_dir=args.artifacts_dir)
        stats = build_error_stats(
            predictions_df=predictions_df,
            metrics=metrics,
            exports_info=exports_info,
            merge_debug=merge_debug,
            stats_path=args.stats_path,
        )
    except Exception as exc:
        logging.error("Analyse des erreurs échouée: %s", exc)
        raise SystemExit(1) from exc

    logging.info("Analyse terminée")
    logging.info("Total prédictions: %s", stats["total_predictions"])
    logging.info("Total erreurs: %s", stats["total_errors"])
    logging.info("Error rate: %.4f", stats["error_rate"])
    logging.info("Accuracy snapshot: %s", stats["model_metrics_snapshot"].get("accuracy"))
    logging.info("Macro F1 snapshot: %s", stats["model_metrics_snapshot"].get("f1_macro"))
    logging.info("Weighted F1 snapshot: %s", stats["model_metrics_snapshot"].get("f1_weighted"))

    print("Exports produits:")
    for key, path in exports_info["paths"].items():
        print(f"- {key}: {path}")
    print(f"- error_stats: {args.stats_path}")


if __name__ == "__main__":
    main()