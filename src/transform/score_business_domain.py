"""Score business-domain predictions and persist them in serving schema."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, NamedTuple

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from scipy.sparse import csr_matrix, hstack, issparse
from sqlalchemy import text

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.ml.domain_term_base import DOMAIN_TERMS
from src.ml.domain_term_base import KEYWORD_TO_LABEL as _TERM_KEYWORD_TO_LABEL
from src.utils.logging_utils import configure_logging

DEFAULT_MODEL_PATH = "LLM/artifacts_business_domain/production_pipeline_latest.joblib"
INSERT_BATCH_SIZE = 1000
DEFAULT_CLOSE_TOP2_MARGIN = 0.05

# char n-grams: technical_name + source_ref concatenated
DEFAULT_TEXT_COLS_CHAR: tuple[str, ...] = (
    "technical_name",
    "source_ref",
)

# word n-grams: column_names_text only
DEFAULT_TEXT_COLS_WORD: tuple[str, ...] = ("column_names_text",)

# 12 raw numeric columns — no has_profile_data (that lives in CAT_COLS)
DEFAULT_NUMERIC_COLS: tuple[str, ...] = (
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

# OHE columns in exact training order
DEFAULT_CAT_COLS: tuple[str, ...] = (
    "source_system",
    "asset_type",
    "has_profile_data",
)

DELETE_SQL = "DELETE FROM serving.asset_business_domain_prediction WHERE run_id = :run_id"

READ_SQL = """
SELECT
    run_id,
    asset_id,
    source_system,
    asset_type,
    technical_name,
    source_ref,
    column_names_text,
    column_type_signature_text,
    column_value_semantics_text,
    field_count,
    nullable_field_count,
    non_nullable_field_count,
    numeric_field_count,
    date_field_count,
    text_field_count,
    large_text_field_count,
    avg_data_length,
    max_data_length,
    row_count,
    size_bytes,
    size_mb,
    has_profile_data
FROM processed.dataset_asset_ml
WHERE run_id = :run_id
  AND lower(coalesce(source_system, '')) IN ('oracle', 'peoplesoft')
