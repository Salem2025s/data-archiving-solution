"""Export `processed.dataset_asset_ml` rows to an annotable CSV file."""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

EXPORT_SQL = """
SELECT
    run_id,
    asset_id,
    source_system,
    asset_type,
    technical_name,
    source_ref,
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
    has_profile_data,
    column_names_text,
    column_type_signature_text,
    column_value_semantics_text
FROM processed.dataset_asset_ml
WHERE run_id = :run_id
ORDER BY source_system, asset_type, technical_name
"""

SAMPLED_EXPORT_SQL = """
WITH eligible AS (
    SELECT
        run_id,
        asset_id,
        source_system,
        asset_type,
        technical_name,
        source_ref,
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
        has_profile_data,
        column_names_text,
        column_type_signature_text,
        column_value_semantics_text
    FROM processed.dataset_asset_ml
    WHERE run_id = :run_id
      AND field_count > 0
),
strata AS (
    SELECT
        source_system,
        asset_type,
        COUNT(*)::integer AS stratum_size
    FROM eligible
    GROUP BY source_system, asset_type
),
strata_count AS (
    SELECT COUNT(*)::integer AS n_strata
    FROM strata
),
strata_target AS (
    SELECT
        s.source_system,
        s.asset_type,
        s.stratum_size,
        ROW_NUMBER() OVER (ORDER BY s.source_system, s.asset_type) AS strata_rank,
        CASE
            WHEN sc.n_strata > 0 THEN floor((:limit)::numeric / sc.n_strata)::integer
            ELSE 0
        END AS base_target,
        CASE
            WHEN sc.n_strata > 0 THEN mod(:limit, sc.n_strata)
            ELSE 0
        END AS remainder_target
    FROM strata s
    CROSS JOIN strata_count sc
),
strata_target_final AS (
    SELECT
        st.source_system,
        st.asset_type,
        least(
            st.stratum_size,
            st.base_target
            + CASE WHEN st.strata_rank <= st.remainder_target THEN 1 ELSE 0 END
        )::integer AS target_rows
    FROM strata_target st
),
ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.source_system, e.asset_type
            ORDER BY
                CASE WHEN coalesce(e.has_profile_data, false) THEN 0 ELSE 1 END,
                random()
        ) AS rn
    FROM eligible e
)
SELECT
    r.run_id,
    r.asset_id,
    r.source_system,
    r.asset_type,
    r.technical_name,
    r.source_ref,
    r.field_count,
    r.nullable_field_count,
    r.non_nullable_field_count,
    r.numeric_field_count,
    r.date_field_count,
    r.text_field_count,
    r.large_text_field_count,
    r.avg_data_length,
    r.max_data_length,
    r.row_count,
    r.size_bytes,
    r.size_mb,
    r.has_profile_data,
    r.column_names_text,
    r.column_type_signature_text,
    r.column_value_semantics_text
FROM ranked r
JOIN strata_target_final stf
  ON stf.source_system = r.source_system
 AND stf.asset_type = r.asset_type
WHERE r.rn <= stf.target_rows
ORDER BY r.source_system, r.asset_type, r.technical_name
LIMIT :limit
"""

SOURCE_COLUMNS: tuple[str, ...] = (
    "run_id",
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
    "column_names_text",
    "column_type_signature_text",
    "column_value_semantics_text",
)

EXPORT_COLUMNS: tuple[str, ...] = (
    *SOURCE_COLUMNS,
    "column_sample_values_text",
    "column_observed_pattern_text",
    "business_domain_label",
    "labeling_notes",
)

MAX_OBSERVED_ASSETS_PER_SAMPLED_EXPORT = 120
MAX_OBSERVED_COLUMNS_PER_ASSET = 24
MAX_COLUMN_SAMPLE_VALUES = 4
MAX_COLUMN_SCAN_ROWS = 4000
MAX_RENDERED_VALUE_LENGTH = 64

SAFE_ORACLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$#]+$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^(?:https?://|www\.)", re.IGNORECASE)
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}$"
)
PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().\-]{6,}$")
INTEGER_RE = re.compile(r"^[+\-]?\d+$")
DECIMAL_RE = re.compile(r"^[+\-]?\d+(?:[.,]\d+)?$")
SHORT_CODE_RE = re.compile(r"^[A-Z0-9_\-]{2,12}$")
ALPHANUMERIC_ID_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_\-]{6,}$")

DATE_PATTERNS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
)

TIMESTAMP_PATTERNS: tuple[str, ...] = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def _split_pipe_items(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item and item.strip()]


