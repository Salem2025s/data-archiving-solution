"""Column-based loader for Mongo raw datasets into PostgreSQL.

This module loads extracted Mongo rows (``list[dict]``) directly into
existing ``raw_mongo.*`` tables using actual columns (no generic JSON payload
model). Tables and schema are expected to already exist.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.connectors.postgres_client import PostgresClient

try:
    from bson import DBRef, ObjectId
except Exception:  # pragma: no cover - defensive fallback
    DBRef = None  # type: ignore[assignment]
    ObjectId = None  # type: ignore[assignment]

RAW_MONGO_SCHEMA = "raw_mongo"
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "collection_inventory",
        "metadatastable",
        "fields",
        "datalineage",
        "business_term",
        "glossary",
        "classification_definition",
        "archlog_purge",
        "project_catalog",
    }
)


class RawMongoLoader:
    """Loader for Mongo extraction outputs into ``raw_mongo`` tables."""

    def __init__(self, postgres_client: PostgresClient) -> None:
        self.postgres_client = postgres_client

    def _normalize_table_name(self, table_name: str) -> str:
        """Normalize and validate target table name.

        Accepts either ``metadatastable`` or ``raw_mongo.metadatastable``.

        Args:
            table_name: Logical target table name.

        Returns:
            Normalized table name (without schema).

        Raises:
            ValueError: If table name is not allowed.
        """
        normalized = table_name.strip().lower()
        if normalized.startswith(f"{RAW_MONGO_SCHEMA}."):
            normalized = normalized.split(".", maxsplit=1)[1]

        if normalized not in ALLOWED_TABLES:
            raise ValueError(
                f"Unsupported table_name '{table_name}'. "
                f"Allowed values: {sorted(ALLOWED_TABLES)}"
            )
        return normalized

    @staticmethod
    def _resolve_columns(rows: Sequence[dict[str, Any]]) -> list[str]:
        """Resolve insert columns from the first row.

        Args:
            rows: Source rows to insert.

        Returns:
            List of normalized columns to insert (excluding ``run_id``).

        Raises:
            ValueError: When no insertable columns are found.
        """
        first_row = rows[0]
        columns: list[str] = []
        for key in first_row.keys():
            col = str(key).lower().strip()
            if col and col != "run_id":
                columns.append(col)

        if not columns:
            raise ValueError("No insertable columns found in rows")
        return columns

    @staticmethod
    def to_jsonable(value: Any) -> Any:
        """Recursively convert values to JSON-compatible Python objects."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if ObjectId is not None and isinstance(value, ObjectId):
            return str(value)

        if DBRef is not None and isinstance(value, DBRef):
            return {
                "$ref": value.collection,
                "$id": RawMongoLoader.to_jsonable(value.id),
                "$db": value.database,
            }

        if isinstance(value, dict):
            return {
                str(key): RawMongoLoader.to_jsonable(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [RawMongoLoader.to_jsonable(item) for item in value]

        return str(value)

    @staticmethod
    def _is_json_column(column_name: str) -> bool:
        """Return True when column is expected to hold JSON payload text."""
        return column_name in {"sample_document", "document_json"} or column_name.endswith("_json")

    @staticmethod
    def _build_batch_params(
        rows: Sequence[dict[str, Any]],
        columns: Sequence[str],
        run_id: int,
    ) -> list[dict[str, Any]]:
        """Build SQLAlchemy parameter list for batch insert."""
        params: list[dict[str, Any]] = []
        for row in rows:
            param_row: dict[str, Any] = {"run_id": int(run_id)}
            for col in columns:
                value = row.get(col)
                if RawMongoLoader._is_json_column(col):
                    value = json.dumps(
                        RawMongoLoader.to_jsonable(value),
                        ensure_ascii=False,
                    )
                param_row[col] = value
            params.append(param_row)
        return params

    def insert_rows(self, table_name: str, rows: list[dict[str, Any]], run_id: int) -> int:
        """Insert rows into one ``raw_mongo`` table (column-based).

        Args:
            table_name: Logical target table name.
            rows: Extracted Mongo rows.
            run_id: Current pipeline run identifier, auto-inserted.

        Returns:
            Number of inserted rows.

        Raises:
            ValueError: On invalid table name or missing insert columns.
            SQLAlchemyError: On SQL execution failure.
        """
        target_table = self._normalize_table_name(table_name)

        if not rows:
            logger.info("No rows to load for raw_mongo.{}", target_table)
            return 0

        columns = self._resolve_columns(rows)
        insert_columns = ["run_id", *columns]

        column_sql = ", ".join(f'"{col}"' for col in insert_columns)
        values_sql = ", ".join(f":{col}" for col in insert_columns)
        sql = text(
            f'INSERT INTO "{RAW_MONGO_SCHEMA}"."{target_table}" ({column_sql}) '
            f"VALUES ({values_sql})"
        )

        params = self._build_batch_params(rows=rows, columns=columns, run_id=run_id)

        try:
            with self.postgres_client.engine.begin() as conn:
                conn.execute(sql, params)
            inserted = len(params)
            logger.info(
                "Loaded {} row(s) into raw_mongo.{} for run_id={}",
                inserted,
                target_table,
                run_id,
            )
            return inserted
        except SQLAlchemyError:
            logger.exception(
                "Failed loading rows into raw_mongo.{} for run_id={}",
                target_table,
                run_id,
            )
            raise

    def load_collection_inventory(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.collection_inventory``."""
        return self.insert_rows("collection_inventory", rows, run_id)

    def load_metadatastable(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.metadatastable``."""
        return self.insert_rows("metadatastable", rows, run_id)

    def load_fields(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.fields``."""
        return self.insert_rows("fields", rows, run_id)

    def load_datalineage(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.datalineage``."""
        return self.insert_rows("datalineage", rows, run_id)

    def load_business_term(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.business_term``."""
        return self.insert_rows("business_term", rows, run_id)

    def load_glossary(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.glossary``."""
        return self.insert_rows("glossary", rows, run_id)

    def load_classification_definition(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.classification_definition``."""
        return self.insert_rows("classification_definition", rows, run_id)

    def load_archlog_purge(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.archlog_purge``."""
        return self.insert_rows("archlog_purge", rows, run_id)

    def load_project_catalog(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_mongo.project_catalog``."""
        return self.insert_rows("project_catalog", rows, run_id)


def load_all_raw_mongo(
    loader: RawMongoLoader,
    run_id: int,
    collection_inventory_rows: Sequence[dict[str, Any]] | None = None,
    metadatastable_rows: Sequence[dict[str, Any]] | None = None,
    fields_rows: Sequence[dict[str, Any]] | None = None,
    datalineage_rows: Sequence[dict[str, Any]] | None = None,
    business_term_rows: Sequence[dict[str, Any]] | None = None,
    glossary_rows: Sequence[dict[str, Any]] | None = None,
    classification_definition_rows: Sequence[dict[str, Any]] | None = None,
    archlog_purge_rows: Sequence[dict[str, Any]] | None = None,
    project_catalog_rows: Sequence[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Load all Mongo raw datasets for one run.

    Args:
        loader: Initialized ``RawMongoLoader`` instance.
        run_id: Current run identifier.
        collection_inventory_rows: Rows for ``collection_inventory``.
        metadatastable_rows: Rows for ``metadatastable``.
        fields_rows: Rows for ``fields``.
        datalineage_rows: Rows for ``datalineage``.
        business_term_rows: Rows for ``business_term``.
        glossary_rows: Rows for ``glossary``.
        classification_definition_rows: Rows for ``classification_definition``.
        archlog_purge_rows: Rows for ``archlog_purge``.
        project_catalog_rows: Rows for ``project_catalog``.

    Returns:
        Per-table inserted row counts.
    """
    counts = {
        "collection_inventory": loader.load_collection_inventory(list(collection_inventory_rows or []), run_id),
        "metadatastable": loader.load_metadatastable(list(metadatastable_rows or []), run_id),
        "fields": loader.load_fields(list(fields_rows or []), run_id),
        "datalineage": loader.load_datalineage(list(datalineage_rows or []), run_id),
        "business_term": loader.load_business_term(list(business_term_rows or []), run_id),
        "glossary": loader.load_glossary(list(glossary_rows or []), run_id),
        "classification_definition": loader.load_classification_definition(
            list(classification_definition_rows or []),
            run_id,
        ),
        "archlog_purge": loader.load_archlog_purge(list(archlog_purge_rows or []), run_id),
        "project_catalog": loader.load_project_catalog(list(project_catalog_rows or []), run_id),
    }
    logger.info("Raw Mongo load completed for run_id={} with counts={}", run_id, counts)
    return counts
