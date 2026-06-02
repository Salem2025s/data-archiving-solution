"""Reproducible CLI training for the PRODUCTION business-domain classifier.

Ports ``LLM/business_domain_production.ipynb`` into a deterministic script so the
production model can be retrained without a notebook.

Design — train/inference parity by construction
------------------------------------------------
The feature builders are imported from :mod:`src.transform.score_business_domain`
(``_build_numeric_values``, ``_compose_text``, ``normalize_text`` and the
``DOMAIN_KEYWORDS`` / ``PS_MODULE_PREFIXES`` / ``KNOWN_SEMANTIC_LABELS`` tables).
Training therefore uses the *exact same* feature code as scoring, which removes
the whole class of train/inference feature-mismatch bugs.

The produced artifact is byte-compatible with
``score_business_domain._load_scoring_artifacts`` (same dict keys), and
``model_version`` resolves to ``<pipeline_version>_<timestamp>``.

Safety: by default this writes a *timestamped* artifact and does NOT overwrite
the deployed ``production_pipeline_latest.joblib``. Pass ``--promote-latest`` to
also refresh the ``latest`` copy once you have validated the new model.

Usage
-----
    python -m src.ml.train_production_classifier
    python -m src.ml.train_production_classifier --pipeline-version v3.1 --promote-latest
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from scipy.sparse import csr_matrix, hstack
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, cohen_kappa_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.svm import LinearSVC

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.transform.score_business_domain import (
    DEFAULT_CAT_COLS,
    DEFAULT_TEXT_COLS_CHAR,
    DEFAULT_TEXT_COLS_WORD,
    DOMAIN_KEYWORDS,
    KNOWN_SEMANTIC_LABELS,
    PS_MODULE_PREFIXES,
    _build_feature_matrix,
    _build_numeric_values,
    _build_prediction_rows,
    _compose_text,
    _keyword_classify,
    _load_scoring_artifacts,
)
from src.utils.logging_utils import configure_logging

AMBIGUOUS_LABEL = "Ambigu/Inconnu"
HUMAN_FEATURE_SQL = """
SELECT
    asset_id, source_system, asset_type, technical_name, source_ref,
    column_names_text, column_type_signature_text, column_value_semantics_text,
    field_count, nullable_field_count, non_nullable_field_count, numeric_field_count,
    date_field_count, text_field_count, large_text_field_count, avg_data_length,
    max_data_length, row_count, size_bytes, size_mb, has_profile_data
FROM processed.dataset_asset_ml
WHERE run_id = :run_id AND asset_id = ANY(:asset_ids)
"""

# --- Constants mirrored from business_domain_production.ipynb -----------------
DEFAULT_INPUT = (
    "exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_business_domain_v4.csv"
)
DEFAULT_OUTPUT_DIR = "LLM/artifacts_business_domain"
TARGET = "business_domain"
CONSENSUS_COL = "llm_consensus_score"
CONSENSUS_SOFT_FLOOR = 0.7  # gold = consensus >= this
RANDOM_STATE = 42
TEST_SIZE = 0.15

CHAR_NGRAMS = (3, 5)
WORD_NGRAMS = (1, 2)
CHAR_MAX_FEATURES = 50_000
WORD_MAX_FEATURES = 80_000

SQL_STOPWORDS = [
    "varchar2", "number", "date", "timestamp", "clob", "blob", "long",
    "char", "raw", "xmltype", "float", "integer", "nvarchar2", "nclob",
    "timestamp(6)", "sysadm", "ps",
]

DROP_COLS = [
    "business_domain_raw", "business_domain_label", "labeling_notes",
    "llm_votes_json", "llm_consensus_score", "llm_models_used",
    "llm_prompt_version", "llm_status", "confidence", "reason",
    "run_id", "asset_id",
]
DROPPED_TEXT_COLS = [
    "column_type_signature_text", "column_value_semantics_text",
    "column_sample_values_text", "column_observed_pattern_text",
]


def _make_ohe() -> OneHotEncoder:
    """OneHotEncoder(handle_unknown='ignore') compatible across sklearn versions."""
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=True, dtype=np.float32)
    except TypeError:  # sklearn < 1.2
        return OneHotEncoder(handle_unknown="ignore", sparse=True, dtype=np.float32)


def _numeric_feature_order() -> list[str]:
    """Stable numeric feature order = keys produced by ``_build_numeric_values``.

    The dict is built deterministically (independent of the row), so any row
    yields the canonical column order. This exact list is saved as
    ``numeric_feature_names`` and reused at inference time, guaranteeing the
    train/score matrices line up column-for-column.
    """
    probe = {"technical_name": "", "source_ref": "", "column_names_text": ""}
    return list(_build_numeric_values(probe).keys())


def _numeric_matrix(rows: list[dict[str, Any]], names: list[str]) -> np.ndarray:
    """Build the numeric matrix using the SAME builder score_business_domain uses."""
    arr = np.zeros((len(rows), len(names)), dtype=np.float32)
    for i, row in enumerate(rows):
        values = _build_numeric_values(row)
        for j, name in enumerate(names):
            arr[i, j] = np.float32(values.get(name, 0.0))
    return arr


def _cat_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Categorical frame for OHE (string-typed, mirrors the production notebook)."""
    data = {
        col: ["missing" if row.get(col) is None else str(row.get(col)) for row in rows]
        for col in DEFAULT_CAT_COLS
    }
    return pd.DataFrame(data)


