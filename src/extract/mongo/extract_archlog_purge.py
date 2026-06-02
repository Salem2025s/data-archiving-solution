"""MongoDB extraction script for the `systnaps_archlog_purge` collection.

This module extracts documents from MongoDB (`DDTMdbDemo.systnaps_archlog_purge`)
and returns normalized rows as ``list[dict]`` for V1 full-reload pipelines.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from src.config.settings import get_settings
from src.connectors.mongo_client import MongoClientWrapper
from src.utils.logging_utils import configure_logging


def compute_row_hash(record: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash for one normalized row.

    Args:
        record: Normalized output row.

    Returns:
        SHA-256 hex digest built from sorted-key JSON serialization.
    """
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_archlog_purge() -> list[dict[str, Any]]:
    """Extract and normalize documents from ``systnaps_archlog_purge``.

    For each source document, this function returns:
    - source_doc_id
    - systnaps_archid
    - name_table
    - count_src
    - count_arch
    - count_csv
    - count_bad
    - count_temp
    - count_purge
    - base
    - campaign
    - time_save_csv
    - time_load_temp
    - time_purge
    - document_json
    - document_hash
    - row_hash

    Returns:
        List of normalized rows.

    Raises:
        Exception: Propagates connector errors after logging.
    """
    settings = get_settings()
    client = MongoClientWrapper(settings=settings)

    try:
        logger.info(
            "Starting extraction from Mongo collection={} in db={}",
            "systnaps_archlog_purge",
            settings.mongo_database_name,
        )

        documents = client.find_many(collection_name="systnaps_archlog_purge")
        rows: list[dict[str, Any]] = []

        for doc in documents:
            source_doc_id = str(doc["_id"])
            document_json: dict[str, Any] = dict(doc)

            document_hash_payload = json.dumps(
                document_json,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            )
            document_hash = hashlib.sha256(document_hash_payload.encode("utf-8")).hexdigest()

            row: dict[str, Any] = {
                "source_doc_id": source_doc_id,
                "systnaps_archid": doc.get("systnaps_archid"),
                "name_table": doc.get("name_table"),
                "count_src": doc.get("count_src"),
                "count_arch": doc.get("count_arch"),
                "count_csv": doc.get("count_csv"),
                "count_bad": doc.get("count_bad"),
                "count_temp": doc.get("count_temp"),
                "count_purge": doc.get("count_purge"),
                "base": doc.get("base"),
                "campaign": doc.get("campaign"),
                "time_save_csv": doc.get("time_save_csv"),
                "time_load_temp": doc.get("time_load_temp"),
                "time_purge": doc.get("time_purge"),
                "document_json": document_json,
                "document_hash": document_hash,
            }
            row["row_hash"] = compute_row_hash(row)
            rows.append(row)

        logger.info(
            "Extraction completed for systnaps_archlog_purge: {} row(s)",
            len(rows),
        )
        return rows

    except Exception:
        logger.exception("Extraction failed for Mongo collection systnaps_archlog_purge")
        raise
    finally:
        client.close()


def main() -> None:
    """Run manual extraction for local validation."""
    configure_logging()
    rows = extract_archlog_purge()
    logger.info("Manual run successful. Row count={}", len(rows))
    if rows:
        logger.info("First row sample: {}", rows[0])


if __name__ == "__main__":
    main()
