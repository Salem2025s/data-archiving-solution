"""Oracle read-only connector for PeopleSoft EP92U038.

This module provides a simple reusable client to test Oracle connectivity and
run SELECT queries without any ORM or async layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import re

import oracledb
from loguru import logger
from tenacity import (
    Retrying,
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import Settings

# Codes d'erreur transitoires (connexion / réseau / instance) — seuls ceux-là
# justifient un retry. Les erreurs SQL déterministes (syntaxe ORA-009xx, table
# absente ORA-00942, identifiant invalide ORA-00904…) échoueraient à l'identique
# à chaque tentative : on les laisse remonter immédiatement.
_RETRYABLE_DPY: frozenset[str] = frozenset({
    "DPY-6005",  # cannot connect to database (timeout, VPN coupé)
    "DPY-4011",  # the database or network closed the connection
    "DPY-4024",  # connection was closed
    "DPY-1001",  # not connected to database
})
_RETRYABLE_ORA: frozenset[str] = frozenset({
    "ORA-03113",  # end-of-file on communication channel
    "ORA-03114",  # not connected to ORACLE
    "ORA-03135",  # connection lost contact
    "ORA-00028",  # your session has been killed
    "ORA-01012",  # not logged on
    "ORA-01033",  # ORACLE initialization or shutdown in progress
    "ORA-01034",  # ORACLE not available
    "ORA-01089",  # immediate shutdown in progress
    "ORA-12170",  # TNS: connect timeout occurred
    "ORA-12514",  # listener does not currently know of service
    "ORA-12518",  # listener could not hand off client connection
    "ORA-12537",  # TNS: connection closed
    "ORA-12541",  # TNS: no listener
    "ORA-12570",  # TNS: packet reader failure
    "ORA-12571",  # TNS: packet writer failure
    "ORA-25408",  # can not safely replay call
})


def _oracle_error_code(exc: BaseException) -> str:
    """Extrait le code complet (ex. 'ORA-00933', 'DPY-6005') d'une erreur oracledb."""
    err = exc.args[0] if getattr(exc, "args", None) else None
    code = getattr(err, "full_code", None)
    if code:
        return code
    match = re.match(r"\s*([A-Z]{3}-\d{4,5})", str(err) if err is not None else str(exc))
    return match.group(1) if match else ""


def _is_retryable_oracle_error(exc: BaseException) -> bool:
    """True uniquement pour les erreurs transitoires (connexion/réseau)."""
    if not isinstance(exc, oracledb.Error):
        return False
    code = _oracle_error_code(exc)
    return code in _RETRYABLE_DPY or code in _RETRYABLE_ORA


