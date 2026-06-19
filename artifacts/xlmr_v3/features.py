"""Standalone, dependency-free feature builder for the XLM-R v1 domain classifier.

This file is VENDORED from the training project so the inference bundle has no
dependency on the repo or its DB connectors. It reproduces *byte-for-byte* the
129 numeric features and the input-text format used at training time. Parity is
verified at build time against the project's ``_build_numeric_values``.

Only depends on the standard library + numpy.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import numpy as np

# --- canonical 7 classes (exact order, indices 0..6) ------------------------
CLASS_LABELS: list[str] = [
    "Finance & Contrôle",
    "RH",
    "Achats & Fournisseurs",
    "Ventes & Clients",
    "Supply Chain / Logistique / Production",
    "IT & Sécurité",
    "Other",
]
REGULATED_LABELS: list[str] = CLASS_LABELS[:4]  # recall SLA >= 0.90

# ---------------------------------------------------------------------------
# Feature-engineering constants — identical to the training pipeline
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

_DOMAIN_PATTERNS: dict[str, "re.Pattern[str]"] = {
    domain: re.compile(
        r"\b(" + "|".join(re.escape(k) for k in kws) + r")\b",
        flags=re.IGNORECASE,
    )
    for domain, kws in DOMAIN_KEYWORDS.items()
}

_SORTED_PS_MODS: tuple[str, ...] = tuple(sorted(PS_MODULE_PREFIXES))


# ---------------------------------------------------------------------------
# Helpers — identical to the training pipeline
# ---------------------------------------------------------------------------
def normalize_text(x: Any) -> str:
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


def _parse_semantic_counts(semantics_text: Any) -> "Counter[str]":
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


# ---------------------------------------------------------------------------
# Input text + 129 numeric features
# ---------------------------------------------------------------------------
def build_input_text(row: dict) -> str:
    """Compose the tokenizer input (handles gold and human-eval column names).

    v3: appends the column type signature as a [TYPES] section (the model was
    trained with it). ``column_type_signature_text`` is present on real schema
    rows; if absent, the section is simply omitted.
    """
    name = str(row.get("technical_name") or "").strip()
    module = str(row.get("source_ref") or "").strip()
    cols = str(row.get("column_names_text") or row.get("column_names") or "").strip()
    sem = str(
        row.get("column_value_semantics_text") or row.get("column_semantics") or ""
    ).strip()
    text = f"[TABLE] {name} [MODULE] {module} [COLS] {cols[:400]} [SEM] {sem[:200]}"
    types = str(row.get("column_type_signature_text") or "").strip()
    if types:
        text += f" [TYPES] {types[:200]}"
    return text.strip()


def build_numeric_values(row: dict) -> dict[str, float]:
    """Compute ALL numeric features for one row, in the exact training order."""
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

    technical_name_n = normalize_text(technical_name)
    source_ref_n = normalize_text(source_ref)
    column_names_text_n = normalize_text(column_names_text)

    values: dict[str, float] = {
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
        "ratio_numeric": safe_div(numeric_field_count, field_count),
        "ratio_date": safe_div(date_field_count, field_count),
        "ratio_text": safe_div(text_field_count, field_count),
        "ratio_large_text": safe_div(large_text_field_count, field_count),
        "ratio_nullable": safe_div(nullable_field_count, field_count),
        "ratio_non_nullable": safe_div(non_nullable_field_count, field_count),
        "log_row_count": float(np.log1p(row_count)),
        "log_size_bytes": float(np.log1p(size_bytes)),
        "log_size_mb": float(np.log1p(size_mb)),
        "log_avg_data_length": float(np.log1p(avg_data_length)),
        "log_max_data_length": float(np.log1p(max_data_length)),
        "avg_size_per_field": safe_div(size_bytes, max(field_count, 1.0)),
    }

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

    prefix = extract_prefix(technical_name_n)
    for mod in _SORTED_PS_MODS:
        values[f"ps_is_{mod}"] = 1.0 if prefix == mod else 0.0

    combined = " ".join((technical_name_n, source_ref_n, column_names_text_n))
    for domain, pattern in _DOMAIN_PATTERNS.items():
        count = float(len(pattern.findall(combined)))
        values[f"{domain}_keyword_count"] = count
        values[f"has_{domain}_keyword"] = 1.0 if count > 0 else 0.0

    sem_counts = _parse_semantic_counts(row.get("column_value_semantics_text"))
    total_sem = max(float(sum(sem_counts.values())), 1.0)
    for label in KNOWN_SEMANTIC_LABELS:
        values[f"sem_{label}"] = float(sem_counts.get(label, 0))
    for label in _SEMANTIC_RATIO_LABELS:
        values[f"ratio_{label}"] = values.get(f"sem_{label}", 0.0) / total_sem

    return values


def numeric_feature_order() -> list[str]:
    """Stable 129-name order = keys produced by build_numeric_values (probe row)."""
    probe = {"technical_name": "", "source_ref": "", "column_names_text": ""}
    return list(build_numeric_values(probe).keys())


NUMERIC_FEATURE_NAMES: list[str] = numeric_feature_order()


def build_numeric_vector(row: dict, names: list[str] = NUMERIC_FEATURE_NAMES) -> np.ndarray:
    """Return the 129 raw (un-scaled) numeric features as float32, in order.

    A row WITHOUT schema metadata (no 'field_count') is treated as having no
    numeric features and gets a zero vector (matches training of human-eval
    rows). In production the real schema metrics should always be present.
    """
    has_numeric = ("field_count" in row) and (row.get("field_count") is not None)
    if not has_numeric:
        return np.zeros(len(names), dtype=np.float32)
    values = build_numeric_values(row)
    arr = np.zeros(len(names), dtype=np.float32)
    for j, name in enumerate(names):
        arr[j] = np.float32(values.get(name, 0.0))
    return arr
