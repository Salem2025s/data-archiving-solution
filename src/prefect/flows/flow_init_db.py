"""Prefect flow to initialize PostgreSQL database objects for V1.

This flow executes the existing DDL files from ``sql/ddl`` in a fixed order
using ``PostgresClient``. It is intended for local environment bootstrap and
can be reused later in deployment pipelines.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from prefect import flow

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DDL_DIR = PROJECT_ROOT / "sql" / "ddl"
DDL_FILES: tuple[str, ...] = (
    "001_schemas.sql",
    "010_admin.sql",
    "020_raw_oracle.sql",
    "030_raw_mongo.sql",
    "040_processed.sql",
    "050_serving.sql",
)


def read_sql_file(file_path: Path) -> str:
    """Read and return SQL content from a file.

    Args:
        file_path: Path to the SQL file.

    Returns:
        SQL file content as text.

    Raises:
        FileNotFoundError: If the SQL file does not exist.
        OSError: If the file cannot be read.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"SQL file not found: {file_path}")

    sql_content = file_path.read_text(encoding="utf-8")
    logger.info("Read SQL file: {}", file_path.name)
    return sql_content


def execute_sql_file(postgres_client: PostgresClient, file_path: Path) -> None:
    """Execute one SQL file using the provided PostgreSQL client.

    Args:
        postgres_client: Initialized PostgreSQL client.
        file_path: Path to the SQL file to execute.

    Raises:
        Exception: Propagates read or SQL execution errors after logging.
    """
    try:
        logger.info("Executing SQL file: {}", file_path.name)
        sql_script = read_sql_file(file_path)
        postgres_client.execute_script(sql_script)
        logger.info("Successfully executed SQL file: {}", file_path.name)
    except Exception:
        logger.exception("Failed to execute SQL file: {}", file_path)
        raise


@flow(name="flow_init_db")
def flow_init_db() -> None:
    """Initialize PostgreSQL database objects for the V1 pipeline.

    The flow executes the DDL files from ``sql/ddl`` in the required order.
    It stops immediately on the first failure.
    """
    configure_logging()
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    logger.info("Starting database initialization flow")
    logger.info("DDL directory: {}", DDL_DIR)

    try:
        postgres_client.test_connection()

        for ddl_file_name in DDL_FILES:
            execute_sql_file(postgres_client=postgres_client, file_path=DDL_DIR / ddl_file_name)

        logger.info("Database initialization flow completed successfully")
    except Exception:
        logger.exception("Database initialization flow failed")
        raise


if __name__ == "__main__":
    flow_init_db()