def _fit_char_word(rows: list[dict[str, Any]]) -> tuple[TfidfVectorizer, TfidfVectorizer, Any, Any]:
    char_text = _compose_text(rows, list(DEFAULT_TEXT_COLS_CHAR))
    word_text = _compose_text(rows, list(DEFAULT_TEXT_COLS_WORD))
    char_vec = TfidfVectorizer(
        analyzer="char_wb", ngram_range=CHAR_NGRAMS, min_df=3,
        max_features=CHAR_MAX_FEATURES, sublinear_tf=True, dtype=np.float32,
    )
    word_vec = TfidfVectorizer(
        analyzer="word", ngram_range=WORD_NGRAMS, min_df=3,
        max_features=WORD_MAX_FEATURES, sublinear_tf=True, dtype=np.float32,
        stop_words=SQL_STOPWORDS,
    )
    x_char = char_vec.fit_transform(char_text)
    x_word = word_vec.fit_transform(word_text)
    return char_vec, word_vec, x_char, x_word


def _assemble(
    rows: list[dict[str, Any]],
    names: list[str],
    char_vec: TfidfVectorizer,
    word_vec: TfidfVectorizer,
    num_scaler: StandardScaler,
    ohe: OneHotEncoder,
) -> csr_matrix:
    """Transform rows with already-fitted components → [char|word|num|ohe]."""
    x_char = char_vec.transform(_compose_text(rows, list(DEFAULT_TEXT_COLS_CHAR)))
    x_word = word_vec.transform(_compose_text(rows, list(DEFAULT_TEXT_COLS_WORD)))
    x_num = csr_matrix(num_scaler.transform(_numeric_matrix(rows, names)))
    x_cat = ohe.transform(_cat_frame(rows))
    return hstack([x_char, x_word, x_num, x_cat]).tocsr()


def _load_human_labels(csv_paths: list[str]) -> dict[int, str]:
    """Collect {asset_id: human_label} from annotated CSV(s); drop empty/ambiguous."""
    labels: dict[int, str] = {}
    for path in csv_paths:
        p = Path(path)
        if not p.exists():
            logger.warning("Human-label CSV not found, ignored: {}", p)
            continue
        df = pd.read_csv(p, encoding="utf-8-sig")
        if "asset_id" not in df.columns or "human_label" not in df.columns:
            logger.warning("CSV {} lacks asset_id/human_label, ignored", p)
            continue
        df["human_label"] = df["human_label"].astype("string").fillna("").str.strip()
        for asset_id, label in zip(df["asset_id"], df["human_label"]):
            if not label or label == AMBIGUOUS_LABEL:
                continue
            try:
                aid = int(asset_id)
            except (TypeError, ValueError):
                continue
            labels.setdefault(aid, str(label))  # first CSV wins on conflict
    return labels


