"""Prefect flow : rechargement complet de la source Oracle.

Crée un nouveau run_id, extrait Oracle → raw_oracle, construit la couche
processed (avec scoring ML), puis publie la couche serving. Cycle de vie tracé
dans `admin.pipeline_run`.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from prefect import flow

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.prefect.flows.flow_build_processed import flow_build_processed
from src.prefect.flows.flow_oracle_raw import flow_oracle_raw
from src.prefect.flows.flow_publish_serving import flow_publish_serving
from src.utils.logging_utils import configure_logging

CREATE_RUN_SQL = """
    INSERT INTO admin.pipeline_run (flow_name, run_type, source_system, status)
    VALUES ('flow_oracle_only', 'full', 'oracle', 'running')
    RETURNING id
"""


def _create_oracle_run(postgres_client: PostgresClient) -> int:
    """Create a running entry in admin.pipeline_run (source = oracle)."""
    row = postgres_client.execute_returning(sql=CREATE_RUN_SQL)
    if row is None or row.get("id") is None:
        raise RuntimeError("Échec création admin.pipeline_run : id manquant")
    run_id = int(row["id"])
    logger.info("admin.pipeline_run créé (oracle-only) run_id={}", run_id)
    return run_id


def mark_pipeline_run_success(postgres_client: PostgresClient, run_id: int) -> None:
    """Mark a pipeline run as success and set ended_at."""
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
    """Mark a pipeline run as failed and set ended_at + error_message."""
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


@flow(name="flow_oracle_only")
def flow_oracle_only(model_path: str | None = None) -> int:
    """Run the Oracle full reload end-to-end.

    Ordered: flow_oracle_raw -> flow_build_processed (incl. scoring) ->
    flow_publish_serving.

    Returns:
        Generated run identifier.
    """
    configure_logging()
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    logger.info("Starting flow_oracle_only (source Oracle PeopleSoft EP92U038)")
    run_id = _create_oracle_run(postgres_client=postgres_client)

    try:
        flow_oracle_raw(run_id=run_id)
        processed_counters = flow_build_processed(run_id=run_id, model_path=model_path)
        logger.info(
            "flow_build_processed counters for run_id={}: {}",
            run_id,
            processed_counters,
        )
        flow_publish_serving()

        mark_pipeline_run_success(postgres_client=postgres_client, run_id=run_id)
        logger.info("flow_oracle_only completed successfully for run_id={}", run_id)
        return run_id
    except Exception as exc:
        logger.exception("flow_oracle_only failed for run_id={}", run_id)
        mark_pipeline_run_failed(
            postgres_client=postgres_client,
            run_id=run_id,
            error_message=str(exc),
        )
        raise


def main() -> None:
    """Local entry point to execute the Oracle-only flow."""
    flow_oracle_only()


if __name__ == "__main__":
    main()
