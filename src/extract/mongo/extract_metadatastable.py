"""MongoDB extraction script for the `metadatastable` collection.

This module extracts documents from MongoDB (`DDTMdbDemo.metadatastable`) and
returns normalized rows as ``list[dict]`` for V1 full-reload pipelines.
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


def extract_metadatastable() -> list[dict[str, Any]]:
    """Extract and normalize documents from Mongo collection ``metadatastable``.

    For each source document, this function returns the following keys:
    - source_doc_id
    - name
    - object_md
    - module_md
    - status
    - effective_date
    - add_by
    - created_at
    - updated_at
    - updated_by
    - date_synch_md
    - columns_count
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
            "metadatastable",
            settings.mongo_database_name,
        )

        documents = client.find_many(collection_name="metadatastable")
        rows: list[dict[str, Any]] = []

        for doc in documents:
            source_doc_id = str(doc["_id"])
            document_json: dict[str, Any] = dict(doc)
            columns_count = len(doc.get("columns", []))

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
                "name": doc.get("name"),
                "object_md": doc.get("objectMD"),
                "module_md": doc.get("moduleMD"),
                "status": doc.get("status"),
                "effective_date": doc.get("effectiveDate"),
                "add_by": doc.get("addBy"),
                "created_at": doc.get("createdAt"),
                "updated_at": doc.get("updatedAt"),
                "updated_by": doc.get("updatedBy"),
                "date_synch_md": doc.get("dateSynchMD"),
                "columns_count": columns_count,
                "document_json": document_json,
                "document_hash": document_hash,
            }
            row["row_hash"] = compute_row_hash(row)
            rows.append(row)

        logger.info(
            "Extraction completed for metadatastable: {} row(s)",
            len(rows),
        )
        return rows

    except Exception:
        logger.exception("Extraction failed for Mongo collection metadatastable")
        raise
    finally:
        client.close()


def main() -> None:
    """Run manual extraction for local validation."""
    configure_logging()
    rows = extract_metadatastable()
    logger.info("Manual run successful. Row count={}", len(rows))


if __name__ == "__main__":
    main()
