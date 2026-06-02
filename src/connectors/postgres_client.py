"""PostgreSQL connector module.

Provides :class:`PostgresClient`, a thin wrapper around SQLAlchemy for
use in the pfe-data-ia data pipeline.  The client exposes simple methods
for connection testing, generic SQL execution, result fetching and DDL/DML
scripting without relying on any ORM layer.

Example::

    from src.config.settings import get_settings
    from src.connectors.postgres_client import PostgresClient

    pg = PostgresClient(get_settings())
    if pg.test_connection():
        rows = pg.fetch_all("SELECT * FROM staging.raw_ingestion LIMIT 5")
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Any, Generator

from loguru import logger
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import Settings

# ---------------------------------------------------------------------------
# Tenacity retry policy reused across methods that open a connection
# ---------------------------------------------------------------------------

_CONNECTION_RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(SQLAlchemyError),
    before_sleep=before_sleep_log(logger, "WARNING"),  # type: ignore[arg-type]
    reraise=True,
)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PostgresClient:
    """Reusable PostgreSQL client for the pfe-data-ia pipeline.

    Wraps SQLAlchemy Core (no ORM).  A single engine is created once at
    instantiation and reused for all operations.  All public methods manage
    their own connection/transaction lifecycle and never leak open resources.

    Args:
        settings: Application settings instance carrying connection parameters.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: Engine = self._build_engine()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_engine(self) -> Engine:
        """Build and return the SQLAlchemy engine.

        Uses ``pool_pre_ping=True`` so stale connections borrowed from the
        pool are automatically discarded.
        """
        logger.info(
            "Building PostgreSQL engine — host={} db={}",
            self.settings.postgres_host,
            self.settings.postgres_db,
        )
        return create_engine(
            self.settings.postgresql_url,
            pool_pre_ping=True,
            future=True,
        )

    @contextmanager
    def _connect(self) -> Generator[Connection, None, None]:
        """Context manager that yields an open :class:`~sqlalchemy.engine.Connection`.

        The connection is closed automatically when the ``with`` block exits,
        whether normally or due to an exception.
        """
        conn: Connection = self.engine.connect()
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @retry(**_CONNECTION_RETRY)
    def test_connection(self) -> bool:
        """Probe the database with a lightweight query.

        Returns:
            ``True`` when the connection succeeds.

        Raises:
            :class:`~sqlalchemy.exc.SQLAlchemyError`: After all retries are
                exhausted if the database is unreachable.
        """
        with self._connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(
            "PostgreSQL connection OK — {}:{}/{}",
            self.settings.postgres_host,
            self.settings.postgres_port,
            self.settings.postgres_db,
        )
        return True

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        """Execute a DML statement (INSERT / UPDATE / DELETE) inside a transaction.

        The transaction is committed automatically on success and rolled back
        on any exception.

        Args:
            sql: SQL statement string.  Use ``:name`` placeholders for
                parameter binding.
            params: Optional mapping of bind parameter values.

        Raises:
            :class:`~sqlalchemy.exc.SQLAlchemyError`: On database error.
        """
        logger.debug("execute | sql={!r} params={}", sql, params)
        try:
            with self.engine.begin() as conn:
                conn.execute(text(sql), params or {})
            logger.debug("execute | committed")
        except SQLAlchemyError:
            logger.exception("execute | failed — sql={!r}", sql)
            raise

    def fetch_all(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT and return every row as a plain dictionary.

        Args:
            sql: SELECT statement string.  Use ``:name`` placeholders for
                parameter binding.
            params: Optional mapping of bind parameter values.

        Returns:
            List of dictionaries mapping column names to row values.
            Returns an empty list when no rows match.

        Raises:
            :class:`~sqlalchemy.exc.SQLAlchemyError`: On database error.
        """
        logger.debug("fetch_all | sql={!r} params={}", sql, params)
        try:
            with self._connect() as conn:
                result = conn.execute(text(sql), params or {})
                keys = list(result.keys())
                rows: list[dict[str, Any]] = [
                    dict(zip(keys, row)) for row in result.fetchall()
                ]
            logger.debug("fetch_all | {} row(s) returned", len(rows))
            return rows
        except SQLAlchemyError:
            logger.exception("fetch_all | failed — sql={!r}", sql)
            raise

    def fetch_one(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Execute a SELECT and return only the first row as a dictionary.

        Args:
            sql: SELECT statement string.  Use ``:name`` placeholders for
                parameter binding.
            params: Optional mapping of bind parameter values.

        Returns:
            A dictionary mapping column names to values, or ``None`` when
            the query returns no rows.

        Raises:
            :class:`~sqlalchemy.exc.SQLAlchemyError`: On database error.
        """
        logger.debug("fetch_one | sql={!r} params={}", sql, params)
        try:
            with self._connect() as conn:
                result = conn.execute(text(sql), params or {})
                row = result.fetchone()
                if row is None:
                    logger.debug("fetch_one | no row returned")
                    return None
                record: dict[str, Any] = dict(zip(result.keys(), row))
            logger.debug("fetch_one | row returned")
            return record
        except SQLAlchemyError:
            logger.exception("fetch_one | failed — sql={!r}", sql)
            raise

    def execute_returning(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Execute a writing statement with RETURNING inside a committed transaction.

        Unlike :meth:`fetch_one` (read-only, non-committing), this runs the
        statement in ``engine.begin()`` so an ``INSERT/UPDATE ... RETURNING``
        is **persisted**. Returns the first returned row as a dict, or ``None``.

        Args:
            sql: DML statement string with a ``RETURNING`` clause.
            params: Optional mapping of bind parameter values.

        Raises:
            :class:`~sqlalchemy.exc.SQLAlchemyError`: On database error.
        """
        logger.debug("execute_returning | sql={!r} params={}", sql, params)
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text(sql), params or {})
                row = result.fetchone()
                if row is None:
                    return None
                return dict(zip(result.keys(), row))
        except SQLAlchemyError:
            logger.exception("execute_returning | failed — sql={!r}", sql)
            raise

    def execute_script(self, sql_script: str) -> None:
        """Execute a multi-statement SQL script inside a single transaction.

        Individual statements must be separated by semicolons.  Empty
        statements (e.g. trailing semicolons) are silently ignored.

        Args:
            sql_script: Raw SQL text containing one or more statements.

        Raises:
            :class:`~sqlalchemy.exc.SQLAlchemyError`: On database error.
                The transaction is rolled back automatically.
        """
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        logger.debug("execute_script | {} statement(s) to run", len(statements))
        try:
            with self.engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
            logger.info("execute_script | {} statement(s) committed", len(statements))
        except SQLAlchemyError:
            logger.exception("execute_script | failed — rolling back")
            raise

    def get_connection(self) -> Connection:
        """Return a raw :class:`~sqlalchemy.engine.Connection` for advanced use.

        The caller is responsible for closing the connection (e.g. via a
        ``with`` statement or an explicit ``.close()`` call).

        Returns:
            An open SQLAlchemy ``Connection``.
        """
        return self.engine.connect()

# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from src.config.settings import get_settings
    from src.utils.logging_utils import configure_logging

    _settings = get_settings()
    configure_logging()

    _client = PostgresClient(settings=_settings)

    try:
        _client.test_connection()
        logger.info("Smoke-test passed.")
    except Exception:
        logger.exception("Smoke-test failed.")
        sys.exit(1)
