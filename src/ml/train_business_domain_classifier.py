"""Train a baseline business-domain classifier from a cleaned labeled CSV."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TEXT_COLUMNS: tuple[str, ...] = (
    "technical_name",
    "source_ref",
    "asset_type",
)

NUMERIC_COLUMNS: tuple[str, ...] = (
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

TARGET_COLUMN = "label_normalized"


def build_feature_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, dict[str, list[str]]]:
    """Build model-ready feature frame and target from available CSV columns."""
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Colonne cible absente: {TARGET_COLUMN}")

    available_text = [column for column in TEXT_COLUMNS if column in df.columns]
    available_numeric = [column for column in NUMERIC_COLUMNS if column in df.columns]

    if not available_text and not available_numeric:
        raise ValueError("Aucune feature exploitable trouvée (texte ou numérique).")

    feature_df = pd.DataFrame(index=df.index)

    if available_text:
        text_parts = []
        for column in available_text:
            text_part = df[column].astype("string").fillna("").str.strip()
            text_parts.append(text_part)
        combined = text_parts[0]
        for text_part in text_parts[1:]:
            combined = combined.str.cat(text_part, sep=" ", na_rep="")
        combined = combined.str.replace(r"\s+", " ", regex=True).str.strip()
    else:
        combined = pd.Series([""] * len(df), index=df.index, dtype="string")

    if (combined == "").all():
        combined = pd.Series(["no_text"] * len(df), index=df.index, dtype="string")

    feature_df["text_combined"] = combined

    for column in available_numeric:
        feature_df[column] = pd.to_numeric(df[column], errors="coerce")

    target = df[TARGET_COLUMN].astype("string").str.strip()
    valid_mask = target.notna() & (target != "")

    feature_df = feature_df.loc[valid_mask].copy()
    target = target.loc[valid_mask].copy()

    used_features = {
        "text": available_text,
        "numeric": available_numeric,
    }
    return feature_df, target, used_features


def build_pipeline(numeric_columns: list[str]) -> Pipeline:
    """Build baseline sklearn pipeline with text + optional numeric features."""
    transformers: list[tuple[str, Any, Any]] = []

    text_transformer = Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=1,
                ),
            )
        ]
    )
    transformers.append(("text", text_transformer, "text_combined"))

    if numeric_columns:
        numeric_transformer = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler(with_mean=False)),
            ]
        )
        transformers.append(("num", numeric_transformer, numeric_columns))

    preprocessor = ColumnTransformer(transformers=transformers)

    classifier = LogisticRegression(
        max_iter=3000,
        class_weight="balanced",
        random_state=42,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def train_and_evaluate(
    input_path: str,
    model_path: str,
    metrics_path: str,
    predictions_path: str,
) -> dict[str, Any]:
    """Train baseline model, evaluate it, and persist artifacts."""
    input_file = Path(input_path)
    model_file = Path(model_path)
    metrics_file = Path(metrics_path)
    predictions_file = Path(predictions_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Dataset introuvable: {input_file}")

    logging.info("Chargement du dataset propre: %s", input_file)
    df = pd.read_csv(input_file, encoding="utf-8")

    X, y, used_features = build_feature_frame(df)
    if X.empty or y.empty:
        raise ValueError("Dataset vide après préparation des features/cible.")

    class_counts = y.value_counts()
    if class_counts.min() < 2:
        raise ValueError(
            "Stratify impossible: au moins une classe a moins de 2 observations. "
            f"Distribution: {class_counts.to_dict()}"
        )

    logging.info("Split train/test (test_size=0.2, random_state=42, stratify=y)")
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    pipeline = build_pipeline(numeric_columns=used_features["numeric"])

    logging.info("Entraînement LogisticRegression baseline")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)

    labels_sorted = sorted(y.unique().tolist())
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    conf_matrix = confusion_matrix(y_test, y_pred, labels=labels_sorted)

    metrics: dict[str, Any] = {
        "input_path": str(input_file),
        "rows_total": int(len(X)),
        "rows_train": int(len(X_train)),
        "rows_test": int(len(X_test)),
        "target_column": TARGET_COLUMN,
        "used_text_features": used_features["text"],
        "used_numeric_features": used_features["numeric"],
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
        "classification_report": report,
        "confusion_matrix": {
            "labels": labels_sorted,
            "matrix": conf_matrix.tolist(),
        },
        "train_distribution": y_train.value_counts().to_dict(),
        "test_distribution": y_test.value_counts().to_dict(),
    }

    model_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    predictions_file.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Sauvegarde modèle: %s", model_file)
    joblib.dump(pipeline, model_file)

    logging.info("Sauvegarde métriques: %s", metrics_file)
    with metrics_file.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)

    test_predictions = X_test.copy()
    test_predictions["y_true"] = y_test
    test_predictions["y_pred"] = y_pred
    test_predictions.to_csv(predictions_file, index=False, encoding="utf-8")
    logging.info("Sauvegarde prédictions test: %s", predictions_file)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train baseline business-domain classifier")
    parser.add_argument(
        "--input-path",
        type=str,
        default="artifacts/labeled_dataset_clean.csv",
        help="Path to cleaned labeled dataset CSV",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default="artifacts/business_domain_model.joblib",
        help="Output path for trained model",
    )
    parser.add_argument(
        "--metrics-path",
        type=str,
        default="artifacts/business_domain_metrics.json",
        help="Output path for metrics JSON",
    )
    parser.add_argument(
        "--predictions-path",
        type=str,
        default="artifacts/business_domain_test_predictions.csv",
        help="Output path for test predictions CSV",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        metrics = train_and_evaluate(
            input_path=args.input_path,
            model_path=args.model_path,
            metrics_path=args.metrics_path,
            predictions_path=args.predictions_path,
        )
    except Exception as exc:
        logging.error("Échec entraînement baseline: %s", exc)
        raise SystemExit(1) from exc

    logging.info(
        "Training terminé | accuracy=%.4f | f1_macro=%.4f | f1_weighted=%.4f",
        metrics["accuracy"],
        metrics["f1_macro"],
        metrics["f1_weighted"],
    )
    print(
        "Baseline entraîné | "
        f"text={metrics['used_text_features']} | "
        f"num={metrics['used_numeric_features']} | "
        f"model={args.model_path}"
    )


if __name__ == "__main__":
    main()