def _parse_column_map(value: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for token in _split_pipe_items(value):
        if ":" not in token:
            continue
        key, raw = token.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if key:
            parsed[key] = raw
    return parsed


def _normalize_text_value(raw: Any) -> str:
    text = str(raw).replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    text = text.replace("|", "/")
    if len(text) > MAX_RENDERED_VALUE_LENGTH:
        return text[: MAX_RENDERED_VALUE_LENGTH - 3] + "..."
    return text


def _normalize_name_for_matching(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _column_tokens(value: str) -> list[str]:
    normalized = _normalize_name_for_matching(value)
    if not normalized:
        return []
    return [token for token in normalized.split("_") if token]


def _token_set(value: str) -> set[str]:
    return set(_column_tokens(value))


def _has_any_token(name_lc: str, tokens: tuple[str, ...]) -> bool:
    normalized_name = _normalize_name_for_matching(name_lc)
    if not normalized_name:
        return False

    name_tokens = set(normalized_name.split("_"))
    for token in tokens:
        normalized_token = _normalize_name_for_matching(token)
        if not normalized_token:
            continue
        if "_" in normalized_token:
            if normalized_token in normalized_name:
                return True
            continue
        if normalized_token in name_tokens:
            return True
    return False


def _is_status_column(column_name: str) -> bool:
    tokens = _token_set(column_name)
    if "status" in tokens or "stat" in tokens:
        return True
    return "sts" in tokens and ("cd" in tokens or "flg" in tokens)


def _is_state_location_column(column_name: str) -> bool:
    tokens = _token_set(column_name)
    if "state" not in tokens:
        return False
    if _is_status_column(column_name):
        return False
    return bool(tokens.intersection({"address", "city", "country", "postal", "zip", "province", "county"}))


def _is_geo_latitude_column(column_name: str) -> bool:
    return _has_any_token(column_name, ("latitude", "lat"))


def _is_geo_longitude_column(column_name: str) -> bool:
    return _has_any_token(column_name, ("longitude", "lon", "lng"))


def _looks_like_date(value: str) -> bool:
    for pattern in DATE_PATTERNS:
        try:
            datetime.strptime(value, pattern)
            return True
        except ValueError:
            continue
    return False


def _looks_like_timestamp(value: str) -> bool:
    for pattern in TIMESTAMP_PATTERNS:
        try:
            datetime.strptime(value, pattern)
            return True
        except ValueError:
            continue
    return False


def _ratio(values: list[str], predicate: Any) -> float:
    if not values:
        return 0.0
    matched = 0
    for item in values:
        if predicate(item):
            matched += 1
    return matched / len(values)


def _is_binary_flag_values(values: list[str]) -> bool:
    if not values:
        return False
    normalized = {value.strip().upper() for value in values}
    allowed = {"Y", "N", "YES", "NO", "0", "1", "TRUE", "FALSE", "T", "F"}
    return normalized.issubset(allowed) and len(normalized) <= 2


def _infer_pattern_from_name_type(column_name: str, data_type: str | None) -> str:
    name_lc = column_name.lower()
    type_lc = (data_type or "").lower()

    if _has_any_token(name_lc, ("email", "mail")):
        return "email_like"
    if _has_any_token(name_lc, ("phone", "mobile", "tel")):
        return "phone_like"
    if _has_any_token(name_lc, ("url", "website", "link")):
        return "url_like"
    if _has_any_token(name_lc, ("uuid", "guid")):
        return "uuid_like"
    if _has_any_token(name_lc, ("created", "updated", "modified", "dttm", "timestamp")):
        return "timestamp_like"
    if _has_any_token(name_lc, ("date", "dt", "effdt", "asof")):
        return "date_like"
    if _is_status_column(name_lc):
        return "short_code_like"
    if _has_any_token(name_lc, ("code", "ref", "key")):
        return "short_code_like"
    if _has_any_token(name_lc, ("name", "descr", "label", "title")):
        return "name_like"

    if "timestamp" in type_lc:
        return "timestamp_like"
    if "date" in type_lc:
        return "date_like"
    if any(token in type_lc for token in ("number", "int", "decimal", "numeric", "float", "double")):
        return "decimal_like"
    if any(token in type_lc for token in ("char", "text", "clob")):
        return "short_code_like"
    return "free_text_like"


def _detect_observed_pattern(
    column_name: str,
    data_type: str | None,
    observed_values: list[str],
) -> str:
    if not observed_values:
        return _infer_pattern_from_name_type(column_name, data_type)

    uppercase_values = [value.upper() for value in observed_values]

    if _ratio(observed_values, lambda value: bool(EMAIL_RE.match(value))) >= 0.6:
        return "email_like"
    if _ratio(observed_values, lambda value: bool(URL_RE.match(value))) >= 0.6:
        return "url_like"
    if _ratio(observed_values, lambda value: bool(PHONE_RE.match(value))) >= 0.6:
        return "phone_like"
    if _ratio(observed_values, lambda value: bool(UUID_RE.match(value))) >= 0.6:
        return "uuid_like"
    if _ratio(observed_values, _looks_like_timestamp) >= 0.6:
        return "timestamp_like"
    if _ratio(observed_values, _looks_like_date) >= 0.6:
        return "date_like"
    if _is_binary_flag_values(observed_values):
        return "binary_flag_like"
    if _ratio(observed_values, lambda value: bool(INTEGER_RE.match(value))) >= 0.75:
        return "integer_like"
    if _ratio(
        observed_values,
        lambda value: bool(DECIMAL_RE.match(value.replace(" ", ""))),
    ) >= 0.75:
        return "decimal_like"
    if _ratio(observed_values, lambda value: bool(SHORT_CODE_RE.match(value))) >= 0.7:
        return "short_code_like"
    if _ratio(observed_values, lambda value: bool(ALPHANUMERIC_ID_RE.match(value))) >= 0.7:
        return "alphanumeric_identifier_like"

    avg_len = sum(len(value) for value in observed_values) / len(observed_values)
    spaced_ratio = _ratio(observed_values, lambda value: " " in value)
    if avg_len > 28 or spaced_ratio >= 0.7:
        if _ratio(observed_values, lambda value: value.istitle() and " " in value) >= 0.5:
            return "name_like"
        return "free_text_like"

    if _ratio(observed_values, lambda value: value.istitle()) >= 0.6:
        return "name_like"
    if _ratio(uppercase_values, lambda value: value in {"A", "B", "C", "D", "E"}) >= 0.7:
        return "short_code_like"

    return _infer_pattern_from_name_type(column_name, data_type)


def _semantic_from_observed(
    column_name: str,
    data_type: str | None,
    observed_values: list[str],
    pattern: str,
) -> str | None:
    name_lc = column_name.lower()

    if _is_geo_latitude_column(name_lc):
        return "geo_latitude"
    if _is_geo_longitude_column(name_lc):
        return "geo_longitude"
    if _has_any_token(name_lc, ("postal", "zipcode", "zip_code", "zip")):
        return "postal_location"
    if "state" in _token_set(name_lc) and not _is_status_column(name_lc):
        if _is_state_location_column(name_lc):
            return "location_text"
        return "other"

    if _has_any_token(name_lc, ("year", "month", "quarter", "week")):
        return "date_part"

    if pattern == "email_like":
        return "email_address"
    if pattern == "phone_like":
        return "phone_number"
    if pattern == "url_like":
        return "url"
    if pattern == "uuid_like":
        return "technical_identifier"
    if pattern == "binary_flag_like":
        return "flag"

    if pattern in {"timestamp_like", "date_like"}:
        if _has_any_token(name_lc, ("created", "updated", "modified", "dttm", "stamp", "load")):
            return "technical_timestamp"
        return "date_or_timestamp"

    if pattern in {"integer_like", "decimal_like"}:
        if _has_any_token(name_lc, ("duration", "delay", "elapsed", "age")):
            return "duration"
        if _has_any_token(name_lc, ("pct", "percent", "rate", "ratio")):
            return "percentage_or_rate"
        if _has_any_token(name_lc, ("score", "index")):
            return "score"
        if _has_any_token(
            name_lc,
            ("amt", "amount", "bal", "price", "cost", "revenue", "salary", "monetary"),
        ):
            return "financial_amount"
        if _has_any_token(name_lc, ("qty", "quantity", "count", "nbr", "num", "seq", "line", "rows")):
            return "quantity"

    if _is_status_column(name_lc):
        return "status"
    if _has_any_token(name_lc, ("type", "category", "class")):
        return "classification"
    if _has_any_token(name_lc, ("job", "role", "position")):
        return "job_label"
    if _has_any_token(name_lc, ("batch", "run", "process", "request", "workflow")):
        return "processing_identifier"

    if _has_any_token(name_lc, ("emplid", "employee", "staff")):
        return "person_identifier"
    if _has_any_token(name_lc, ("oprid", "userid", "user", "login", "account")):
        return "user_identifier"

    if _has_any_token(name_lc, ("firstname", "first_name", "given_name")):
        return "person_first_name"
    if _has_any_token(name_lc, ("lastname", "last_name", "surname")):
        return "person_last_name"
    if _has_any_token(name_lc, ("fullname", "full_name", "contact_name", "person_name")):
        return "person_full_name"

    if _has_any_token(name_lc, ("comment", "note", "remark", "message", "descrlong")):
        return "comment_text"
    if _has_any_token(name_lc, ("descr", "label", "title")):
        return "label"
    if _has_any_token(name_lc, ("name",)):
        return "label"

    if _has_any_token(name_lc, ("uuid", "guid")):
        return "technical_identifier"
    if _has_any_token(name_lc, ("ref", "code", "key")):
        return "reference_identifier"
    if name_lc == "id" or name_lc.endswith("_id") or name_lc.startswith("id_") or "identifier" in name_lc:
        return "identifier"

    type_lc = (data_type or "").lower()
    if "timestamp" in type_lc:
        return "date_or_timestamp"
    if "date" in type_lc:
        return "date_or_timestamp"

    if observed_values and pattern == "alphanumeric_identifier_like":
        return "identifier"
    if observed_values and pattern == "short_code_like":
        return "classification"

    return None


def _semantic_from_name_type(column_name: str, data_type: str | None) -> str:
    name_lc = column_name.lower()
    type_lc = (data_type or "").lower()

    if _has_any_token(name_lc, ("email", "mail")):
        return "email_address"
    if _has_any_token(name_lc, ("phone", "mobile", "tel")):
        return "phone_number"
    if _has_any_token(name_lc, ("url", "website", "link")):
        return "url"
    if _has_any_token(name_lc, ("uuid", "guid")):
        return "technical_identifier"
    if _is_status_column(name_lc):
        return "status"
    if _has_any_token(name_lc, ("type", "category", "class")):
        return "classification"
    if _has_any_token(name_lc, ("job", "role", "position")):
        return "job_label"
    if _has_any_token(name_lc, ("batch", "run", "process", "request", "workflow")):
        return "processing_identifier"
    if _has_any_token(name_lc, ("flag", "enabled", "active", "is_", "has_")):
        return "flag"
    if _has_any_token(name_lc, ("year", "month", "quarter", "week")):
        return "date_part"
    if _has_any_token(name_lc, ("created", "updated", "modified", "dttm", "stamp")):
        return "technical_timestamp"
    if _has_any_token(name_lc, ("duration", "delay", "elapsed", "age")):
        return "duration"
    if _has_any_token(name_lc, ("pct", "percent", "rate", "ratio")):
        return "percentage_or_rate"
    if _has_any_token(name_lc, ("score", "index")):
        return "score"
    if _has_any_token(
        name_lc,
        ("amt", "amount", "bal", "price", "cost", "revenue", "salary", "monetary"),
    ):
        return "financial_amount"
    if _has_any_token(name_lc, ("qty", "quantity", "count", "nbr", "num", "seq")):
        return "quantity"
    if _has_any_token(name_lc, ("postal", "zipcode", "zip_code", "zip")):
        return "postal_location"
    if _is_geo_latitude_column(name_lc):
        return "geo_latitude"
    if _is_geo_longitude_column(name_lc):
        return "geo_longitude"
    if _is_state_location_column(name_lc):
        return "location_text"
    if "state" in _token_set(name_lc) and not _is_status_column(name_lc):
        return "other"
    if _has_any_token(name_lc, ("emplid", "employee", "staff")):
        return "person_identifier"
    if _has_any_token(name_lc, ("oprid", "userid", "user", "login", "account")):
        return "user_identifier"
    if _has_any_token(name_lc, ("firstname", "first_name", "given_name")):
        return "person_first_name"
    if _has_any_token(name_lc, ("lastname", "last_name", "surname")):
        return "person_last_name"
    if _has_any_token(name_lc, ("fullname", "full_name", "contact_name", "person_name")):
        return "person_full_name"
    if _has_any_token(name_lc, ("comment", "note", "remark", "message", "descrlong")):
        return "comment_text"
    if _has_any_token(name_lc, ("descr", "label", "title")):
        return "label"
    if _has_any_token(name_lc, ("name",)):
        return "label"
    if _has_any_token(name_lc, ("ref", "code", "key")):
        return "reference_identifier"
    if name_lc == "id" or name_lc.endswith("_id") or name_lc.startswith("id_") or "identifier" in name_lc:
        return "identifier"

    if "timestamp" in type_lc:
        return "date_or_timestamp"
    if "date" in type_lc or "time" in type_lc:
        return "date_or_timestamp"
    if any(token in type_lc for token in ("number", "int", "decimal", "numeric", "float", "double")):
        return "quantity"
    if any(token in type_lc for token in ("char", "varchar", "text", "clob")):
        return "label"
    return "other"


def _is_safe_oracle_identifier(value: str | None) -> bool:
    if not value:
        return False
    return bool(SAFE_ORACLE_IDENTIFIER_RE.fullmatch(value.strip()))


def _split_owner_table(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    normalized = str(value).strip().upper()
    if "." not in normalized:
        return None
    owner, table = normalized.split(".", 1)
    if not owner or not table:
        return None
    if not (_is_safe_oracle_identifier(owner) and _is_safe_oracle_identifier(table)):
        return None
    return owner, table


def _quote_oracle_identifier(value: str) -> str:
    return f'"{value.upper()}"'


def _build_in_clause_params(
    column_name: str,
    param_prefix: str,
    values: list[int],
) -> tuple[str, dict[str, int]]:
    params: dict[str, int] = {}
    placeholders: list[str] = []
    for index, value in enumerate(values):
        key = f"{param_prefix}_{index}"
        placeholders.append(f":{key}")
        params[key] = int(value)
    return f"{column_name} IN ({', '.join(placeholders)})", params


def _fetch_asset_details(
    postgres_client: PostgresClient,
    run_id: int,
    asset_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not asset_ids:
        return {}

    in_clause, in_params = _build_in_clause_params("da.id", "asset_id", asset_ids)
    sql = f"""
SELECT
    da.id AS asset_id,
    da.source_system,
    da.asset_type,
    da.technical_name,
    da.source_ref,
    da.owner_name,
    tc.table_name AS oracle_table_exists,
    rc.table_exists_flag AS ps_table_exists_flag,
    rc.physical_table_name AS ps_physical_table_name,
    rc.oracle_owner AS ps_oracle_owner
FROM processed.dim_asset da
LEFT JOIN raw_oracle.table_catalog tc
  ON da.source_system = 'oracle'
 AND tc.run_id = da.run_id
 AND upper(tc.owner) = upper(da.owner_name)
 AND upper(tc.table_name) = upper(da.source_ref)
LEFT JOIN raw_oracle.record_catalog rc
  ON da.source_system = 'peoplesoft'
 AND rc.run_id = da.run_id
 AND upper(rc.recname) = upper(da.technical_name)
WHERE da.run_id = :run_id
  AND {in_clause}
"""
    params: dict[str, Any] = {"run_id": run_id, **in_params}
    rows = postgres_client.fetch_all(sql, params)
    return {int(row["asset_id"]): row for row in rows}


def _fetch_asset_columns(
    postgres_client: PostgresClient,
    run_id: int,
    asset_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    if not asset_ids:
        return {}

    in_clause, in_params = _build_in_clause_params("df.asset_id", "asset_col", asset_ids)
    sql = f"""
SELECT
    df.asset_id,
    df.technical_name AS column_name,
    df.data_type
FROM processed.dim_field df
WHERE df.run_id = :run_id
  AND {in_clause}
ORDER BY df.asset_id, df.technical_name
"""
    params: dict[str, Any] = {"run_id": run_id, **in_params}
    rows = postgres_client.fetch_all(sql, params)

    by_asset: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        asset_id = int(row["asset_id"])
        by_asset.setdefault(asset_id, []).append(row)
    return by_asset


def _resolve_oracle_object(
    asset_detail: dict[str, Any],
    default_oracle_owner: str,
) -> tuple[str, str] | None:
    source_system = str(asset_detail.get("source_system") or "").lower()

    if source_system == "oracle":
        by_technical = _split_owner_table(str(asset_detail.get("technical_name") or ""))
        if by_technical is not None:
            return by_technical

        owner = str(asset_detail.get("owner_name") or "").strip().upper() or default_oracle_owner
        table = str(asset_detail.get("source_ref") or "").strip().upper()

        if not (owner and table):
            return None
        if not (_is_safe_oracle_identifier(owner) and _is_safe_oracle_identifier(table)):
            return None
        return owner, table

    if source_system == "peoplesoft":
        owner = str(
            asset_detail.get("ps_oracle_owner") or asset_detail.get("owner_name") or ""
        ).strip().upper()
        table = str(
            asset_detail.get("ps_physical_table_name") or asset_detail.get("source_ref") or ""
        ).strip().upper()
        table_exists_flag = int(asset_detail.get("ps_table_exists_flag") or 0)
        if not (owner and table and table_exists_flag == 1):
            return None
        if not (_is_safe_oracle_identifier(owner) and _is_safe_oracle_identifier(table)):
            return None
        return owner, table

    return None


def _fetch_column_samples(
    oracle_client: OracleClient,
    owner: str,
    table_name: str,
    column_name: str,
    data_type: str | None,
) -> list[str]:
    if not _is_safe_oracle_identifier(column_name):
        return []

    quoted_owner = _quote_oracle_identifier(owner)
    quoted_table = _quote_oracle_identifier(table_name)
    quoted_column = _quote_oracle_identifier(column_name)
    source_table = f"{quoted_owner}.{quoted_table}"
    type_lc = (data_type or "").lower()

    if any(token in type_lc for token in ("blob", "bfile", "raw", "long raw")):
        return []

    if "clob" in type_lc:
        rendered_expr = f"DBMS_LOB.SUBSTR({quoted_column}, {MAX_RENDERED_VALUE_LENGTH}, 1)"
    elif "timestamp" in type_lc:
        rendered_expr = f"TO_CHAR({quoted_column}, 'YYYY-MM-DD\"T\"HH24:MI:SS')"
    elif "date" in type_lc:
        rendered_expr = f"TO_CHAR({quoted_column}, 'YYYY-MM-DD')"
    else:
        rendered_expr = f"TO_CHAR({quoted_column})"

        sql = f"""
SELECT sampled_value
FROM (
        SELECT sampled_value
        FROM (
                SELECT DISTINCT {rendered_expr} AS sampled_value
                FROM {source_table}
                WHERE {quoted_column} IS NOT NULL
                    AND ROWNUM <= :scan_limit
        ) distinct_values
        WHERE sampled_value IS NOT NULL
            AND LENGTH(TRIM(sampled_value)) > 0
        ORDER BY sampled_value
)
WHERE ROWNUM <= :sample_limit
"""

    rows = oracle_client.fetch_all(
        sql=sql,
        params={
            "scan_limit": MAX_COLUMN_SCAN_ROWS,
            "sample_limit": MAX_COLUMN_SAMPLE_VALUES,
        },
    )

    samples: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = row.get("sampled_value")
        if raw is None:
            continue
        normalized = _normalize_text_value(raw)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        samples.append(normalized)
        if len(samples) >= MAX_COLUMN_SAMPLE_VALUES:
            break

    return samples


def _build_observed_enrichment(
    run_id: int,
    rows: list[dict[str, Any]],
    settings: Any,
    postgres_client: PostgresClient,
    enable_observed_values: bool,
) -> tuple[dict[int, dict[str, dict[str, Any]]], dict[str, int]]:
    stats: dict[str, int] = {
        "sampled_assets_total": 0,
        "sampled_assets_oracle_table": 0,
        "sampled_assets_ps_record": 0,
        "assets_resolved_to_oracle_table": 0,
        "assets_unresolved": 0,
        "oracle_queries_attempted": 0,
        "oracle_queries_succeeded": 0,
        "oracle_queries_failed": 0,
        "columns_with_sample_values": 0,
        "rows_with_sample_values": 0,
    }

    if not enable_observed_values:
        logger.info(
            "Observed Oracle enrichment disabled for full export (limit=None): metadata-only mode"
        )
        return {}, stats

    candidate_asset_ids: list[int] = []
    seen_assets: set[int] = set()
    for row in rows:
        try:
            asset_id = int(row.get("asset_id"))
        except (TypeError, ValueError):
            continue
        if asset_id in seen_assets:
            continue
        source_system = str(row.get("source_system") or "").lower()
        field_count = int(row.get("field_count") or 0)
        if source_system not in {"oracle", "peoplesoft"}:
            continue
        if field_count <= 0:
            continue
        candidate_asset_ids.append(asset_id)
        seen_assets.add(asset_id)
        if len(candidate_asset_ids) >= MAX_OBSERVED_ASSETS_PER_SAMPLED_EXPORT:
            break

    stats["sampled_assets_total"] = len(candidate_asset_ids)

    if not candidate_asset_ids:
        return {}, stats

    asset_details = _fetch_asset_details(postgres_client, run_id, candidate_asset_ids)
    columns_by_asset = _fetch_asset_columns(postgres_client, run_id, candidate_asset_ids)

    for asset_id in candidate_asset_ids:
        asset_detail = asset_details.get(asset_id) or {}
        asset_type = str(asset_detail.get("asset_type") or "").lower()
        if asset_type == "oracle_table":
            stats["sampled_assets_oracle_table"] += 1
        elif asset_type == "ps_record":
            stats["sampled_assets_ps_record"] += 1

    default_oracle_owner = str(getattr(settings, "oracle_owner", "") or "").strip().upper()
    resolved_map: dict[int, tuple[str, str] | None] = {}
    for asset_id in candidate_asset_ids:
        asset_detail = asset_details.get(asset_id)
        if not asset_detail:
            resolved_map[asset_id] = None
            stats["assets_unresolved"] += 1
            continue
        resolved = _resolve_oracle_object(
            asset_detail=asset_detail,
            default_oracle_owner=default_oracle_owner,
        )
        resolved_map[asset_id] = resolved
        if resolved is None:
            stats["assets_unresolved"] += 1
        else:
            stats["assets_resolved_to_oracle_table"] += 1

    oracle_client = OracleClient(settings=settings)
    observed: dict[int, dict[str, dict[str, Any]]] = {}

    # Fast probe to avoid expensive per-column retries when Oracle is unreachable.
    try:
        oracle_client.fetch_one("SELECT 1 AS ping_ok FROM dual")
    except Exception:
        logger.warning("Oracle observed enrichment disabled: connectivity failed")
        for asset_id in candidate_asset_ids[:10]:
            asset_detail = asset_details.get(asset_id) or {}
            resolved = resolved_map.get(asset_id)
            resolved_table = "NONE" if resolved is None else f"{resolved[0]}.{resolved[1]}"
            logger.debug(
                "Observed enrichment asset debug | asset_id={} | asset_type={} | technical_name={} | source_ref={} | resolved_table={} | columns_tested=0 | columns_with_values=0",
                asset_id,
                asset_detail.get("asset_type"),
                asset_detail.get("technical_name"),
                asset_detail.get("source_ref"),
                resolved_table,
            )
        return observed, stats

    enriched_assets = 0
    debug_assets_logged = 0

    for asset_id in candidate_asset_ids:
        asset_detail = asset_details.get(asset_id)
        if not asset_detail:
            continue

        resolved = resolved_map.get(asset_id)
        if resolved is None:
            if debug_assets_logged < 10:
                logger.debug(
                    "Observed enrichment asset debug | asset_id={} | asset_type={} | technical_name={} | source_ref={} | resolved_table=NONE | columns_tested=0 | columns_with_values=0",
                    asset_id,
                    asset_detail.get("asset_type"),
                    asset_detail.get("technical_name"),
                    asset_detail.get("source_ref"),
                )
                debug_assets_logged += 1
            continue
        owner, table_name = resolved

        columns = columns_by_asset.get(asset_id, [])
        if not columns:
            if debug_assets_logged < 10:
                logger.debug(
                    "Observed enrichment asset debug | asset_id={} | asset_type={} | technical_name={} | source_ref={} | resolved_table={}.{} | columns_tested=0 | columns_with_values=0",
                    asset_id,
                    asset_detail.get("asset_type"),
                    asset_detail.get("technical_name"),
                    asset_detail.get("source_ref"),
                    owner,
                    table_name,
                )
                debug_assets_logged += 1
            continue

        sample_map: dict[str, list[str]] = {}
        pattern_map: dict[str, str] = {}
        semantic_map: dict[str, str] = {}
        columns_tested = 0
        columns_with_values = 0

        for column in columns[:MAX_OBSERVED_COLUMNS_PER_ASSET]:
            column_name = str(column.get("column_name") or "").strip()
            if not column_name:
                continue
            columns_tested += 1
            stats["oracle_queries_attempted"] += 1

            data_type = column.get("data_type")
            try:
                values = _fetch_column_samples(
                    oracle_client=oracle_client,
                    owner=owner,
                    table_name=table_name,
                    column_name=column_name,
                    data_type=str(data_type) if data_type is not None else None,
                )
                stats["oracle_queries_succeeded"] += 1
            except Exception:
                stats["oracle_queries_failed"] += 1
                logger.debug(
                    "Oracle sample read failed for {}.{}.{}",
                    owner,
                    table_name,
                    column_name,
                )
                continue

            if not values:
                continue

            columns_with_values += 1
            stats["columns_with_sample_values"] += 1

            pattern = _detect_observed_pattern(
                column_name=column_name,
                data_type=str(data_type) if data_type is not None else None,
                observed_values=values,
            )
            semantic = _semantic_from_observed(
                column_name=column_name,
                data_type=str(data_type) if data_type is not None else None,
                observed_values=values,
                pattern=pattern,
            )

            sample_map[column_name] = values
            pattern_map[column_name] = pattern
            if semantic:
                semantic_map[column_name] = semantic

        if sample_map:
            observed[asset_id] = {
                "samples": sample_map,
                "patterns": pattern_map,
                "semantics": semantic_map,
            }
            enriched_assets += 1

        if debug_assets_logged < 10:
            logger.debug(
                "Observed enrichment asset debug | asset_id={} | asset_type={} | technical_name={} | source_ref={} | resolved_table={}.{} | columns_tested={} | columns_with_values={}",
                asset_id,
                asset_detail.get("asset_type"),
                asset_detail.get("technical_name"),
                asset_detail.get("source_ref"),
                owner,
                table_name,
                columns_tested,
                columns_with_values,
            )
            debug_assets_logged += 1

    logger.info(
        "Observed Oracle enrichment completed: {} asset(s) with observed values",
        enriched_assets,
    )
    return observed, stats


def _ordered_columns(
    row: dict[str, Any],
    signature_map: dict[str, str],
    observed_map: dict[str, Any] | None,
) -> list[str]:
    ordered = _split_pipe_items(str(row.get("column_names_text") or ""))
    if ordered:
        return ordered

    if signature_map:
        return list(signature_map.keys())

    if observed_map:
        observed_samples = observed_map.get("samples") or {}
        return sorted(str(key) for key in observed_samples.keys())

    return []


def _build_enriched_row(
    row: dict[str, Any],
    observed_map: dict[str, Any] | None,
) -> dict[str, Any]:
    export_row = {column: row.get(column) for column in SOURCE_COLUMNS}

    signature_map = _parse_column_map(str(row.get("column_type_signature_text") or ""))
    metadata_semantics = _parse_column_map(str(row.get("column_value_semantics_text") or ""))
    columns = _ordered_columns(row, signature_map, observed_map)

    observed_samples_map = (observed_map or {}).get("samples", {})
    observed_patterns_map = (observed_map or {}).get("patterns", {})
    observed_semantics_map = (observed_map or {}).get("semantics", {})

    sample_parts: list[str] = []
    pattern_parts: list[str] = []
    semantic_parts: list[str] = []

    for column_name in columns:
        data_type = signature_map.get(column_name)
        values = observed_samples_map.get(column_name, [])

        if values:
            sample_parts.append(f"{column_name}:[{' | '.join(values)}]")

        if values:
            pattern = observed_patterns_map.get(column_name)
            if pattern:
                pattern_parts.append(f"{column_name}:{pattern}")

        observed_semantic = observed_semantics_map.get(column_name)
        if observed_semantic:
            final_semantic = observed_semantic
        else:
            fallback_semantic = _semantic_from_name_type(column_name, data_type)
            if fallback_semantic != "other":
                final_semantic = fallback_semantic
            else:
                metadata_semantic = metadata_semantics.get(column_name)
                final_semantic = metadata_semantic if metadata_semantic else "other"
        semantic_parts.append(f"{column_name}:{final_semantic or 'other'}")

    # PII masking (Phase 0 — safety): redact real values for columns whose semantic
    # is a PII category. The pattern/semantic signal is preserved for the LLM annotator;
    # only the raw sample values (which could contain real names, emails, IDs…) are
    # replaced with a placeholder. This prevents the labeling export from leaking real
    # personal data into annotation pipelines or third-party LLM endpoints.
    PII_SEMANTICS = frozenset({
        "email_address", "phone_number", "person_identifier", "person_first_name",
        "person_last_name", "person_full_name", "user_identifier", "postal_location",
        "geo_latitude", "geo_longitude",
    })
    masked_sample_parts: list[str] = []
    for part in sample_parts:
        col_name = part.split(":")[0].strip() if ":" in part else ""
        col_sem = observed_samples_map and next(
            (s for c, s in (observed_map or {}).get("semantics", {}).items() if c == col_name),
            None,
        )
        if col_sem in PII_SEMANTICS:
            masked_sample_parts.append(f"{col_name}:[*** masqué PII ***]")
        else:
            masked_sample_parts.append(part)

    export_row["column_sample_values_text"] = " | ".join(masked_sample_parts)
    export_row["column_observed_pattern_text"] = " | ".join(pattern_parts)

    if semantic_parts:
        export_row["column_value_semantics_text"] = " | ".join(semantic_parts)
    else:
        export_row["column_value_semantics_text"] = str(
            row.get("column_value_semantics_text") or ""
        )

    export_row["business_domain_label"] = ""
    export_row["labeling_notes"] = ""
    return export_row


def export_dataset_asset_ml_for_labeling(
    run_id: int,
    output_path: str | None = None,
    limit: int | None = None,
) -> str:
    """Export one run of `processed.dataset_asset_ml` to a labeling CSV."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    output_file = (
        Path(output_path)
        if output_path is not None
        else Path("exports") / f"dataset_asset_ml_run_{run_id}_for_labeling.csv"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)

    query = EXPORT_SQL
    params: dict[str, Any] = {"run_id": run_id}

    if limit is not None:
        query = SAMPLED_EXPORT_SQL
        params["limit"] = limit

    logger.info(
        "Starting dataset_asset_ml labeling export (run_id={}, limit={})",
        run_id,
        limit,
    )

    rows = postgres_client.fetch_all(query, params)

    observed_enrichment, observed_stats = _build_observed_enrichment(
        run_id=run_id,
        rows=rows,
        settings=settings,
        postgres_client=postgres_client,
        enable_observed_values=limit is not None,
    )

    export_rows: list[dict[str, Any]] = []
    for row in rows:
        try:
            asset_id = int(row.get("asset_id"))
        except (TypeError, ValueError):
            asset_id = -1
        observed_map = observed_enrichment.get(asset_id)
        export_row = _build_enriched_row(row=row, observed_map=observed_map)
        export_rows.append(export_row)

    observed_stats["rows_with_sample_values"] = sum(
        1
        for row in export_rows
        if str(row.get("column_sample_values_text") or "").strip()
    )

    with output_file.open(mode="w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(EXPORT_COLUMNS))
        writer.writeheader()
        writer.writerows(export_rows)

    logger.info("Exported {} row(s) to labeling CSV", len(export_rows))
    logger.info(
        "Observed enrichment stats | sampled_assets_total={} | sampled_assets_oracle_table={} | sampled_assets_ps_record={} | assets_resolved_to_oracle_table={} | assets_unresolved={} | oracle_queries_attempted={} | oracle_queries_succeeded={} | oracle_queries_failed={} | columns_with_sample_values={} | rows_with_sample_values={}",
        observed_stats.get("sampled_assets_total", 0),
        observed_stats.get("sampled_assets_oracle_table", 0),
        observed_stats.get("sampled_assets_ps_record", 0),
        observed_stats.get("assets_resolved_to_oracle_table", 0),
        observed_stats.get("assets_unresolved", 0),
        observed_stats.get("oracle_queries_attempted", 0),
        observed_stats.get("oracle_queries_succeeded", 0),
        observed_stats.get("oracle_queries_failed", 0),
        observed_stats.get("columns_with_sample_values", 0),
        observed_stats.get("rows_with_sample_values", 0),
    )
    logger.info("Generated file: {}", output_file)
    return str(output_file)


def main() -> None:
    """CLI entrypoint for dataset_asset_ml labeling export."""
    parser = argparse.ArgumentParser(
        description="Export processed.dataset_asset_ml to annotable CSV"
    )
    parser.add_argument("--run-id", type=int, required=True, help="Run ID to export")
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Optional output CSV path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of exported rows",
    )

    args = parser.parse_args()

    configure_logging()
    output_file = export_dataset_asset_ml_for_labeling(
        run_id=args.run_id,
        output_path=args.output_path,
        limit=args.limit,
    )
    logger.info("CSV export completed: {}", output_file)


if __name__ == "__main__":
    main()