"""Prepare a cleaned labeled dataset from weak LLM labels.

This script:
- loads a labeled CSV export,
- detects the label column,
- normalizes raw labels to a strict target taxonomy,
- drops non-exploitable rows,
- writes a cleaned CSV and a compact JSON stats report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

TARGET_LABELS: tuple[str, ...] = (
    "RH",
    "Finance",
    "Paie",
    "Achats",
    "Technique",
    "Inconnu",
)

EXPLOITABLE_LABELS: tuple[str, ...] = (
    "RH",
    "Finance",
    "Paie",
    "Achats",
    "Technique",
)

LABEL_CANDIDATES: tuple[str, ...] = (
    "business_domain_label",
    "label",
    "llm_label",
    "domain_label",
    "business_label",
    "label_metier",
    "metier_label",
    "target_label",
    "class_label",
)

FEATURE_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "source_system",
    "asset_type",
    "technical_name",
    "source_ref",
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
    "has_profile_data",
)


def _fold_text(value: str) -> str:
    text = value.strip().lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_label_column(df: pd.DataFrame) -> str:
    """Detect the most plausible label column from dataframe columns."""
    if df.empty:
        raise ValueError("Le CSV est vide: impossible de détecter une colonne de label.")

    column_map = {str(col).lower().strip(): str(col) for col in df.columns}

    for candidate in LABEL_CANDIDATES:
        if candidate in column_map:
            return column_map[candidate]

    scored: list[tuple[str, int, float, int]] = []
    for column in df.columns:
        column_name = str(column)
        lowered = column_name.lower()

        score = 0
        if "label" in lowered:
            score += 5
        if any(token in lowered for token in ("domain", "metier", "business", "classe")):
            score += 3

        series = df[column_name].astype("string").fillna("").str.strip()
        non_empty = series[series != ""]
        fill_rate = float(len(non_empty)) / float(len(df))
        unique_non_empty = int(non_empty.nunique())

        if unique_non_empty > 1:
            score += 2
        if unique_non_empty > 3:
            score += 1

        scored.append((column_name, score, fill_rate, unique_non_empty))

    scored.sort(key=lambda item: (-item[1], -item[2], item[0]))
    best_column, best_score, *_ = scored[0]

    if best_score <= 0:
        raise ValueError(
            "Aucune colonne de label plausible détectée. "
            f"Colonnes disponibles: {list(df.columns)}"
        )

    return best_column


def normalize_label(value: Any) -> str:
    """Normalize a raw label to the strict target taxonomy."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Inconnu"

    raw = str(value).strip()
    if not raw:
        return "Inconnu"

    folded = _fold_text(raw)

    if re.search(r"\brh\b|ressources? humaines?|human resources?|\bhr\b", folded):
        return "RH"

    if re.search(r"\bpaie\b|payroll|remuneration|salaire", folded):
        return "Paie"

    if re.search(r"finance|financier|compta|comptable|accounting|budget|tresorerie", folded):
        return "Finance"

    if re.search(r"achat|procurement|purchas|approvisionnement|fournisseur", folded):
        return "Achats"

    if re.search(
        r"techni|\bit\b|infra|systeme|system|admin|securite|security|data|etl|\bdb\b|base de donnees|devops|ops",
        folded,
    ):
        return "Technique"

    if re.search(r"inconnu|unknown|autre|other|\bna\b|n/a|none|non classe|non renseigne|unsure", folded):
        return "Inconnu"

    return "Inconnu"


def prepare_labeled_dataset(input_path: str, output_path: str, stats_path: str) -> dict[str, Any]:
    """Prepare and export a cleaned labeled dataset and stats JSON."""
    input_file = Path(input_path)
    output_file = Path(output_path)
    stats_file = Path(stats_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Fichier d'entrée introuvable: {input_file}")

    df = pd.read_csv(input_file, sep=None, engine="python", encoding="utf-8-sig")
    initial_count = int(len(df))

    label_column = detect_label_column(df)
    df["label_raw"] = df[label_column].astype("string").fillna("").str.strip()
    df["label_normalized"] = df["label_raw"].apply(normalize_label)

    retained_df = df[df["label_normalized"].isin(EXPLOITABLE_LABELS)].copy()

    columns_to_keep = [col for col in FEATURE_COLUMNS if col in retained_df.columns]
    columns_to_keep.extend(["label_raw", "label_normalized"])
    retained_df = retained_df[columns_to_keep]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.parent.mkdir(parents=True, exist_ok=True)

    retained_df.to_csv(output_file, index=False, encoding="utf-8")

    normalized_distribution = (
        retained_df["label_normalized"].value_counts(dropna=False).to_dict()
        if not retained_df.empty
        else {}
    )

    stats: dict[str, Any] = {
        "input_path": str(input_file),
        "output_path": str(output_file),
        "label_column_detected": label_column,
        "rows_initial": initial_count,
        "rows_retained": int(len(retained_df)),
        "rows_dropped": int(initial_count - len(retained_df)),
        "normalized_label_distribution": normalized_distribution,
        "target_labels": list(TARGET_LABELS),
        "retention_rule": "Conserve uniquement RH/Finance/Paie/Achats/Technique; exclut Inconnu.",
    }

    with stats_file.open("w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare cleaned labeled dataset for training")
    parser.add_argument(
        "--input-path",
        type=str,
        default="exports/dataset_asset_ml_run_5_for_labeling_sample_1200_labeled.csv",
        help="Path to labeled input CSV",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default="artifacts/labeled_dataset_clean.csv",
        help="Path to cleaned output CSV",
    )
    parser.add_argument(
        "--stats-path",
        type=str,
        default="artifacts/labeled_dataset_stats.json",
        help="Path to JSON stats output",
    )
    args = parser.parse_args()

    try:
        stats = prepare_labeled_dataset(
            input_path=args.input_path,
            output_path=args.output_path,
            stats_path=args.stats_path,
        )
    except Exception as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        "Préparation terminée | "
        f"label={stats['label_column_detected']} | "
        f"retenues={stats['rows_retained']}/{stats['rows_initial']} | "
        f"sortie={stats['output_path']}"
    )


if __name__ == "__main__":
    main()