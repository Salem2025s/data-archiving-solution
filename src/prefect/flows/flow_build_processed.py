"""Prefect flow for processed-layer build (V1 full reload)."""

from __future__ import annotations

from loguru import logger
from prefect import flow

from src.connectors.postgres_client import PostgresClient
from src.config.settings import get_settings
from src.transform.build_dataset_asset_ml import build_dataset_asset_ml
from src.transform.build_bridge_asset_term import build_bridge_asset_term
from src.transform.build_dim_asset import build_dim_asset
from src.transform.build_dim_field import build_dim_field
from src.transform.build_fact_archiving_event import build_fact_archiving_event
from src.transform.build_fact_asset_profile import build_fact_asset_profile
from src.transform.build_fact_lineage_edge import build_fact_lineage_edge
from src.transform.build_features_asset import build_features_asset
from src.transform.score_business_domain import DEFAULT_MODEL_PATH, score_business_domain
from src.utils.logging_utils import configure_logging


CLEAR_BUSINESS_DOMAIN_PREDICTIONS_SQL = (
    "DELETE FROM serving.asset_business_domain_prediction WHERE run_id = :run_id"
)


def _clear_business_domain_predictions(run_id: int) -> None:
    """Delete existing business-domain predictions for the current run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    postgres_client.execute(CLEAR_BUSINESS_DOMAIN_PREDICTIONS_SQL, {"run_id": run_id})


def _resolve_business_domain_model_path(model_path: str | None) -> str:
    """Resolve business-domain model path from runtime argument or settings."""
    if model_path and model_path.strip():
        return model_path.strip()

    settings = get_settings()
    configured_path = getattr(settings, "business_domain_model_path", None)
    if isinstance(configured_path, str) and configured_path.strip():
        return configured_path.strip()

    return DEFAULT_MODEL_PATH


@flow(name="flow_build_processed")
def flow_build_processed(run_id: int, model_path: str | None = None) -> dict[str, int]:
    """Build all processed tables in dependency order for one run.

    Execution order:
    - clear business-domain predictions for run_id
    - build_dim_asset
    - build_dim_field
    - build_bridge_asset_term
    - build_fact_asset_profile
    - build_fact_lineage_edge
    - build_fact_archiving_event
    - build_features_asset
    - build_dataset_asset_ml
    - score_business_domain

    Args:
        run_id: Current run identifier.
        model_path: Optional path to business-domain model artifact.

    Returns:
        Per-step produced row counts.
    """
    configure_logging()
    resolved_model_path = _resolve_business_domain_model_path(model_path=model_path)
    logger.info(
        "Starting flow_build_processed for run_id={} with business-domain model_path={}",
        run_id,
        resolved_model_path,
    )

    try:
        counters: dict[str, int] = {}

        logger.info(
            "Step 0/10 - clearing business domain predictions for run_id={}",
            run_id,
        )
        _clear_business_domain_predictions(run_id=run_id)

        logger.info("Step 1/10 - build_dim_asset")
        counters["build_dim_asset"] = build_dim_asset(run_id=run_id)

        logger.info("Step 2/10 - build_dim_field")
        counters["build_dim_field"] = build_dim_field(run_id=run_id)

        logger.info("Step 3/10 - build_bridge_asset_term")
        counters["build_bridge_asset_term"] = build_bridge_asset_term(run_id=run_id)

        logger.info("Step 4/10 - build_fact_asset_profile")
        counters["build_fact_asset_profile"] = build_fact_asset_profile(run_id=run_id)

        logger.info("Step 5/10 - build_fact_lineage_edge")
        counters["build_fact_lineage_edge"] = build_fact_lineage_edge(run_id=run_id)

        logger.info("Step 6/10 - build_fact_archiving_event")
        counters["build_fact_archiving_event"] = build_fact_archiving_event(run_id=run_id)

        logger.info("Step 7/10 - build_features_asset")
        counters["build_features_asset"] = build_features_asset(run_id=run_id)

        logger.info("Step 8/10 - build_dataset_asset_ml")
        counters["build_dataset_asset_ml"] = build_dataset_asset_ml(run_id=run_id)

        logger.info("Step 9/10 - score_business_domain")
        counters["score_business_domain"] = score_business_domain(
            run_id=run_id,
            model_path=resolved_model_path,
        )

        logger.info("flow_build_processed completed for run_id={} with counters={}", run_id, counters)
        return counters
    except Exception:
        logger.exception("flow_build_processed failed for run_id={}", run_id)
        raise


if __name__ == "__main__":
    flow_build_processed(run_id=1)
