"""Oracle extraction script for PeopleSoft record catalog mapping.

This module extracts PeopleSoft record metadata from Oracle and maps each
record to its physical Oracle table. It is designed for V1 full-reload
pipelines and returns pure Python structures (`list[dict]`) without any load
step.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging


def build_record_catalog_query() -> str:
    """Build the Oracle SQL query for record-to-physical-table mapping.

    Returns:
        SQL text used to extract PeopleSoft record catalog metadata.
    """
    return """
SELECT
    r.recname,
    r.recdescr,
    r.rectype,
    TRIM(r.sqltablename) AS sqltablename_raw,
    CASE
        WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
            THEN TRIM(r.sqltablename)
        ELSE 'PS_' || r.recname
    END AS physical_table_name,
    CASE
        WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
            THEN 'SQLTABLENAME'
        ELSE 'FALLBACK_PS_PREFIX'
    END AS mapping_source,
    t.owner AS oracle_owner,
    t.table_name AS oracle_table_name,
    CASE WHEN t.table_name IS NOT NULL THEN 1 ELSE 0 END AS table_exists_flag,
    NULLIF(TRIM(r.parentrecname), ' ') AS parentrecname
FROM SYSADM.PSRECDEFN r
LEFT JOIN ALL_TABLES t
       ON t.owner = :owner
      AND t.table_name = CASE
            WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
                THEN TRIM(r.sqltablename)
            ELSE 'PS_' || r.recname
          END
WHERE r.recname <> 'PSDUMMY'
ORDER BY r.recname
""".strip()


def compute_row_hash(record: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash for one extracted row.

    Hashing strategy:
    - serialize row as JSON
    - sort keys for deterministic order
    - keep unicode characters (`ensure_ascii=False`)
    - convert non-JSON-native values with `default=str`

    Args:
        record: One extracted row.

    Returns:
        Hex digest of SHA-256 for the normalized row JSON string.
    """
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_record_catalog(owner: str | None = None) -> list[dict[str, Any]]:
    """Extract PeopleSoft record catalog and Oracle table mapping.

    Args:
        owner: Oracle owner used in `ALL_TABLES` join.
            If ``None``, defaults to ``settings.oracle_owner``.

    Returns:
        List of extracted rows with lower-cased columns and an extra
        ``row_hash`` field.

    Raises:
        Exception: Propagates connector errors after logging.
    """
    settings = get_settings()
    effective_owner = (owner or settings.oracle_owner).upper().strip()

    query = build_record_catalog_query()
    client = OracleClient(settings=settings)

    try:
        logger.info(
            "Starting Oracle record catalog extraction for owner={}",
            effective_owner,
        )
        raw_rows = client.fetch_all(sql=query, params={"owner": effective_owner})

        extracted_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            normalized_row = {str(key).lower(): value for key, value in row.items()}
            row_hash = compute_row_hash(normalized_row)
            normalized_row["row_hash"] = row_hash
            extracted_rows.append(normalized_row)

        logger.info(
            "Record catalog extraction completed: {} row(s) extracted",
            len(extracted_rows),
        )
        return extracted_rows

    except Exception:
        logger.exception(
            "Record catalog extraction failed for owner={}.",
            effective_owner,
        )
        raise


def main() -> None:
    """Run a manual extraction of the record catalog.

    This function is intended for local smoke tests and can be reused by a
    scheduler or an orchestration flow wrapper.
    """
    configure_logging()
    rows = extract_record_catalog()
    logger.info("Manual run successful. Sample row count={}", len(rows))


if __name__ == "__main__":
    main()