def _fetch_feature_rows(asset_ids: list[int], run_id: int) -> dict[int, dict[str, Any]]:
    """Fetch full feature rows for asset_ids from processed.dataset_asset_ml (run_id)."""
    if not asset_ids:
        return {}
    pg = PostgresClient(settings=get_settings())
    rows = pg.fetch_all(HUMAN_FEATURE_SQL, {"run_id": run_id, "asset_ids": list(asset_ids)})
    return {int(r["asset_id"]): dict(r) for r in rows}


def _system_predict(rows: list[dict[str, Any]], model_path: str) -> tuple[str, list[str]]:
    """Final label per row via the PRODUCTION path (keyword pass, else ML), using one artifact."""
    artifacts = _load_scoring_artifacts(model_path)
    labels: list[Any] = [None] * len(rows)
    ml_rows: list[dict[str, Any]] = []
    ml_idx: list[int] = []
    for i, row in enumerate(rows):
        kw = _keyword_classify(row)
        if kw is not None:
            labels[i] = kw[0]
        else:
            ml_rows.append(row)
            ml_idx.append(i)
    if ml_rows:
        matrix = _build_feature_matrix(ml_rows, artifacts)
        preds = _build_prediction_rows(ml_rows, matrix, artifacts, run_id=0)
        by_id = {
            int(p["asset_id"]): p["business_domain_predicted"]
            for p in preds if p.get("asset_id") is not None
        }
        for i in ml_idx:
            labels[i] = by_id.get(int(rows[i]["asset_id"]))
    return artifacts.model_version, [str(x) for x in labels]


def _human_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    return {
        "n": len(y_true),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_weighted": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
        "kappa": round(float(cohen_kappa_score(y_true, y_pred)), 4),
    }


