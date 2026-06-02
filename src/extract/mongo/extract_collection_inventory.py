"""MongoDB extraction script for collection inventory metadata.

This module extracts inventory-level metadata for every collection in the
configured MongoDB database. It is designed for V1 full-reload pipelines and
returns pure Python structures (``list[dict]``) without any load step.
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
    """Compute a deterministic SHA-256 hash for one extracted row.

    Args:
        record: One extracted row dictionary.

    Returns:
        SHA-256 hex digest based on a sorted-key JSON representation.
    """
    payload = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_collection_inventory() -> list[dict[str, Any]]:
    """Build collection inventory rows for all collections in the Mongo database.

    For each collection, this function gathers:
    - source_doc_id
    - collection_name
    - db_name
    - document_count
    - avg_obj_size_bytes
    - storage_size_bytes
    - total_index_size_bytes
    - sample_document
    - document_json
    - document_hash
    - row_hash

    Returns:
        Collection inventory as a list of dictionaries.

    Raises:
        Exception: Propagates connector errors after logging.
    """
    settings = get_settings()
    client = MongoClientWrapper(settings=settings)
    db_name = settings.mongo_database_name

    try:
        logger.info("Starting Mongo collection inventory build for db={}", db_name)

        collection_names = sorted(client.list_collection_names())
        rows: list[dict[str, Any]] = []

        for collection_name in collection_names:
            stats = client.get_collection_stats(collection_name)
            sample_document = client.find_one(collection_name=collection_name) or {}
            document_json = dict(sample_document)
            document_hash_payload = json.dumps(
                document_json,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            document_hash = hashlib.sha256(document_hash_payload.encode("utf-8")).hexdigest()

            row: dict[str, Any] = {
                "source_doc_id": f"{db_name}:{collection_name}",
                "collection_name": collection_name,
                "db_name": db_name,
                "document_count": stats.get("count", 0),
                "avg_obj_size_bytes": stats.get("avgObjSize", 0),
                # storage_size_bytes comes from MongoDB collStats: stats["storageSize"]
                "storage_size_bytes": stats.get("storageSize", 0),
                "total_index_size_bytes": stats.get("totalIndexSize", 0),
                "sample_document": sample_document,
                "document_json": document_json,
                "document_hash": document_hash,
            }
            row["row_hash"] = compute_row_hash(row)
            rows.append(row)

        logger.info(
            "Mongo collection inventory built successfully: {} collection(s)",
            len(rows),
        )
        return rows
    except Exception:
        logger.exception("Mongo collection inventory extraction failed for db={}", db_name)
        raise
    finally:
        client.close()


def extract_collection_inventory() -> list[dict[str, Any]]:
    """Extract collection inventory rows for the configured Mongo database.

    Returns:
        List of collection inventory rows.
    """
    rows = build_collection_inventory()
    logger.info("Collection inventory extraction completed: {} row(s)", len(rows))
    return rows


def main() -> None:
    """Run manual extraction of Mongo collection inventory."""
    configure_logging()
    rows = extract_collection_inventory()
    logger.info("Manual run successful. Row count={}", len(rows))


if __name__ == "__main__":
    main()
