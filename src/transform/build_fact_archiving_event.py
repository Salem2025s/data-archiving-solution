"""Build `processed.fact_archiving_event` for the Oracle-only scope.

The Oracle source exposes no purge journal, so no archiving events can be
derived. The build performs a safe full-reload cleanup for the run and keeps
the table empty.
"""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.fact_archiving_event WHERE run_id = :run_id"

COUNT_SQL = "SELECT COUNT(*) AS row_count FROM processed.fact_archiving_event WHERE run_id = :run_id"


def build_fact_archiving_event(run_id: int) -> int:
    """Build `processed.fact_archiving_event` for one full-reload run.

    Oracle-only V1 mode: no insertion is performed because there is currently
    no explicit Oracle raw source for archiving events in the project.
    """
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.fact_archiving_event for run_id={}", run_id)

        logger.info(
            "Step 1/2 - deleting existing fact_archiving_event rows for run_id={}",
            run_id,
        )
        postgres_client.execute(DELETE_SQL, {"run_id": run_id})

        logger.info(
            "Step 2/2 - Oracle-only V1 mode: insertion disabled for run_id={} "
            "(no explicit Oracle archiving source available)",
            run_id,
        )

        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0

        logger.info("processed.fact_archiving_event built: {} row(s)", produced)
        return produced
    except Exception:
        logger.exception(
            "Failed building processed.fact_archiving_event for run_id={}",
            run_id,
        )
        raise


def main() -> None:
    """Run local test for `build_fact_archiving_event`."""
    configure_logging()
    count = build_fact_archiving_event(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()
