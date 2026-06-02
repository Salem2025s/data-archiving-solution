"""Oracle extraction script for table catalog metadata.

This module extracts Oracle table catalog information from ``ALL_TABLES`` for a
specific owner (schema). It is designed for V1 full-reload pipelines and
returns rows as ``list[dict]`` without any write/load step.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging


def build_table_catalog_query() -> str:
    """Build the SQL query used to extract Oracle table catalog metadata.

    Returns:
        SQL query text for ``ALL_TABLES`` extraction.
    """
    return """
SELECT
    t.owner,
    t.table_name,
    t.tablespace_name,
    t.num_rows,
    t.blocks,
    t.avg_row_len,
    t.last_analyzed,
    m.last_modified,
    NVL(d.referenced_by_count, 0) AS referenced_by_count,
    t.temporary AS temporary_flag,
    t.partitioned AS partitioned_flag
FROM ALL_TABLES t
LEFT JOIN (
    SELECT table_owner, table_name, MAX(timestamp) AS last_modified
    FROM ALL_TAB_MODIFICATIONS
    GROUP BY table_owner, table_name
) m
  ON m.table_owner = t.owner
 AND m.table_name = t.table_name
LEFT JOIN (
    SELECT referenced_owner, referenced_name,
           COUNT(DISTINCT owner || '.' || name || '.' || type) AS referenced_by_count
    FROM ALL_DEPENDENCIES
    WHERE referenced_type = 'TABLE'
    GROUP BY referenced_owner, referenced_name
) d
  ON d.referenced_owner = t.owner
 AND d.referenced_name = t.table_name
WHERE t.owner = :owner
ORDER BY t.num_rows DESC NULLS LAST, t.table_name
""".strip()


def compute_row_hash(record: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash for one row.

    Args:
        record: One extracted row as a dictionary.

    Returns:
        SHA-256 hex digest based on a sorted-key JSON payload.
    """
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_table_catalog(owner: str | None = None) -> list[dict[str, Any]]:
    """Extract table catalog metadata from Oracle ``ALL_TABLES``.

    Args:
        owner: Oracle schema owner. If ``None``, ``settings.oracle_owner`` is
            used.

    Returns:
        List of normalized rows (lower-case keys) with an additional
        ``row_hash`` field.

    Raises:
        Exception: Propagates connector exceptions after logging.
    """
    settings = get_settings()
    effective_owner = (owner or settings.oracle_owner).upper().strip()

    query = build_table_catalog_query()
    client = OracleClient(settings=settings)

    try:
        logger.info(
            "Starting Oracle table catalog extraction for owner={}",
            effective_owner,
        )
        raw_rows = client.fetch_all(sql=query, params={"owner": effective_owner})

        extracted_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            normalized_row = {str(key).lower(): value for key, value in row.items()}
            normalized_row["row_hash"] = compute_row_hash(normalized_row)
            extracted_rows.append(normalized_row)

        logger.info(
            "Table catalog extraction completed: {} row(s) extracted",
            len(extracted_rows),
        )
        return extracted_rows

    except Exception:
        logger.exception(
            "Table catalog extraction failed for owner={}",
            effective_owner,
        )
        raise


def main() -> None:
    """Run manual extraction for local validation."""
    configure_logging()
    rows = extract_table_catalog()
    logger.info("Manual run successful. Row count={}", len(rows))


if __name__ == "__main__":
    main()