def train_production_classifier(
    input_path: str = DEFAULT_INPUT,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    pipeline_version: str = "v3.1",
    consensus_floor: float = CONSENSUS_SOFT_FLOOR,
    test_size: float = TEST_SIZE,
    calibrate: bool = True,
    promote_latest: bool = False,
    human_csv: list[str] | None = None,
    human_weight: float = 10.0,
    human_test_frac: float = 0.3,
    human_run_id: int = 6,
    human_test_csv: str | None = None,
    baseline_model_path: str | None = None,
) -> dict[str, Any]:
    """Train the production LinearSVC(+Platt) classifier and save the artifact.

    When ``human_csv`` is given, human-annotated rows are split into a held-out
    test set and a training augmentation (added to the gold with ``human_weight``
    sample weight). After saving, the new model and the baseline are evaluated on
    the SAME human test set via the production scoring path (before/after).
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Gold dataset introuvable: {input_file}")

    logger.info("Loading gold dataset: {}", input_file)
    df = pd.read_csv(input_file, low_memory=False)
    if TARGET not in df.columns:
        raise ValueError(f"Colonne cible '{TARGET}' absente du dataset.")

    # --- Gold filter (consensus >= floor) + sample weights ---
    if CONSENSUS_COL in df.columns:
        consensus = pd.to_numeric(df[CONSENSUS_COL], errors="coerce").fillna(0.0)
        gold = df[consensus >= consensus_floor].copy()
        weights = pd.to_numeric(gold[CONSENSUS_COL], errors="coerce").fillna(1.0).astype(np.float32).values
    else:
        logger.warning("Colonne '{}' absente — gold = tout le dataset, poids uniformes", CONSENSUS_COL)
        gold = df.copy()
        weights = np.ones(len(gold), dtype=np.float32)

    gold = gold.reset_index(drop=True)
    y_labels = gold[TARGET].astype(str).str.strip()
    logger.info("Gold size = {} (consensus >= {})", len(gold), consensus_floor)
    logger.info("Class distribution:\n{}", y_labels.value_counts().to_string())

    # Build row dicts from the FULL gold frame. The shared feature builders
    # (_build_numeric_values / _compose_text) read only the columns they need
    # (technical_name, source_ref, column_names_text, column_value_semantics_text
    # and the 12 NUM_COLS) and ignore the rest, so leak columns are never consumed.
    # CRITICAL: do NOT drop column_value_semantics_text — _build_numeric_values
    # derives the 38 semantic features from it. Dropping it would zero those
    # features at train time while inference computes them for real, causing a
    # train/inference mismatch (the notebook computes semantics BEFORE its drop).
    rows: list[dict[str, Any]] = gold.to_dict("records")
    names = _numeric_feature_order()

    # --- Optional human-label augmentation (active-learning corrections) ---
    human_train_rows: list[dict[str, Any]] = []
    human_train_labels: list[str] = []
    human_test_rows: list[dict[str, Any]] = []
    human_test_labels: list[str] = []
    if human_csv:
        hmap = _load_human_labels(human_csv)
        if human_test_csv:
            # Fixed held-out test from a dedicated CSV; excluded from training so
            # the same test set is fair for every compared model (none trained on it).
            tmap = _load_human_labels([human_test_csv])
            test_ids = set(tmap)
            train_map = {a: lbl for a, lbl in hmap.items() if a not in test_ids}
            feats = _fetch_feature_rows(list(set(train_map) | test_ids), human_run_id)
            human_train_rows = [feats[a] for a in train_map if a in feats]
            human_train_labels = [train_map[a] for a in train_map if a in feats]
            human_test_rows = [feats[a] for a in test_ids if a in feats]
            human_test_labels = [tmap[a] for a in test_ids if a in feats]
            logger.info("Human (fixed test CSV): {} train (weight={}) / {} test",
                        len(human_train_rows), human_weight, len(human_test_rows))
        else:
            feats = _fetch_feature_rows(list(hmap.keys()), human_run_id)
            hrows = [feats[a] for a in hmap if a in feats]
            hlabels = [hmap[a] for a in hmap if a in feats]
            logger.info("Human labels usable: {}/{} (features found in run {})",
                        len(hrows), len(hmap), human_run_id)
            if hrows:
                tr, te = train_test_split(
                    list(range(len(hrows))), test_size=human_test_frac,
                    random_state=RANDOM_STATE, stratify=hlabels,
                )
                human_train_rows = [hrows[i] for i in tr]
                human_train_labels = [hlabels[i] for i in tr]
                human_test_rows = [hrows[i] for i in te]
                human_test_labels = [hlabels[i] for i in te]
                logger.info("Human split: {} train (weight={}) / {} test",
                            len(human_train_rows), human_weight, len(human_test_rows))

    # Label encoder fitted on the UNION of gold + human labels
    label_encoder = LabelEncoder().fit(
        list(y_labels) + human_train_labels + human_test_labels
    )
    y_enc = label_encoder.transform(y_labels)
    logger.info("Classes ({}): {}", len(label_encoder.classes_), list(label_encoder.classes_))
    logger.info("Numeric feature count = {}", len(names))

    # --- Holdout validation (vectorizers fit on train only → no leakage) ---
    idx = np.arange(len(rows))
    idx_tr, idx_ho = train_test_split(
        idx, test_size=test_size, random_state=RANDOM_STATE, stratify=y_enc
    )
    rows_tr = [rows[i] for i in idx_tr]
    rows_ho = [rows[i] for i in idx_ho]
    y_tr, y_ho = y_enc[idx_tr], y_enc[idx_ho]
    w_tr = weights[idx_tr]

    logger.info("Holdout split: {} train / {} holdout", len(rows_tr), len(rows_ho))
    char_v, word_v, _, _ = _fit_char_word(rows_tr)
    num_scaler_v = StandardScaler(with_mean=False).fit(_numeric_matrix(rows_tr, names))
    ohe_v = _make_ohe().fit(_cat_frame(rows_tr))

    x_tr = _assemble(rows_tr, names, char_v, word_v, num_scaler_v, ohe_v)
    x_ho = _assemble(rows_ho, names, char_v, word_v, num_scaler_v, ohe_v)

    svc_val = LinearSVC(C=1.0, class_weight="balanced", random_state=RANDOM_STATE, max_iter=4000)
    svc_val.fit(x_tr, y_tr, sample_weight=w_tr)
    pred_ho = svc_val.predict(x_ho)
    macro_ho = float(f1_score(y_ho, pred_ho, average="macro"))
    weighted_ho = float(f1_score(y_ho, pred_ho, average="weighted"))
    logger.info("Holdout — macro-F1={:.4f} weighted-F1={:.4f}", macro_ho, weighted_ho)
    logger.info(
        "\n{}",
        classification_report(y_ho, pred_ho, target_names=list(label_encoder.classes_), digits=4),
    )

    # --- Final model: gold (+ human_train rows, up-weighted) ---
    final_rows = rows + human_train_rows
    final_y = label_encoder.transform(list(y_labels) + human_train_labels)
    final_w = np.concatenate([
        weights,
        np.full(len(human_train_rows), float(human_weight), dtype=np.float32),
    ])
    logger.info("Final training set: {} rows (gold {} + human_train {} @ weight {})",
                len(final_rows), len(rows), len(human_train_rows), human_weight)
    char_vec, word_vec, x_char, x_word = _fit_char_word(final_rows)
    num_scaler = StandardScaler(with_mean=False)
    x_num = csr_matrix(num_scaler.fit_transform(_numeric_matrix(final_rows, names)))
    ohe = _make_ohe()
    x_cat = ohe.fit_transform(_cat_frame(final_rows))
    x_full = hstack([x_char, x_word, x_num, x_cat]).tocsr()
    logger.info("Full feature matrix: {}", x_full.shape)

    svc = LinearSVC(C=1.0, class_weight="balanced", random_state=RANDOM_STATE, max_iter=4000)
    svc.fit(x_full, final_y, sample_weight=final_w)

    calibrated_model = None
    if calibrate:
        logger.info("Calibrating (Platt / sigmoid, cv=5)")
        calibrated_model = CalibratedClassifierCV(svc, cv=5, method="sigmoid")
        calibrated_model.fit(x_full, final_y, sample_weight=final_w)

    # --- Build artifact (byte-compatible with score_business_domain loader) ---
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    with input_file.open("rb") as handle:
        data_hash = hashlib.md5(handle.read()).hexdigest()[:12]

    cat_feat = list(ohe.get_feature_names_out(list(DEFAULT_CAT_COLS)))
    all_feat = (
        [f"char__{n}" for n in char_vec.get_feature_names_out()]
        + [f"word__{n}" for n in word_vec.get_feature_names_out()]
        + names + cat_feat
    )

    artifact: dict[str, Any] = {
        "pipeline_version": pipeline_version,
        "timestamp": timestamp,
        "data_hash": data_hash,
        "data_path": str(input_file),
        "gold_size": int(len(gold)),
        "gold_consensus_floor": consensus_floor,
        "holdout_macro_f1": macro_ho,
        "holdout_weighted_f1": weighted_ho,
        "model_type": "LinearSVC",
        "calibrated": bool(calibrate),
        "trained_by": "src.ml.train_production_classifier",
        "label_encoder": label_encoder,
        "char_vectorizer": char_vec,
        "word_vectorizer": word_vec,
        "one_hot_encoder": ohe,
        "num_scaler": num_scaler,
        "model": svc,
        "calibrated_model": calibrated_model,
        "config": {
            "TARGET": TARGET,
            "DROP_COLS": DROP_COLS,
            "DROPPED_TEXT_COLS": DROPPED_TEXT_COLS,
            "TEXT_COLS_CHAR": list(DEFAULT_TEXT_COLS_CHAR),
            "TEXT_COLS_WORD": list(DEFAULT_TEXT_COLS_WORD),
            "CAT_COLS": list(DEFAULT_CAT_COLS),
            "SQL_STOPWORDS": SQL_STOPWORDS,
            "KNOWN_SEMANTIC_LABELS": KNOWN_SEMANTIC_LABELS,
        },
        "feature_names": all_feat,
        "numeric_feature_names": names,
        "domain_keywords": DOMAIN_KEYWORDS,
        "ps_module_prefixes": PS_MODULE_PREFIXES,
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    versioned_path = out_dir / f"production_pipeline_{pipeline_version}_{timestamp}.joblib"
    joblib.dump(artifact, versioned_path, compress=3)
    logger.info("Saved versioned artifact: {}", versioned_path)

    latest_path = out_dir / "production_pipeline_latest.joblib"
    if promote_latest:
        joblib.dump(artifact, latest_path, compress=3)
        logger.info("Promoted to latest: {}", latest_path)
    else:
        logger.info("Not promoted (latest untouched). Use --promote-latest to deploy.")

    result: dict[str, Any] = {
        "artifact_path": str(versioned_path),
        "promoted_latest": bool(promote_latest),
        "model_version": f"{pipeline_version}_{timestamp}",
        "gold_size": int(len(gold)),
        "holdout_macro_f1": macro_ho,
        "holdout_weighted_f1": weighted_ho,
        "classes": list(label_encoder.classes_),
        "numeric_features": len(names),
        "total_features": len(all_feat),
    }

    # --- Human-test comparison: NEW model vs BASELINE on the SAME held-out human set ---
    if human_test_rows:
        ver_new, pred_new = _system_predict(human_test_rows, str(versioned_path))
        m_new = _human_metrics(human_test_labels, pred_new)
        logger.info("HUMAN TEST ({} rows) — NEW {}: {}", len(human_test_rows), ver_new, m_new)
        result["human_test_n"] = len(human_test_rows)
        result["human_test_new"] = m_new

        baseline = baseline_model_path or str(latest_path)
        if Path(baseline).exists():
            ver_base, pred_base = _system_predict(human_test_rows, baseline)
            m_base = _human_metrics(human_test_labels, pred_base)
            logger.info("HUMAN TEST ({} rows) — BASELINE {}: {}", len(human_test_rows), ver_base, m_base)
            result["human_test_baseline"] = m_base
        else:
            logger.warning("Baseline model not found for comparison: {}", baseline)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the production business-domain classifier (reproducible).")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Gold dataset CSV (v4).")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Artifact output directory.")
    parser.add_argument("--pipeline-version", default="v3.1", help="Pipeline version tag.")
    parser.add_argument("--consensus-floor", type=float, default=CONSENSUS_SOFT_FLOOR, help="Gold consensus threshold.")
    parser.add_argument("--test-size", type=float, default=TEST_SIZE, help="Holdout fraction.")
    parser.add_argument("--no-calibrate", action="store_true", help="Skip Platt calibration.")
    parser.add_argument("--promote-latest", action="store_true", help="Also overwrite production_pipeline_latest.joblib.")
    parser.add_argument("--human-csv", action="append", default=None,
                        help="Annotated human-label CSV (repeatable) to augment training + evaluate.")
    parser.add_argument("--human-weight", type=float, default=10.0,
                        help="sample_weight applied to human-labeled training rows.")
    parser.add_argument("--human-test-frac", type=float, default=0.3,
                        help="Fraction of human labels held out as a pure test set.")
    parser.add_argument("--human-run-id", type=int, default=6,
                        help="Run whose dataset_asset_ml provides the human rows' features.")
    parser.add_argument("--human-test-csv", default=None,
                        help="Fixed held-out test CSV (excluded from training; fair for all models).")
    parser.add_argument("--baseline-model-path", default=None,
                        help="Baseline artifact for the human-test comparison (default: latest).")
    args = parser.parse_args()

    configure_logging()
    result = train_production_classifier(
        input_path=args.input,
        output_dir=args.output_dir,
        pipeline_version=args.pipeline_version,
        consensus_floor=args.consensus_floor,
        test_size=args.test_size,
        calibrate=not args.no_calibrate,
        promote_latest=args.promote_latest,
        human_csv=args.human_csv,
        human_weight=args.human_weight,
        human_test_frac=args.human_test_frac,
        human_run_id=args.human_run_id,
        human_test_csv=args.human_test_csv,
        baseline_model_path=args.baseline_model_path,
    )
    logger.info("Training complete: {}", result)


if __name__ == "__main__":
    main()
