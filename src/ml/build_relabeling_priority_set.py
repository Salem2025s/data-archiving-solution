"""Build a relabeling priority set to improve business-domain classification."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

DEFAULT_CLEAN_PATH = "artifacts/labeled_dataset_clean.csv"
DEFAULT_PREDICTIONS_PATH = "artifacts/business_domain_test_predictions.csv"
DEFAULT_OUTPUT_PATH = "artifacts/relabeling_priority_set.csv"

RARE_CLASSES: tuple[str, ...] = ("RH", "Achats")

MIN_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "technical_name",
    "source_ref",
    "asset_type",
    "label_normalized",
    "predicted_label",
    "review_priority",
)


def _build_text_combined(df: pd.DataFrame) -> pd.Series:
    text_columns = [column for column in ("technical_name", "source_ref", "asset_type") if column in df.columns]
    if not text_columns:
        return pd.Series([""] * len(df), index=df.index, dtype="string")

    combined = df[text_columns[0]].astype("string").fillna("").str.strip()
    for column in text_columns[1:]:
        part = df[column].astype("string").fillna("").str.strip()
        combined = combined.str.cat(part, sep=" ", na_rep="")
    return combined.str.replace(r"\s+", " ", regex=True).str.strip()


def _detect_true_pred_columns(df: pd.DataFrame) -> tuple[str, str]:
    true_candidates = ("label_normalized", "y_true", "true_label", "label_true")
    pred_candidates = ("predicted_label", "y_pred", "pred_label", "prediction")

    true_column = next((column for column in true_candidates if column in df.columns), None)
    pred_column = next((column for column in pred_candidates if column in df.columns), None)

    if true_column is None or pred_column is None:
        raise ValueError(
            "Colonnes true/pred introuvables dans les prédictions. "
            f"Colonnes disponibles: {list(df.columns)}"
        )

    return true_column, pred_column


def _enrich_predictions_with_clean(predictions_df: pd.DataFrame, clean_df: pd.DataFrame) -> pd.DataFrame:
    predictions = predictions_df.copy()
    true_column, pred_column = _detect_true_pred_columns(predictions)

    predictions["label_normalized"] = predictions[true_column].astype("string").str.strip()
    predictions["predicted_label"] = predictions[pred_column].astype("string").str.strip()

    enrich_columns = [
        column
        for column in ("asset_id", "technical_name", "source_ref", "asset_type", "label_normalized")
        if column in clean_df.columns
    ]

    if "asset_id" in predictions.columns and all(col in predictions.columns for col in ("technical_name", "source_ref", "asset_type")):
        return predictions

    if "text_combined" not in predictions.columns:
        return predictions

    clean_work = clean_df.copy()
    clean_work["text_combined"] = _build_text_combined(clean_work)

    numeric_keys = [
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
        if column in predictions.columns and column in clean_work.columns
    ]

    merge_keys = ["text_combined", *numeric_keys]
    reference = clean_work[merge_keys + enrich_columns].drop_duplicates(subset=merge_keys, keep="first")

    merged = predictions.merge(reference, on=merge_keys, how="left", suffixes=("", "_clean"))

    for column in ("asset_id", "technical_name", "source_ref", "asset_type", "label_normalized"):
        clean_column = f"{column}_clean"
        if clean_column in merged.columns:
            if column in merged.columns:
                merged[column] = merged[column].fillna(merged[clean_column])
            else:
                merged[column] = merged[clean_column]

    return merged


def build_relabeling_priority_set(
    clean_path: str = DEFAULT_CLEAN_PATH,
    predictions_path: str = DEFAULT_PREDICTIONS_PATH,
    output_path: str = DEFAULT_OUTPUT_PATH,
) -> str:
    """Build and export a priority relabeling subset."""
    clean_file = Path(clean_path)
    predictions_file = Path(predictions_path)
    output_file = Path(output_path)

    if not clean_file.exists():
        raise FileNotFoundError(f"Fichier clean introuvable: {clean_file}")
    if not predictions_file.exists():
        raise FileNotFoundError(f"Fichier prédictions introuvable: {predictions_file}")

    clean_df = pd.read_csv(clean_file, encoding="utf-8")
    predictions_df = pd.read_csv(predictions_file, encoding="utf-8")

    enriched_predictions = _enrich_predictions_with_clean(predictions_df, clean_df)

    if "label_normalized" not in enriched_predictions.columns or "predicted_label" not in enriched_predictions.columns:
        raise ValueError("Colonnes label_normalized/predicted_label indisponibles après enrichissement.")

    enriched_predictions["label_normalized"] = enriched_predictions["label_normalized"].astype("string").str.strip()
    enriched_predictions["predicted_label"] = enriched_predictions["predicted_label"].astype("string").str.strip()

    # 1) Erreurs Technique -> Finance (high)
    err_tech_fin = enriched_predictions[
        (enriched_predictions["label_normalized"] == "Technique")
        & (enriched_predictions["predicted_label"] == "Finance")
    ].copy()
    err_tech_fin["review_priority"] = "high"

    # 2) Erreurs RH -> Finance (high)
    err_rh_fin = enriched_predictions[
        (enriched_predictions["label_normalized"] == "RH")
        & (enriched_predictions["predicted_label"] == "Finance")
    ].copy()
    err_rh_fin["review_priority"] = "high"

    # 3) Technique correctement reconnues (medium)
    correct_tech = enriched_predictions[
        (enriched_predictions["label_normalized"] == "Technique")
        & (enriched_predictions["predicted_label"] == "Technique")
    ].copy()
    correct_tech["review_priority"] = "medium"

    # 4) Toutes les lignes des classes rares (RH, Achats) (high)
    rare_subset = clean_df[clean_df["label_normalized"].isin(RARE_CLASSES)].copy()
    if "predicted_label" not in rare_subset.columns:
        rare_subset["predicted_label"] = pd.NA
    if "asset_id" in rare_subset.columns and "asset_id" in enriched_predictions.columns:
        # Propagate predicted_label from predictions when available for the same asset_id.
        predicted_map = (
            enriched_predictions[["asset_id", "predicted_label"]]
            .dropna(subset=["asset_id"])
            .copy()
        )
        predicted_map["asset_id"] = pd.to_numeric(predicted_map["asset_id"], errors="coerce")
        rare_subset["asset_id"] = pd.to_numeric(rare_subset["asset_id"], errors="coerce")
        rare_subset = rare_subset.merge(
            predicted_map.drop_duplicates(subset=["asset_id"], keep="first"),
            on="asset_id",
            how="left",
            suffixes=("", "_pred"),
        )
        rare_subset["predicted_label"] = rare_subset["predicted_label"].fillna(rare_subset["predicted_label_pred"])
        rare_subset = rare_subset.drop(columns=["predicted_label_pred"], errors="ignore")

    rare_subset["review_priority"] = "high"

    combined = pd.concat([err_tech_fin, err_rh_fin, correct_tech, rare_subset], ignore_index=True)

    # Compléter colonnes minimales si absentes
    for column in MIN_COLUMNS:
        if column not in combined.columns:
            combined[column] = pd.NA

    # Déduplication par asset_id avec priorité high > medium
    combined["priority_rank"] = combined["review_priority"].map({"high": 0, "medium": 1}).fillna(9)
    combined["asset_id"] = pd.to_numeric(combined["asset_id"], errors="coerce")
    combined = combined.sort_values(by=["priority_rank"]).drop_duplicates(subset=["asset_id"], keep="first")
    combined = combined[combined["asset_id"].notna()].copy()

    if "review_priority" in combined.columns:
        allowed = {"high", "medium"}
        invalid = set(combined["review_priority"].dropna().unique()) - allowed
        if invalid:
            raise ValueError(f"Valeurs review_priority invalides détectées: {invalid}")

    combined["asset_id"] = combined["asset_id"].astype("Int64")

    useful_columns = list(dict.fromkeys([*MIN_COLUMNS, *[c for c in combined.columns if c not in {"priority_rank"}]])).copy()
    useful_columns = [column for column in useful_columns if column in combined.columns and column != "priority_rank"]
    final_df = combined[useful_columns].copy()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(output_file, index=False, encoding="utf-8")

    logging.info("Relabeling priority set écrit: %s", output_file)
    logging.info("Lignes finales: %s", len(final_df))
    if "review_priority" in final_df.columns:
        logging.info("Distribution review_priority: %s", final_df["review_priority"].value_counts().to_dict())

    return str(output_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build relabeling priority set")
    parser.add_argument("--clean-path", type=str, default=DEFAULT_CLEAN_PATH)
    parser.add_argument("--predictions-path", type=str, default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument("--output-path", type=str, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    try:
        output = build_relabeling_priority_set(
            clean_path=args.clean_path,
            predictions_path=args.predictions_path,
            output_path=args.output_path,
        )
    except Exception as exc:
        logging.error("Échec build relabeling priority set: %s", exc)
        raise SystemExit(1) from exc

    print(f"Fichier produit: {output}")


if __name__ == "__main__":
    main()