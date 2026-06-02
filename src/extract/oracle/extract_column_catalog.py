"""Oracle extraction script for column catalog metadata.

This module extracts column-level metadata by mapping PeopleSoft records to
physical Oracle tables and enriching column data with PeopleSoft field
definitions. It is designed for V1 full-reload pipelines and returns a
``list[dict]`` without any write/load step.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging


def build_column_catalog_query(recname_prefix: str | None = None) -> str:
    """Build the SQL query used to extract Oracle/PeopleSoft column catalog.

    Args:
        recname_prefix: Optional first-character filter applied to
            ``m.recname``.

    Returns:
        SQL text for column catalog extraction.
    """
    prefix_filter = ""
    if recname_prefix is not None:
        prefix_filter = (
            "\nWHERE SUBSTR(m.recname, 1, LENGTH(:recname_prefix)) = :recname_prefix"
        )

    return f"""
WITH record_map AS (
    SELECT
        r.recname,
        CASE
            WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
                THEN TRIM(r.sqltablename)
            ELSE 'PS_' || r.recname
        END AS physical_table_name
    FROM SYSADM.PSRECDEFN r
    WHERE r.recname <> 'PSDUMMY'
)
SELECT
    m.recname,
    m.physical_table_name,
    c.column_id,
    c.column_name,
    c.data_type,
    c.data_length,
    c.data_precision,
    c.data_scale,
    c.nullable AS nullable_flag,
    c.num_distinct,
    c.num_nulls,
    c.histogram,
    rf.fieldnum,
    rf.useedit,
    NULLIF(TRIM(rf.recname_parent), ' ') AS recname_parent,
    df.fieldtype,
    df.length AS ps_field_length,
    df.decimalpos,
    DBMS_LOB.SUBSTR(df.descrlong, 4000, 1) AS field_descrlong
FROM record_map m
JOIN ALL_TAB_COLUMNS c
  ON c.owner = :owner
 AND c.table_name = m.physical_table_name
LEFT JOIN SYSADM.PSRECFIELDDB rf
  ON rf.recname = m.recname
 AND rf.fieldname = c.column_name
LEFT JOIN SYSADM.PSDBFIELD df
  ON df.fieldname = c.column_name
{prefix_filter}
ORDER BY m.recname, c.column_id
""".strip()


def compute_row_hash(record: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash for one extracted row.

    Args:
        record: One extracted row dictionary.

    Returns:
        SHA-256 hex digest generated from sorted-key JSON representation.
    """
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_column_catalog(
    owner: str | None = None,
    recname_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Extract Oracle/PeopleSoft column catalog metadata.

    Args:
        owner: Oracle schema owner used for ``ALL_TAB_COLUMNS``. If ``None``,
            ``settings.oracle_owner`` is used.
        recname_prefix: Optional leading character filter for ``recname``.
            When provided, only records whose ``recname`` starts with this
            prefix are extracted.

    Returns:
        List of normalized row dictionaries (lower-case keys) enriched with
        ``row_hash``.

    Raises:
        Exception: Propagates connector exceptions after logging.
    """
    settings = get_settings()
    effective_owner = (owner or settings.oracle_owner).upper().strip()
    effective_prefix = None if recname_prefix is None else recname_prefix.strip().upper()

    query = build_column_catalog_query(recname_prefix=effective_prefix)
    client = OracleClient(settings=settings)
    params: dict[str, Any] = {"owner": effective_owner}
    if effective_prefix is not None:
        params["recname_prefix"] = effective_prefix

    try:
        logger.info(
            "Starting Oracle column catalog extraction for owner={} prefix={}",
            effective_owner,
            effective_prefix or "ALL",
        )
        raw_rows = client.fetch_all(sql=query, params=params)

        extracted_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            normalized_row = {str(key).lower(): value for key, value in row.items()}
            normalized_row["row_hash"] = compute_row_hash(normalized_row)
            extracted_rows.append(normalized_row)

        logger.info(
            "Column catalog extraction completed for owner={} prefix={}: {} row(s) extracted",
            effective_owner,
            effective_prefix or "ALL",
            len(extracted_rows),
        )
        return extracted_rows

    except Exception:
        logger.exception(
            "Column catalog extraction failed for owner={} prefix={}",
            effective_owner,
            effective_prefix or "ALL",
        )
        raise


def main() -> None:
    """Run manual extraction for local validation."""
    configure_logging()
    rows = extract_column_catalog()
    logger.info("Manual run successful. Row count={}", len(rows))


if __name__ == "__main__":
    main()
