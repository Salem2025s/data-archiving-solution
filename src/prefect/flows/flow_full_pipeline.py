"""Prefect flow orchestrating the complete V1 pipeline."""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from prefect import flow

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.prefect.flows.flow_build_processed import flow_build_processed
from src.prefect.flows.flow_mongo_raw import flow_mongo_raw
from src.prefect.flows.flow_oracle_raw import flow_oracle_raw
from src.prefect.flows.flow_publish_serving import flow_publish_serving
from src.utils.logging_utils import configure_logging


def create_pipeline_run(postgres_client: PostgresClient) -> int:
    """Create a running entry in admin.pipeline_run and return its id.

    Inserted values:
    - flow_name = 'flow_full_pipeline'
    - run_type = 'full'
    - source_system = 'all'
    - status = 'running'

    Args:
        postgres_client: Initialized PostgreSQL client.

    Returns:
        Generated run identifier.

    Raises:
        RuntimeError: If INSERT does not return an id.
    """
    sql = """
        INSERT INTO admin.pipeline_run (flow_name, run_type, source_system, status)
        VALUES (:flow_name, :run_type, :source_system, :status)
        RETURNING id
    """
    params = {
        "flow_name": "flow_full_pipeline",
        "run_type": "full",
        "source_system": "all",
        "status": "running",
    }

    row = postgres_client.execute_returning(sql=sql, params=params)
    if row is None or row.get("id") is None:
        raise RuntimeError("Failed to create admin.pipeline_run row: missing id")

    run_id = int(row["id"])
    logger.info("Created admin.pipeline_run with run_id={}", run_id)
    return run_id


def mark_pipeline_run_success(postgres_client: PostgresClient, run_id: int) -> None:
    """Mark a pipeline run as success and set ended_at.

    Args:
        postgres_client: Initialized PostgreSQL client.
        run_id: Pipeline run id.
    """
    sql = """
        UPDATE admin.pipeline_run
        SET status = :status,
            ended_at = :ended_at,
            error_message = NULL
        WHERE id = :run_id
    """
    postgres_client.execute(
        sql=sql,
        params={
            "status": "success",
            "ended_at": datetime.utcnow(),
            "run_id": run_id,
        },
    )
    logger.info("Marked run_id={} as success", run_id)


def mark_pipeline_run_failed(
    postgres_client: PostgresClient,
    run_id: int,
    error_message: str,
) -> None:
    """Mark a pipeline run as failed and set ended_at + error_message.

    Args:
        postgres_client: Initialized PostgreSQL client.
        run_id: Pipeline run id.
        error_message: Error message to persist.
    """
    sql = """
        UPDATE admin.pipeline_run
        SET status = :status,
            ended_at = :ended_at,
            error_message = :error_message
        WHERE id = :run_id
    """
    postgres_client.execute(
        sql=sql,
        params={
            "status": "failed",
            "ended_at": datetime.utcnow(),
            "error_message": error_message[:4000],
            "run_id": run_id,
        },
    )
    logger.info("Marked run_id={} as failed", run_id)


@flow(name="flow_full_pipeline")
def flow_full_pipeline(model_path: str | None = None) -> int:
    """Run full V1 pipeline end-to-end.

    Ordered orchestration:
    - flow_oracle_raw(run_id)
    - flow_mongo_raw(run_id)
    - flow_build_processed(run_id, model_path)
    - flow_publish_serving()

    Lifecycle tracking is stored in ``admin.pipeline_run``.

    Args:
        model_path: Optional business-domain model path forwarded to
            ``flow_build_processed``.

    Returns:
        Generated run identifier.
    """
    configure_logging()
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    logger.info("Starting flow_full_pipeline")
    run_id = create_pipeline_run(postgres_client=postgres_client)

    try:
        flow_oracle_raw(run_id=run_id)
        flow_mongo_raw(run_id=run_id)
        processed_counters = flow_build_processed(run_id=run_id, model_path=model_path)
        logger.info(
            "flow_build_processed counters for run_id={}: {}",
            run_id,
            processed_counters,
        )
        flow_publish_serving()

        mark_pipeline_run_success(postgres_client=postgres_client, run_id=run_id)
        logger.info("flow_full_pipeline completed successfully for run_id={}", run_id)
        return run_id
    except Exception as exc:
        logger.exception("flow_full_pipeline failed for run_id={}", run_id)
        mark_pipeline_run_failed(
            postgres_client=postgres_client,
            run_id=run_id,
            error_message=str(exc),
        )
        raise


def main() -> None:
    """Local entry point to execute the full pipeline flow."""
    flow_full_pipeline()


if __name__ == "__main__":
    main()
