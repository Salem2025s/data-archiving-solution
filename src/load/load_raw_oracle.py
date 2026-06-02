"""Column-based loader for Oracle raw datasets into PostgreSQL.

This module loads extracted Oracle rows (``list[dict]``) directly into the
existing ``raw_oracle.*`` tables using real columns (no JSON payload model).
Tables are assumed to already exist with the expected DDL.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.connectors.postgres_client import PostgresClient

RAW_ORACLE_SCHEMA = "raw_oracle"
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "record_catalog",
        "table_catalog",
        "column_catalog",
        "index_catalog",
    }
)


class RawOracleLoader:
    """Loader for Oracle extraction outputs into ``raw_oracle`` tables."""

    def __init__(self, postgres_client: PostgresClient) -> None:
        self.postgres_client = postgres_client

    def _normalize_table_name(self, table_name: str) -> str:
        """Normalize input table name and validate allowed targets.

        Accepts either ``record_catalog`` or ``raw_oracle.record_catalog``.
        """
        normalized = table_name.strip().lower()
        if normalized.startswith(f"{RAW_ORACLE_SCHEMA}."):
            normalized = normalized.split(".", maxsplit=1)[1]

        if normalized not in ALLOWED_TABLES:
            raise ValueError(
                f"Unsupported table_name '{table_name}'. "
                f"Allowed values: {sorted(ALLOWED_TABLES)}"
            )
        return normalized

    @staticmethod
    def _resolve_columns(rows: Sequence[dict[str, Any]]) -> list[str]:
        """Resolve insertion columns from the first row.

        Column names are lower-cased for consistency with extractors.
        The reserved ``run_id`` field is excluded because it is added
        automatically by the loader.
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
    def _build_batch_params(
        rows: Sequence[dict[str, Any]],
        columns: Sequence[str],
        run_id: int,
    ) -> list[dict[str, Any]]:
        """Build parameter list for SQLAlchemy batch insert."""
        params: list[dict[str, Any]] = []
        for row in rows:
            param_row: dict[str, Any] = {"run_id": int(run_id)}
            for col in columns:
                param_row[col] = row.get(col)
            params.append(param_row)
        return params

    def insert_rows(self, table_name: str, rows: list[dict[str, Any]], run_id: int) -> int:
        """Insert rows into one ``raw_oracle`` table (column-based).

        Args:
            table_name: Target logical table name.
            rows: Extracted rows to load.
            run_id: Current run identifier, auto-added as column ``run_id``.

        Returns:
            Number of inserted rows.

        Raises:
            ValueError: On invalid table name or empty insert columns.
            SQLAlchemyError: On SQL execution errors.
        """
        target_table = self._normalize_table_name(table_name)

        if not rows:
            logger.info("No rows to load for raw_oracle.{}", target_table)
            return 0

        columns = self._resolve_columns(rows)
        insert_columns = ["run_id", *columns]

        column_sql = ", ".join(f'"{col}"' for col in insert_columns)
        values_sql = ", ".join(f":{col}" for col in insert_columns)
        sql = text(
            f'INSERT INTO "{RAW_ORACLE_SCHEMA}"."{target_table}" ({column_sql}) '
            f"VALUES ({values_sql})"
        )

        params = self._build_batch_params(rows=rows, columns=columns, run_id=run_id)

        try:
            with self.postgres_client.engine.begin() as conn:
                conn.execute(sql, params)
            inserted = len(params)
            logger.info(
                "Loaded {} row(s) into raw_oracle.{} for run_id={}",
                inserted,
                target_table,
                run_id,
            )
            return inserted
        except SQLAlchemyError:
            logger.exception(
                "Failed loading rows into raw_oracle.{} for run_id={}",
                target_table,
                run_id,
            )
            raise

    def _delete_run(
        self,
        conn: Any,
        target_table: str,
        run_id: int,
        recname_prefix: str | None = None,
        prefix_len: int = 2,
    ) -> None:
        """Delete existing rows for one run (optionally scoped to a recname prefix).

        The prefix scope makes ``column_catalog`` loads idempotent *per prefix*,
        which is what enables safe resume after a partial extraction.
        """
        if recname_prefix is None:
            conn.execute(
                text(f'DELETE FROM "{RAW_ORACLE_SCHEMA}"."{target_table}" WHERE run_id = :run_id'),
                {"run_id": int(run_id)},
            )
        else:
            conn.execute(
                text(
                    f'DELETE FROM "{RAW_ORACLE_SCHEMA}"."{target_table}" '
                    f"WHERE run_id = :run_id AND SUBSTR(recname, 1, :n) = :prefix"
                ),
                {"run_id": int(run_id), "n": int(prefix_len), "prefix": recname_prefix},
            )

    def replace_rows(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        run_id: int,
        *,
        recname_prefix: str | None = None,
        prefix_len: int = 2,
    ) -> int:
        """Idempotently load rows: DELETE (by run_id [+prefix]) then INSERT, atomically.

        Both statements run in a single transaction, so a given run_id (or a
        single recname prefix for ``column_catalog``) is always all-or-nothing.
        Re-running the same run_id never duplicates rows (honours the
        documented idempotency contract).
        """
        target_table = self._normalize_table_name(table_name)

        with self.postgres_client.engine.begin() as conn:
            self._delete_run(conn, target_table, run_id, recname_prefix, prefix_len)

            if not rows:
                logger.info(
                    "replace_rows: nothing to insert into raw_oracle.{} (run_id={}, prefix={})",
                    target_table,
                    run_id,
                    recname_prefix,
                )
                return 0

            columns = self._resolve_columns(rows)
            insert_columns = ["run_id", *columns]
            column_sql = ", ".join(f'"{col}"' for col in insert_columns)
            values_sql = ", ".join(f":{col}" for col in insert_columns)
            sql = text(
                f'INSERT INTO "{RAW_ORACLE_SCHEMA}"."{target_table}" ({column_sql}) '
                f"VALUES ({values_sql})"
            )
            params = self._build_batch_params(rows=rows, columns=columns, run_id=run_id)
            conn.execute(sql, params)

        inserted = len(rows)
        logger.info(
            "Replaced {} row(s) into raw_oracle.{} for run_id={} (prefix={})",
            inserted,
            target_table,
            run_id,
            recname_prefix,
        )
        return inserted

    def load_record_catalog(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_oracle.record_catalog`` (idempotent by run_id)."""
        return self.replace_rows("record_catalog", rows, run_id)

    def load_table_catalog(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_oracle.table_catalog`` (idempotent by run_id)."""
        return self.replace_rows("table_catalog", rows, run_id)

    def load_column_catalog(
        self,
        rows: list[dict[str, Any]],
        run_id: int,
        recname_prefix: str | None = None,
        prefix_len: int = 2,
    ) -> int:
        """Load rows into ``raw_oracle.column_catalog``.

        When ``recname_prefix`` is given, the load is idempotent *for that
        prefix only* (DELETE+INSERT scoped to the prefix), which is what makes
        prefix-paginated extraction safely resumable.
        """
        return self.replace_rows(
            "column_catalog",
            rows,
            run_id,
            recname_prefix=recname_prefix,
            prefix_len=prefix_len,
        )

    def load_index_catalog(self, rows: list[dict[str, Any]], run_id: int) -> int:
        """Load rows into ``raw_oracle.index_catalog`` (idempotent by run_id)."""
        return self.replace_rows("index_catalog", rows, run_id)


def load_all_raw_oracle(
    loader: RawOracleLoader,
    run_id: int,
    record_catalog_rows: Sequence[dict[str, Any]] | None = None,
    table_catalog_rows: Sequence[dict[str, Any]] | None = None,
    column_catalog_rows: Sequence[dict[str, Any]] | None = None,
    index_catalog_rows: Sequence[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Load all Oracle catalog datasets for one run.

    Args:
        loader: Initialized ``RawOracleLoader``.
        run_id: Current run identifier.
        record_catalog_rows: Record catalog rows.
        table_catalog_rows: Table catalog rows.
        column_catalog_rows: Column catalog rows.
        index_catalog_rows: Index catalog rows.

    Returns:
        Per-table inserted counts.
    """
    counts = {
        "record_catalog": loader.load_record_catalog(list(record_catalog_rows or []), run_id),
        "table_catalog": loader.load_table_catalog(list(table_catalog_rows or []), run_id),
        "column_catalog": loader.load_column_catalog(list(column_catalog_rows or []), run_id),
        "index_catalog": loader.load_index_catalog(list(index_catalog_rows or []), run_id),
    }
    logger.info("Raw Oracle load completed for run_id={} with counts={}", run_id, counts)
    return counts