ORDER BY asset_id
"""

INSERT_SQL = """
INSERT INTO serving.asset_business_domain_prediction (
    run_id,
    asset_id,
    business_domain_predicted,
    business_domain_alt,
    confidence,
    confidence_band,
    review_required,
    review_reason,
    model_version,
    scored_at
)
VALUES (
    :run_id,
    :asset_id,
    :business_domain_predicted,
    :business_domain_alt,
    :confidence,
    :confidence_band,
    :review_required,
    :review_reason,
    :model_version,
    :scored_at
)
"""

COUNT_SQL = (
    "SELECT COUNT(*) AS row_count "
    "FROM serving.asset_business_domain_prediction "
    "WHERE run_id = :run_id"
)

# ---------------------------------------------------------------------------
# Feature-engineering constants — must stay identical to the training notebook
# ---------------------------------------------------------------------------

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "finance": [
        "invoice", "payment", "ledger", "gl", "tax", "budget", "amount",
        "cost", "expense", "revenue", "accounting", "journal", "account",
        "ap", "ar", "fi", "glacct", "treasur", "asset", "deprec",
        "facture", "paiement", "comptabil", "compte", "montant", "devise",
        "currency", "vat", "tva",
    ],
    "hr": [
        "employee", "empl", "emplid", "job", "manager", "payroll", "absence",
        "position", "hire", "worker", "salary", "person", "headcount",
        "compensation", "benefit", "pay", "leave", "employe", "salaire",
        "poste", "conge",
    ],
    "it": [
        "user", "role", "access", "auth", "permission", "config", "server",
        "system", "login", "application", "security", "sysadm",
        "menu", "page", "xlat", "dbowner", "portal", "prcs", "audit",
    ],
    "procurement": [
        "vendor", "supplier", "purchase", "po_", "item", "stock", "inventory",
        "material", "order", "sourcing", "rfq", "contract",
        "fournisseur", "achat", "commande",
    ],
    "sales": [
        "customer", "client", "opportunity", "quote", "deal", "crm",
        "sales", "pipeline", "booking", "cust_", "cust",
        "vente", "facturation",
    ],
    "marketing": [
        "campaign", "lead", "segment", "channel", "audience", "click",
        "impression", "conversion", "promo",
    ],
    "risk": [
        "risk", "control", "incident", "compliance", "issue",
        "mitigation", "policy", "controle", "conformite",
    ],
    "supply_chain": [
        "shipment", "warehouse", "delivery", "route",
        "transport", "plant", "logistics", "bom", "prod_",
        "livraison", "entrepot", "logistique", "production",
    ],
}

# Production label names for each keyword domain key (must match ML model classes)
KEYWORD_TO_LABEL: dict[str, str] = {
    "finance":      "Finance & Contrôle",
    "hr":           "RH",
    "it":           "IT & Sécurité",
    "procurement":  "Achats & Fournisseurs",
    "sales":        "Ventes & Clients",
    "marketing":    "Ventes & Clients",
    "risk":         "Finance & Contrôle",
    "supply_chain": "Supply Chain / Logistique / Production",
}

_MIN_KEYWORD_HITS = 2           # minimum keyword count for a domain to qualify
_KEYWORD_DOMINANCE_RATIO = 3.0  # top domain must score >= N× the second-best
_KEYWORD_RULE_CONFIDENCE = 0.95 # fixed confidence assigned to keyword-classified rows

PS_MODULE_PREFIXES: dict[str, str] = {
    "GL": "finance", "AP": "finance", "AR": "finance", "AM": "finance",
    "BI": "finance", "TR": "finance", "EX": "finance",
    "HR": "hr", "JOB": "hr", "PERSON": "hr", "BEN": "hr", "PAY": "hr",
    "ABS": "hr", "COMP": "hr",
    "PO": "procurement", "EP": "procurement", "RFQ": "procurement",
    "CON": "procurement", "VND": "procurement",
    "IN": "supply_chain", "PL": "supply_chain", "SF": "supply_chain",
    "MG": "supply_chain", "PROD": "supply_chain",
    "SA": "sales", "OM": "sales", "CRM": "sales",
    "PRCS": "it", "PSAUTH": "it", "PSOPR": "it", "PSROLE": "it",
    "PT": "it", "PSMENU": "it",
}

# 31 semantic labels → 31 sem_* counts + 7 ratio_* = 38 numeric features
KNOWN_SEMANTIC_LABELS: list[str] = [
    "label", "quantity", "identifier", "financial_amount", "classification",
    "date_or_timestamp", "processing_identifier", "status",
    "reference_identifier", "percentage_or_rate", "user_identifier",
    "technical_timestamp", "flag", "date_part", "comment_text",
    "person_identifier", "job_label", "postal_location", "email_address",
    "phone_number", "url", "score", "duration", "technical_identifier",
    "person_full_name", "person_first_name", "person_last_name",
    "file_reference", "other", "geo_longitude", "geo_latitude",
]

_SEMANTIC_RATIO_LABELS: tuple[str, ...] = (
    "financial_amount", "person_identifier", "user_identifier",
    "quantity", "processing_identifier", "flag", "status",
)

# Pre-compiled keyword patterns (one per domain) — built once at import time
_DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    domain: re.compile(
        r"\b(" + "|".join(re.escape(k) for k in kws) + r")\b",
        flags=re.IGNORECASE,
    )
    for domain, kws in DOMAIN_KEYWORDS.items()
}

# Pre-compiled term patterns for keyword pre-classification (uses DOMAIN_TERMS,
# not DOMAIN_KEYWORDS, so the ML numeric features remain unaffected).
_TERM_PATTERNS: dict[str, re.Pattern[str]] = {
    domain: re.compile(
        r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b",
        flags=re.IGNORECASE,
    )
    for domain, terms in DOMAIN_TERMS.items()
}

# Sorted PS module keys (matches build_engineered_features in training notebook)
_SORTED_PS_MODS: tuple[str, ...] = tuple(sorted(PS_MODULE_PREFIXES))


class ScoringArtifacts(NamedTuple):
    """In-memory objects required to run inference."""

    model: Any
    model_key: str
    label_encoder: Any | None
    char_vectorizer: Any | None
    word_vectorizer: Any | None
    one_hot_encoder: Any | None
    num_scaler: Any | None
    config: dict[str, Any]
    text_cols_char: list[str]
    text_cols_word: list[str]
    numeric_feature_names: list[str]
    cat_columns: list[str]
    close_top2_margin: float
    model_version: str


# ---------------------------------------------------------------------------
# Feature-engineering helpers — identical to training notebook
# ---------------------------------------------------------------------------

def normalize_text(x: Any) -> str:
    """Lowercase, strip separators, collapse whitespace — mirrors training."""
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    x = str(x).lower()
    for sep in ["_", "-", "|", "/", "\\", ".", ":", ";", ",", "(", ")", "[", "]", "{", "}"]:
        x = x.replace(sep, " ")
    x = re.sub(r"[^a-z0-9\s]", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def safe_div(a: float, b: float) -> float:
    return 0.0 if b == 0.0 else a / b


def extract_prefix(tname: Any) -> str:
    if not isinstance(tname, str):
        return ""
    s = tname.upper()
    s = re.sub(r"^[A-Z]+\.", "", s)
    s = re.sub(r"^PS[_]?", "", s)
    m = re.match(r"([A-Z]+)_", s)
    return m.group(1) if m else s.split("_")[0][:6]


def _parse_semantic_counts(semantics_text: Any) -> Counter[str]:
    """Parse 'col:label|col:label|...' into a label-count Counter."""
    counts: Counter[str] = Counter()
    if semantics_text is None:
        return counts
    text = str(semantics_text).strip()
    if not text:
        return counts
    for pair in text.split("|"):
        pair = pair.strip()
        if ":" in pair:
            _, label = pair.split(":", 1)
            counts[label.strip().lower()] += 1
    return counts


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    return cleaned


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(converted) or np.isinf(converted):
        return default
    return converted


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, np.integer)):
        return int(value) != 0

    text_value = str(value).strip().lower()
    return text_value in {"1", "true", "t", "yes", "y"}


# ---------------------------------------------------------------------------
# Categorical normalization — keeps inference types aligned with OHE training
# ---------------------------------------------------------------------------

def _infer_ohe_column_dtype(cats: np.ndarray) -> type | None:
    """
    Return the Python type the OHE column expects, inferred from its stored categories.
    Handles numpy dtype shorthand and object arrays containing mixed Python types.
    """
    kind = cats.dtype.kind
    if kind == "b":
        return bool
    if kind in ("i", "u"):
        return int
    if kind == "f":
        return float
    if kind in ("U", "S"):
        return str

    # object array: inspect first non-null value
    for cat in cats:
        if cat is None:
            continue
        if isinstance(cat, float) and np.isnan(cat):
            continue
        if isinstance(cat, (bool, np.bool_)):
            return bool
        if isinstance(cat, str):
            return str
        if isinstance(cat, (int, np.integer)):
            return int
        return type(cat)

    return None


def _cast_to_dtype(value: Any, dtype: type) -> Any:
    """Cast a single value to dtype; returns a safe default when value is None."""
    if value is None:
        if dtype is str:
            return "missing"
        if dtype is bool:
            return False
        if dtype in (int, float):
            return dtype(0)
        return None

    if dtype is bool:
        return _safe_bool(value)
    if dtype is str:
        return str(value)
    if dtype is int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    try:
        return dtype(value)
    except (TypeError, ValueError):
        return value


def normalize_categoricals(
    cat_dict: dict[str, list[Any]],
    ohe: Any,
    cat_columns: list[str],
) -> pd.DataFrame:
    """
    Build a DataFrame for OneHotEncoder.transform() with every column cast to the
    exact Python type the encoder was fitted on.

    Root-cause fix for 'unseen labels: np.True_' and similar type-mismatch errors:
    the OHE stores categories as Python objects (e.g. Python bool True/False, or
    strings "True"/"False", or ints 0/1).  When inference passes a different type
    (numpy bool np.True_ instead of Python bool True, etc.) sklearn's internal
    unique-value check marks it as unseen.  Casting to the stored dtype removes the
    mismatch without touching the model artifact.
    """
    normalized: dict[str, list[Any]] = {}

    for col_idx, col_name in enumerate(cat_columns):
        raw_values = cat_dict[col_name]

        expected_dtype: type | None = None
        if hasattr(ohe, "categories_") and col_idx < len(ohe.categories_):
            expected_dtype = _infer_ohe_column_dtype(ohe.categories_[col_idx])

        if expected_dtype is None:
            normalized[col_name] = raw_values
        else:
            normalized[col_name] = [_cast_to_dtype(v, expected_dtype) for v in raw_values]

    return pd.DataFrame(normalized)


def _debug_ohe_columns(
    cat_df: pd.DataFrame,
    ohe: Any,
    cat_columns: list[str],
) -> None:
    """
    Debug helper: log unique inference values per OHE column and warn about any
    values that were not seen during training.

    Runs at DEBUG level (unique values) so it is silent in production by default,
    but WARNING is always emitted when unseen values are detected.
    """
    if not hasattr(ohe, "categories_"):
        return

    for col_idx, col_name in enumerate(cat_columns):
        if col_name not in cat_df.columns:
            continue

        observed = set(cat_df[col_name].dropna().unique().tolist())
        logger.debug(
            "OHE column '{}': unique values at inference = {}",
            col_name,
            observed,
        )

        if col_idx >= len(ohe.categories_):
            continue

        expected = set(ohe.categories_[col_idx].tolist())
        unseen = observed - expected
        if unseen:
            logger.warning(
                "OHE column '{}': {} unseen value(s) at inference: {} "
                "(training categories: {})",
                col_name,
                len(unseen),
                unseen,
                expected,
            )
            # NOTE: to silently zero-out unseen values instead of crashing,
            # the OHE can be re-fitted with handle_unknown="ignore".
            # Only do this if the business logic accepts treating unknown
            # categories as "no signal" (all-zero OHE row).


def _normalise_columns(columns: Sequence[Any]) -> list[str]:
    normalised: list[str] = []
    seen: set[str] = set()

    for column in columns:
        column_name = str(column).strip()
        if not column_name or column_name in seen:
            continue
        seen.add(column_name)
        normalised.append(column_name)

    return normalised


def _resolve_list_config(
    config: dict[str, Any],
    key: str,
    fallback: Sequence[str],
) -> list[str]:
    value = config.get(key)
    if isinstance(value, (list, tuple)):
        return _normalise_columns(value)
    return _normalise_columns(fallback)


def _resolve_model(artifact: dict[str, Any]) -> tuple[Any, str]:
    candidate_keys = (
        "calibrated_model",
        "model",
        "production_model",
        "lightgbm_model",
        "logreg_model",
        "linsvc_model",
    )

    for key in candidate_keys:
        model = artifact.get(key)
        if model is not None:
            return model, key

    raise KeyError(
        "No model object found in artifact. "
        "Expected one of: calibrated_model, model, production_model, "
        "lightgbm_model, logreg_model, linsvc_model."
    )


def _resolve_numeric_feature_names(
    artifact: dict[str, Any],
    config: dict[str, Any],
    num_scaler: Any | None,
) -> list[str]:
    if num_scaler is not None and hasattr(num_scaler, "feature_names_in_"):
        names = [str(name) for name in getattr(num_scaler, "feature_names_in_")]
        return _normalise_columns(names)

    artifact_numeric = artifact.get("numeric_feature_names")
    if isinstance(artifact_numeric, (list, tuple)):
        numeric_names = _normalise_columns(artifact_numeric)
    else:
        numeric_names = _resolve_list_config(config, "NUM_COLS", DEFAULT_NUMERIC_COLS)

    if not numeric_names:
        numeric_names = _normalise_columns(DEFAULT_NUMERIC_COLS)

    n_scaler_features = int(getattr(num_scaler, "n_features_in_", len(numeric_names)))
    if n_scaler_features <= 0:
        return numeric_names

    if len(numeric_names) < n_scaler_features:
        missing_count = n_scaler_features - len(numeric_names)
        for index in range(missing_count):
            numeric_names.append(f"numeric_feature_{index}")
    elif len(numeric_names) > n_scaler_features:
        numeric_names = numeric_names[:n_scaler_features]

    return numeric_names


def _resolve_cat_columns(
    artifact: dict[str, Any],
    config: dict[str, Any],
    one_hot_encoder: Any | None,
) -> list[str]:
    if one_hot_encoder is not None and hasattr(one_hot_encoder, "feature_names_in_"):
        names = [str(name) for name in getattr(one_hot_encoder, "feature_names_in_")]
        return _normalise_columns(names)

    configured = _resolve_list_config(config, "CAT_COLS", ())
    if configured:
        cat_columns = configured
    else:
        artifact_cat = artifact.get("cat_columns")
        if isinstance(artifact_cat, (list, tuple)):
            cat_columns = _normalise_columns(artifact_cat)
        else:
            cat_columns = _normalise_columns(DEFAULT_CAT_COLS)

    n_expected = int(getattr(one_hot_encoder, "n_features_in_", len(cat_columns)))
    if n_expected <= 0:
        return cat_columns

    if len(cat_columns) < n_expected:
        for index in range(n_expected - len(cat_columns)):
            cat_columns.append(f"cat_feature_{index}")
    elif len(cat_columns) > n_expected:
        cat_columns = cat_columns[:n_expected]

    return cat_columns


def _resolve_model_version(
    artifact: dict[str, Any],
    config: dict[str, Any],
    model_path: Path,
) -> str:
    config_keys = (
        "MODEL_VERSION",
        "model_version",
        "PIPELINE_VERSION",
        "pipeline_version",
        "version",
    )
    for key in config_keys:
        value = config.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    # Top-level artifact metadata — production_pipeline_*.joblib stores
    # pipeline_version (e.g. "v3.0") and timestamp (e.g. "20260421_110952").
    # Surfacing them yields a traceable model_version instead of the
    # uninformative file stem ("latest").
    pipeline_version = artifact.get("pipeline_version") or artifact.get("version")
    if pipeline_version is not None and str(pipeline_version).strip():
        resolved = str(pipeline_version).strip()
        timestamp = artifact.get("timestamp")
        if timestamp is not None and str(timestamp).strip():
            return f"{resolved}_{str(timestamp).strip()}"
        return resolved

    root_keys = ("production_model_name", "model_name")
    for key in root_keys:
        value = artifact.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    stem = model_path.stem
    if stem.startswith("production_pipeline_"):
        suffix = stem.replace("production_pipeline_", "", 1)
        if suffix:
            return suffix

    version_match = re.search(
        r"(v\d+(?:\.\d+)*(?:[_-]\d{8}(?:[_-]\d{6})?)?)",
        stem,
        flags=re.IGNORECASE,
    )
    if version_match:
        return version_match.group(1)

    return stem


def _load_scoring_artifacts(model_path: str) -> ScoringArtifacts:
    model_file = Path(model_path)
    if not model_file.exists():
        raise FileNotFoundError(f"Model artifact not found: {model_file}")

    loaded = joblib.load(model_file)
    if not isinstance(loaded, dict):
        raise TypeError(
            "Unsupported artifact format. "
            "Expected a dict containing preprocessors and model objects."
        )

    config = loaded.get("config")
    if not isinstance(config, dict):
        config = {}

    model, model_key = _resolve_model(loaded)
    label_encoder = loaded.get("label_encoder")
    char_vectorizer = loaded.get("char_vectorizer")
    word_vectorizer = loaded.get("word_vectorizer")
    one_hot_encoder = loaded.get("one_hot_encoder")
    num_scaler = loaded.get("num_scaler")

    text_cols_char = _resolve_list_config(config, "TEXT_COLS_CHAR", DEFAULT_TEXT_COLS_CHAR)
    text_cols_word = _resolve_list_config(config, "TEXT_COLS_WORD", DEFAULT_TEXT_COLS_WORD)
    numeric_feature_names = _resolve_numeric_feature_names(loaded, config, num_scaler)
    cat_columns = _resolve_cat_columns(loaded, config, one_hot_encoder)
    close_top2_margin = _safe_float(
        config.get("BORDERLINE_MARGIN_THRESHOLD"),
        default=DEFAULT_CLOSE_TOP2_MARGIN,
    )

    return ScoringArtifacts(
        model=model,
        model_key=model_key,
        label_encoder=label_encoder,
        char_vectorizer=char_vectorizer,
        word_vectorizer=word_vectorizer,
        one_hot_encoder=one_hot_encoder,
        num_scaler=num_scaler,
        config=config,
        text_cols_char=text_cols_char,
        text_cols_word=text_cols_word,
        numeric_feature_names=numeric_feature_names,
        cat_columns=cat_columns,
        close_top2_margin=close_top2_margin,
        model_version=_resolve_model_version(loaded, config, model_file),
    )


def _to_csr(matrix: Any) -> csr_matrix:
    if issparse(matrix):
        return matrix.tocsr()
    return csr_matrix(np.asarray(matrix, dtype=np.float32))


def _compose_text(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> list[str]:
    """Concatenate text columns with normalize_text — matches training preprocessing."""
    composed: list[str] = []
    for row in rows:
        parts = [normalize_text(row.get(column)) for column in columns]
        text_value = " ".join(part for part in parts if part)
        composed.append(text_value if text_value else "no_text")
    return composed


def _build_numeric_values(row: dict[str, Any]) -> dict[str, float]:
    """
    Compute ALL numeric features for one row in the exact order used during training:
    12 raw columns → engineered ratios/logs/shape → PS prefix indicators
    → domain keyword counts → 38 semantic features.
    """
    # --- raw base columns ---
    field_count = max(_safe_float(row.get("field_count")), 0.0)
    nullable_field_count = max(_safe_float(row.get("nullable_field_count")), 0.0)
    non_nullable_field_count = max(_safe_float(row.get("non_nullable_field_count")), 0.0)
    numeric_field_count = max(_safe_float(row.get("numeric_field_count")), 0.0)
    date_field_count = max(_safe_float(row.get("date_field_count")), 0.0)
    text_field_count = max(_safe_float(row.get("text_field_count")), 0.0)
    large_text_field_count = max(_safe_float(row.get("large_text_field_count")), 0.0)
    avg_data_length = max(_safe_float(row.get("avg_data_length")), 0.0)
    max_data_length = max(_safe_float(row.get("max_data_length")), 0.0)
    row_count = max(_safe_float(row.get("row_count")), 0.0)
    size_mb = max(_safe_float(row.get("size_mb")), 0.0)
    size_bytes = max(_safe_float(row.get("size_bytes"), default=size_mb * 1024.0 * 1024.0), 0.0)

    technical_name = str(row.get("technical_name") or "")
    source_ref = str(row.get("source_ref") or "")
    column_names_text = str(row.get("column_names_text") or "")

    # ALL text-derived engineered features (shape, PS prefix, keyword counts) are
    # computed on NORMALIZED text to mirror the training notebook exactly: it runs
    # build_engineered_features on prepare_dataframe()-normalized columns. Using raw
    # text here desynchronises inference from training (underscores break the \b
    # keyword matching, and shape/prefix values differ), which silently corrupts the
    # numeric block fed to the model. normalize_text lowercases and turns separators
    # into spaces.
    technical_name_n = normalize_text(technical_name)
    source_ref_n = normalize_text(source_ref)
    column_names_text_n = normalize_text(column_names_text)

    values: dict[str, float] = {
        # 12 raw columns
        "field_count": field_count,
        "nullable_field_count": nullable_field_count,
        "non_nullable_field_count": non_nullable_field_count,
        "numeric_field_count": numeric_field_count,
        "date_field_count": date_field_count,
        "text_field_count": text_field_count,
        "large_text_field_count": large_text_field_count,
        "avg_data_length": avg_data_length,
        "max_data_length": max_data_length,
        "row_count": row_count,
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        # ratio features
        "ratio_numeric": safe_div(numeric_field_count, field_count),
        "ratio_date": safe_div(date_field_count, field_count),
        "ratio_text": safe_div(text_field_count, field_count),
        "ratio_large_text": safe_div(large_text_field_count, field_count),
        "ratio_nullable": safe_div(nullable_field_count, field_count),
        "ratio_non_nullable": safe_div(non_nullable_field_count, field_count),
        # log features
        "log_row_count": float(np.log1p(row_count)),
        "log_size_bytes": float(np.log1p(size_bytes)),
        "log_size_mb": float(np.log1p(size_mb)),
        "log_avg_data_length": float(np.log1p(avg_data_length)),
        "log_max_data_length": float(np.log1p(max_data_length)),
        # size per field
        "avg_size_per_field": safe_div(size_bytes, max(field_count, 1.0)),
    }

    # shape features for technical_name and source_ref (on normalized text)
    for prefix_name, text_val in (("technical_name", technical_name_n), ("source_ref", source_ref_n)):
        text_len = len(text_val)
        total_len = max(text_len, 1)
        values[f"{prefix_name}_len"] = float(text_len)
        values[f"{prefix_name}_token_count"] = float(len(re.findall(r"[A-Za-z0-9]+", text_val)))
        values[f"{prefix_name}_digit_count"] = float(len(re.findall(r"\d", text_val)))
        values[f"{prefix_name}_underscore_count"] = float(text_val.count("_"))
        values[f"{prefix_name}_upper_ratio"] = sum(1.0 for c in text_val if c.isupper()) / total_len
        values[f"{prefix_name}_has_id"] = 1.0 if re.search(r"id", text_val, re.IGNORECASE) else 0.0
        values[f"{prefix_name}_has_dt"] = 1.0 if re.search(r"dt|date", text_val, re.IGNORECASE) else 0.0
        values[f"{prefix_name}_has_amt"] = 1.0 if re.search(r"amt|amount", text_val, re.IGNORECASE) else 0.0
        values[f"{prefix_name}_has_cd"] = 1.0 if re.search(r"cd|code", text_val, re.IGNORECASE) else 0.0

    # PS module prefix indicators (sorted keys — matches build_engineered_features,
    # which applies extract_prefix to the normalized technical_name)
    prefix = extract_prefix(technical_name_n)
    for mod in _SORTED_PS_MODS:
        values[f"ps_is_{mod}"] = 1.0 if prefix == mod else 0.0

    # domain keyword counts — computed on NORMALIZED text so word-boundary (\b)
    # matching works. On raw text the underscores in PeopleSoft names (e.g.
    # PS_GL_ACCOUNT) are word characters, so \bgl\b never matches; normalize_text
    # turns separators into spaces and restores the intended keyword signal.
    # This also keeps the feature identical to how the training notebook computed
    # it (build_engineered_features runs on prepare_dataframe-normalized text),
    # eliminating the train/inference mismatch on the keyword block.
    combined = " ".join((technical_name_n, source_ref_n, column_names_text_n))
    for domain, pattern in _DOMAIN_PATTERNS.items():
        count = float(len(pattern.findall(combined)))
        values[f"{domain}_keyword_count"] = count
        values[f"has_{domain}_keyword"] = 1.0 if count > 0 else 0.0

    # 38 semantic features from column_value_semantics_text
    sem_counts = _parse_semantic_counts(row.get("column_value_semantics_text"))
    total_sem = max(float(sum(sem_counts.values())), 1.0)
    for label in KNOWN_SEMANTIC_LABELS:
        values[f"sem_{label}"] = float(sem_counts.get(label, 0))
    for label in _SEMANTIC_RATIO_LABELS:
        values[f"ratio_{label}"] = values.get(f"sem_{label}", 0.0) / total_sem

    return values


def _build_feature_matrix(
    rows: Sequence[dict[str, Any]],
    artifacts: ScoringArtifacts,
) -> csr_matrix:
    blocks: list[csr_matrix] = []

    if artifacts.char_vectorizer is not None:
        char_text = _compose_text(rows, artifacts.text_cols_char)
        blocks.append(_to_csr(artifacts.char_vectorizer.transform(char_text)))

    if artifacts.word_vectorizer is not None:
        word_text = _compose_text(rows, artifacts.text_cols_word)
        blocks.append(_to_csr(artifacts.word_vectorizer.transform(word_text)))

    if artifacts.numeric_feature_names:
        numeric_array = np.zeros(
            (len(rows), len(artifacts.numeric_feature_names)),
            dtype=np.float32,
        )
        for row_index, row in enumerate(rows):
            numeric_values = _build_numeric_values(row)
            for column_index, column_name in enumerate(artifacts.numeric_feature_names):
                numeric_array[row_index, column_index] = np.float32(
                    numeric_values.get(column_name, 0.0)
                )

        if artifacts.num_scaler is not None:
            scaled = artifacts.num_scaler.transform(numeric_array)
            blocks.append(_to_csr(scaled))
        else:
            blocks.append(csr_matrix(numeric_array))

    # OHE must receive a named DataFrame whose column types match training exactly.
    # normalize_categoricals() inspects ohe.categories_ and casts each column to
    # the stored dtype — this is the root-cause fix for "unseen labels: np.True_".
    if artifacts.one_hot_encoder is not None and artifacts.cat_columns:
        cat_dict: dict[str, list[Any]] = {
            col: [row.get(col) for row in rows]
            for col in artifacts.cat_columns
        }
        cat_df = normalize_categoricals(
            cat_dict, artifacts.one_hot_encoder, artifacts.cat_columns
        )
        _debug_ohe_columns(cat_df, artifacts.one_hot_encoder, artifacts.cat_columns)
        blocks.append(_to_csr(artifacts.one_hot_encoder.transform(cat_df)))

    if not blocks:
        raise ValueError("No feature block could be built from artifact and source data.")

    if len(blocks) == 1:
        return blocks[0].tocsr()

    return hstack(blocks, format="csr")


# ---------------------------------------------------------------------------
# Keyword pre-classification — fast path before ML inference
# ---------------------------------------------------------------------------

def _keyword_classify(
    row: dict[str, Any],
) -> tuple[str, str | None, float] | None:
    """
    Attempt to classify a row by keyword matching alone.
    Returns (predicted_label, alt_label, confidence) when one domain clearly
    dominates, or None when the signal is ambiguous (row goes to ML).

    Uses DOMAIN_TERMS (_TERM_PATTERNS) — separate from DOMAIN_KEYWORDS which
    feeds ML numeric features. Also searches column_value_semantics_text for
    semantic label signals (e.g. "financial_amount", "person_identifier").
    """
    technical_name = str(row.get("technical_name") or "")
    source_ref = str(row.get("source_ref") or "")
    column_names_text = str(row.get("column_names_text") or "")
    semantics_text = str(row.get("column_value_semantics_text") or "")
    combined = (
        f"{technical_name} {source_ref} {column_names_text} {semantics_text}"
    ).lower()

    hits: dict[str, int] = {}
    for domain, pattern in _TERM_PATTERNS.items():
        count = len(pattern.findall(combined))
        if count > 0:
            hits[domain] = count

    if not hits:
        return None

    sorted_hits = sorted(hits.items(), key=lambda x: x[1], reverse=True)
    top_domain, top_count = sorted_hits[0]

    if top_count < _MIN_KEYWORD_HITS:
        return None

    if len(sorted_hits) > 1:
        _, second_count = sorted_hits[1]
        if top_count < _KEYWORD_DOMINANCE_RATIO * second_count:
            return None

    label = _TERM_KEYWORD_TO_LABEL.get(top_domain)
    if label is None:
        return None

    alt_label: str | None = None
    if len(sorted_hits) > 1:
        alt_label = _TERM_KEYWORD_TO_LABEL.get(sorted_hits[1][0])

    return label, alt_label, _KEYWORD_RULE_CONFIDENCE


def _decode_prediction_labels(
    predictions: Any,
    label_encoder: Any | None,
) -> np.ndarray:
    values = np.asarray(predictions)
    if values.ndim != 1:
        values = values.reshape(-1)

    if label_encoder is None:
        return values.astype(str)

    try:
        if np.issubdtype(values.dtype, np.number):
            decoded = label_encoder.inverse_transform(values.astype(int))
            return np.asarray(decoded, dtype=str)
    except Exception:
        logger.warning("Could not decode predictions via label_encoder; using raw labels.")

    return values.astype(str)


def _resolve_probability_labels(
    model: Any,
    label_encoder: Any | None,
    class_count: int,
) -> np.ndarray:
    if hasattr(model, "classes_"):
        classes = np.asarray(getattr(model, "classes_"))

        if label_encoder is not None:
            try:
                if np.issubdtype(classes.dtype, np.number):
                    decoded = label_encoder.inverse_transform(classes.astype(int))
                    return np.asarray(decoded, dtype=str)
            except Exception:
                logger.warning("Could not decode model.classes_ via label_encoder.")

        return classes.astype(str)

    if label_encoder is not None and hasattr(label_encoder, "classes_"):
        classes = np.asarray(getattr(label_encoder, "classes_"), dtype=str)
        if len(classes) == class_count:
            return classes

    return np.asarray([f"class_{index}" for index in range(class_count)], dtype=str)


def _predict_proba_matrix(model: Any, feature_matrix: csr_matrix) -> np.ndarray | None:
    if hasattr(model, "predict_proba"):
        probability_matrix = np.asarray(model.predict_proba(feature_matrix), dtype=np.float64)
        return probability_matrix

    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(feature_matrix), dtype=np.float64)
        if scores.ndim == 1:
            scores = np.column_stack((-scores, scores))

        scores = scores - np.max(scores, axis=1, keepdims=True)
        exp_scores = np.exp(scores)
        normaliser = np.sum(exp_scores, axis=1, keepdims=True)
        normaliser[normaliser == 0.0] = 1.0
        return exp_scores / normaliser

    return None


def _confidence_band(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.60:
        return "medium"
    return "low"


def _review_flags(
    predicted_label: str,
    confidence_band: str,
    top1_confidence: float | None,
    top2_confidence: float | None,
    close_top2_margin: float,
) -> tuple[bool, str | None]:
    reasons: list[str] = []

    if confidence_band == "low":
        reasons.append("low_model_confidence")

    if predicted_label.strip().lower() == "other":
        reasons.append("predicted_other")

    if top1_confidence is not None and top2_confidence is not None:
        if (top1_confidence - top2_confidence) <= close_top2_margin:
            reasons.append("close_top2_scores")

    if not reasons:
        return False, None

    return True, ",".join(reasons)


def _build_prediction_rows(
    rows: Sequence[dict[str, Any]],
    feature_matrix: csr_matrix,
    artifacts: ScoringArtifacts,
    run_id: int,
) -> list[dict[str, Any]]:
    prediction_rows: list[dict[str, Any]] = []

    probability_matrix = _predict_proba_matrix(artifacts.model, feature_matrix)
    scored_at = datetime.now(timezone.utc)

    if probability_matrix is not None and probability_matrix.shape[0] > 0:
        class_labels = _resolve_probability_labels(
            artifacts.model,
            artifacts.label_encoder,
            probability_matrix.shape[1],
        )

        ranked_indices = np.argsort(probability_matrix, axis=1)[:, ::-1]
        top1_indices = ranked_indices[:, 0]
        has_second_class = probability_matrix.shape[1] > 1
        top2_indices = ranked_indices[:, 1] if has_second_class else top1_indices

        top1_labels = class_labels[top1_indices]
        top2_labels = class_labels[top2_indices] if has_second_class else np.array([None] * len(rows))
        top1_scores = probability_matrix[np.arange(len(rows)), top1_indices]
        top2_scores = (
            probability_matrix[np.arange(len(rows)), top2_indices]
            if has_second_class
            else np.full(len(rows), np.nan, dtype=np.float64)
        )
    else:
        raw_predictions = artifacts.model.predict(feature_matrix)
        top1_labels = _decode_prediction_labels(raw_predictions, artifacts.label_encoder)
        top2_labels = np.array([None] * len(rows), dtype=object)
        top1_scores = np.full(len(rows), np.nan, dtype=np.float64)
        top2_scores = np.full(len(rows), np.nan, dtype=np.float64)

    for index, row in enumerate(rows):
        asset_id_raw = row.get("asset_id")
        if asset_id_raw is None:
            logger.warning("Skipping row with null asset_id for run_id={}", run_id)
            continue

        try:
            asset_id = int(asset_id_raw)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping row with non-integer asset_id={} for run_id={}",
                asset_id_raw,
                run_id,
            )
            continue

        predicted_label = str(top1_labels[index])

        top1_confidence = float(top1_scores[index]) if not np.isnan(top1_scores[index]) else None
        top2_confidence = float(top2_scores[index]) if not np.isnan(top2_scores[index]) else None
        band = _confidence_band(top1_confidence)

        raw_alt = top2_labels[index]
        alt_label = None
        if raw_alt is not None:
            alt_label = str(raw_alt)

        review_required, review_reason = _review_flags(
            predicted_label=predicted_label,
            confidence_band=band,
            top1_confidence=top1_confidence,
            top2_confidence=top2_confidence,
            close_top2_margin=artifacts.close_top2_margin,
        )

        prediction_rows.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "business_domain_predicted": predicted_label,
                "business_domain_alt": alt_label,
                "confidence": top1_confidence,
                "confidence_band": band,
                "review_required": review_required,
                "review_reason": review_reason,
                "model_version": artifacts.model_version,
                "scored_at": scored_at,
            }
        )

    return prediction_rows


def _build_keyword_prediction_rows(
    keyword_classified: list[tuple[dict[str, Any], str, str | None, float]],
    close_top2_margin: float,
    model_version: str,
    run_id: int,
) -> list[dict[str, Any]]:
    scored_at = datetime.now(timezone.utc)
    prediction_rows: list[dict[str, Any]] = []

    for row, label, alt_label, confidence in keyword_classified:
        asset_id_raw = row.get("asset_id")
        if asset_id_raw is None:
            logger.warning("Skipping keyword row with null asset_id for run_id={}", run_id)
            continue
        try:
            asset_id = int(asset_id_raw)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping keyword row with non-integer asset_id={} for run_id={}",
                asset_id_raw,
                run_id,
            )
            continue

        band = _confidence_band(confidence)
        review_required, review_reason = _review_flags(
            predicted_label=label,
            confidence_band=band,
            top1_confidence=confidence,
            top2_confidence=None,
            close_top2_margin=close_top2_margin,
        )
        prediction_rows.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "business_domain_predicted": label,
                "business_domain_alt": alt_label,
                "confidence": confidence,
                "confidence_band": band,
                "review_required": review_required,
                "review_reason": review_reason,
                "model_version": f"keyword_rule/{model_version}",
                "scored_at": scored_at,
            }
        )

    return prediction_rows


def _insert_predictions(
    postgres_client: PostgresClient,
    prediction_rows: Sequence[dict[str, Any]],
) -> None:
    if not prediction_rows:
        return

    with postgres_client.engine.begin() as connection:
        for start_index in range(0, len(prediction_rows), INSERT_BATCH_SIZE):
            batch = prediction_rows[start_index : start_index + INSERT_BATCH_SIZE]
            connection.execute(text(INSERT_SQL), list(batch))


def score_business_domain(run_id: int, model_path: str) -> int:
    """Score business-domain predictions for one run and persist them."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info(
            "Scoring serving.asset_business_domain_prediction for run_id={} using model_path={}",
            run_id,
            model_path,
        )

        logger.info("Step 1/7 - deleting existing predictions for run_id={}", run_id)
        postgres_client.execute(DELETE_SQL, {"run_id": run_id})

        logger.info("Step 2/7 - reading processed.dataset_asset_ml for run_id={}", run_id)
        source_rows = postgres_client.fetch_all(READ_SQL, {"run_id": run_id})
        logger.info("Read {} Oracle-only asset row(s) to score", len(source_rows))

        if not source_rows:
            logger.info("No source rows found for run_id={}. Nothing to score.", run_id)
            return 0

        logger.info("Step 3/7 - loading model artifact")
        artifacts = _load_scoring_artifacts(model_path=model_path)
        logger.info(
            "Artifact loaded with model={} and model_version={}",
            artifacts.model_key,
            artifacts.model_version,
        )

        logger.info("Step 4/7 - keyword pre-classification")
        keyword_classified: list[tuple[dict[str, Any], str, str | None, float]] = []
        ml_rows: list[dict[str, Any]] = []
        for row in source_rows:
            result = _keyword_classify(row)
            if result is not None:
                label, alt_label, confidence = result
                keyword_classified.append((row, label, alt_label, confidence))
            else:
                ml_rows.append(row)
        logger.info(
            "Keyword pre-classified: {} row(s), forwarded to ML: {} row(s)",
            len(keyword_classified),
            len(ml_rows),
        )

        all_prediction_rows: list[dict[str, Any]] = _build_keyword_prediction_rows(
            keyword_classified=keyword_classified,
            close_top2_margin=artifacts.close_top2_margin,
            model_version=artifacts.model_version,
            run_id=run_id,
        )

        if ml_rows:
            logger.info(
                "Step 5/7 - building inference feature matrix for {} ML row(s)",
                len(ml_rows),
            )
            feature_matrix = _build_feature_matrix(ml_rows, artifacts)

            logger.info("Step 6/7 - scoring ML predictions")
            ml_prediction_rows = _build_prediction_rows(
                rows=ml_rows,
                feature_matrix=feature_matrix,
                artifacts=artifacts,
                run_id=run_id,
            )
            all_prediction_rows.extend(ml_prediction_rows)
        else:
            logger.info("Steps 5-6/7 - skipped (all rows classified by keyword rule)")

        logger.info("Step 7/7 - inserting {} prediction row(s)", len(all_prediction_rows))
        _insert_predictions(postgres_client, all_prediction_rows)

        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0

        logger.info(
            "serving.asset_business_domain_prediction scored: {} row(s)",
            produced,
        )
        return produced

    except Exception:
        logger.exception(
            "Failed scoring serving.asset_business_domain_prediction for run_id={} using model_path={}",
            run_id,
            model_path,
        )
        raise