class OracleClient:
    """Simple read-only Oracle client.

    The DSN is built from settings host/port/service_name and connections are
    managed with context managers.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dsn = (
            f"{self.settings.oracle_host}:{self.settings.oracle_port}/"
            f"{self.settings.oracle_service_name}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(oracledb.Error),
        before_sleep=before_sleep_log(logger, "WARNING"),  # type: ignore[arg-type]
        reraise=True,
    )
    def _open_connection(self) -> oracledb.Connection:
        """Open an Oracle connection with retry support.

        ``expire_time`` enables dead-connection keepalive probes (minutes) and
        ``tcp_connect_timeout`` bounds the connect phase — both harden long
        extractions running over an unstable VPN.
        """
        return oracledb.connect(
            user=self.settings.oracle_user,
            password=self.settings.oracle_password,
            dsn=self.dsn,
            tcp_connect_timeout=getattr(self.settings, "oracle_tcp_connect_timeout", 20.0),
            expire_time=getattr(self.settings, "oracle_expire_time_minutes", 1),
        )

    def _query_retrying(self) -> Retrying:
        """Build a retry controller for read queries.

        Unlike ``_open_connection`` (which only retries the *connect* phase),
        this wraps the whole execute+fetch so a connection dropped mid-query
        (e.g. VPN reset / WinError 10053) re-opens and re-runs the SELECT.
        Safe because all queries here are idempotent read-only SELECTs.
        """
        attempts = int(getattr(self.settings, "oracle_query_max_attempts", 4))
        return Retrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            # Ne retente QUE les erreurs transitoires (connexion/réseau).
            # Une erreur de syntaxe SQL échoue immédiatement (pas de 15 s d'attente).
            retry=retry_if_exception(_is_retryable_oracle_error),
            before_sleep=before_sleep_log(logger, "WARNING"),  # type: ignore[arg-type]
            reraise=True,
        )

    @contextmanager
    def _connection(self) -> Iterator[oracledb.Connection]:
        """Yield an open connection and ensure clean close."""
        conn = self._open_connection()
        try:
            yield conn
        finally:
            conn.close()

    def test_connection(self) -> bool:
        """Test Oracle connectivity with a lightweight read query.

        Returns:
            True when Oracle is reachable.
        """
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM dual")
                    cursor.fetchone()
            logger.info("Oracle connection successful: {}", self.dsn)
            return True
        except oracledb.Error:
            logger.exception("Oracle connection failed: {}", self.dsn)
            raise

    @staticmethod
    def _materialize_value(value: Any) -> Any:
        """Convert Oracle-specific values to safe Python values.

        In particular, LOB values are read while the connection is still open
        so downstream code can safely serialize them after cursor/connection
        closure.
        """
        if isinstance(value, oracledb.LOB):
            return value.read()
        return value

    def fetch_all(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a read-only query and return all rows as dictionaries.

        Args:
            sql: SQL SELECT statement.
            params: Optional bind parameters.

        Returns:
            List of dictionaries with lower-cased column names.
        """
        def _execute() -> list[dict[str, Any]]:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.arraysize = 2000
                    cursor.prefetchrows = 2000
                    cursor.execute(sql, params or {})
                    columns = [col[0].lower() for col in (cursor.description or [])]
                    rows = [
                        tuple(self._materialize_value(value) for value in row)
                        for row in cursor.fetchall()
                    ]
            return [
                {columns[idx]: value for idx, value in enumerate(row)} for row in rows
            ]

        try:
            result = self._query_retrying()(_execute)
            logger.info("Oracle fetch_all returned {} row(s)", len(result))
            return result
        except oracledb.Error:
            logger.exception("Oracle fetch_all failed")
            raise

    def fetch_one(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Execute a read-only query and return first row as dictionary.

        Args:
            sql: SQL SELECT statement.
            params: Optional bind parameters.

        Returns:
            Dictionary with lower-cased column names, or None when empty.
        """
        def _execute() -> dict[str, Any] | None:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.arraysize = 2000
                    cursor.prefetchrows = 2000
                    cursor.execute(sql, params or {})
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    row = tuple(self._materialize_value(value) for value in row)
                    columns = [col[0].lower() for col in (cursor.description or [])]
            return {columns[idx]: value for idx, value in enumerate(row)}

        try:
            return self._query_retrying()(_execute)
        except oracledb.Error:
            logger.exception("Oracle fetch_one failed")
            raise

    def check_connection(self) -> None:
        """Compatibility wrapper for existing pipeline code."""
        self.test_connection()

    def fetch_table_rows(self, table_name: str) -> list[dict[str, Any]]:
        """Compatibility helper: fetch all rows from a table name.

        Args:
            table_name: Table name, optionally schema-qualified.
        """
        sql = f"SELECT * FROM {table_name}"
        return self.fetch_all(sql=sql)


if __name__ == "__main__":
    from src.utils.logging_utils import configure_logging
    from src.config.settings import get_settings

    settings = get_settings()
    configure_logging()

    client = OracleClient(settings=settings)
    ok = client.test_connection()
    logger.info("Oracle connectivity test result: {}", ok)
