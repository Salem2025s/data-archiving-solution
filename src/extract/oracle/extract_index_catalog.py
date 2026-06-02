"""Oracle extraction script for PeopleSoft index catalog metadata.

This module extracts index definitions from PeopleSoft metadata tables
(`SYSADM.PSINDEXDEFN` and `SYSADM.PSKEYDEFN`) for V1 full-reload pipelines.
The output is a pure Python ``list[dict]`` with deterministic ``row_hash``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging


def build_index_catalog_query() -> str:
    """Build SQL query for PeopleSoft index catalog extraction.

    Returns:
        SQL query text.
    """
    return """
SELECT
    i.recname,
    i.indexid,
    i.uniqueflag AS uniqueness_flag,
    k.keyposn AS field_position,
    k.fieldname,
    k.ascdesc
FROM SYSADM.PSINDEXDEFN i
LEFT JOIN SYSADM.PSKEYDEFN k
       ON k.recname = i.recname
      AND k.indexid = i.indexid
ORDER BY i.recname, i.indexid, k.keyposn
""".strip()


def compute_row_hash(record: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash for one extracted row.

    Args:
        record: Row dictionary.

    Returns:
        SHA-256 hex digest.
    """
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_index_catalog() -> list[dict[str, Any]]:
    """Extract PeopleSoft index metadata.

    Returns:
        List of normalized rows (lower-case keys) with ``row_hash``.

    Raises:
        Exception: Propagates connector exceptions after logging.
    """
    settings = get_settings()
    query = build_index_catalog_query()
    client = OracleClient(settings=settings)

    try:
        logger.info("Starting Oracle index catalog extraction")
        raw_rows = client.fetch_all(sql=query)

        extracted_rows: list[dict[str, Any]] = []
        for row in raw_rows:
            normalized_row = {str(key).lower(): value for key, value in row.items()}
            normalized_row["row_hash"] = compute_row_hash(normalized_row)
            extracted_rows.append(normalized_row)

        logger.info(
            "Index catalog extraction completed: {} row(s) extracted",
            len(extracted_rows),
        )
        return extracted_rows

    except Exception:
        logger.exception("Index catalog extraction failed")
        raise


def main() -> None:
    """Run manual extraction for local validation."""
    configure_logging()
    rows = extract_index_catalog()
    logger.info("Manual run successful. Row count={}", len(rows))


if __name__ == "__main__":
    main()