def main() -> None:
    """Score business-domain predictions from the command line.

    Usage:
        python -m src.transform.score_business_domain
        python -m src.transform.score_business_domain --run-id 5
        python -m src.transform.score_business_domain --run-id 5 \\
            --model-path LLM/artifacts_business_domain/production_pipeline_latest.joblib
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Score business-domain predictions for a pipeline run."
    )
    parser.add_argument(
        "--run-id",
        type=int,
        default=None,
        help="Pipeline run_id to score. Defaults to latest run_id in the DB.",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help=f"Path to the model artifact. Defaults to {DEFAULT_MODEL_PATH}.",
    )
    args = parser.parse_args()

    configure_logging()

    # Resolve run_id from DB when not supplied
    if args.run_id is None:
        from src.config.settings import get_settings
        from src.connectors.postgres_client import PostgresClient
        client = PostgresClient(settings=get_settings())
        row = client.fetch_one(
            "SELECT MAX(run_id) AS latest FROM processed.dataset_asset_ml", {}
        )
        run_id = int(row["latest"]) if row and row["latest"] else 1
        logger.info("No --run-id supplied, using latest: {}", run_id)
    else:
        run_id = args.run_id

    model_path = args.model_path or DEFAULT_MODEL_PATH

    count = score_business_domain(run_id=run_id, model_path=model_path)
    logger.info("Scoring complete. Predictions inserted: {}", count)


if __name__ == "__main__":
    main()
