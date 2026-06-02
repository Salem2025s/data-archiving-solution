"""Prefect flow to refresh serving materialized views."""

from __future__ import annotations

from loguru import logger
from prefect import flow

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.transform.build_archiving_rules import build_archiving_rules
from src.transform.build_cost_analysis import build_cost_analysis
from src.transform.build_serving_domain_model import build_serving_domain_model
from src.utils.logging_utils import configure_logging

MATERIALIZED_VIEWS: tuple[str, ...] = (
    "serving.mv_asset_inventory",
    "serving.mv_archivability_ranking",
    "serving.mv_roi_summary",
)


def refresh_materialized_view(postgres_client: PostgresClient, view_name: str) -> None:
    logger.info("Refreshing materialized view: {}", view_name)
    postgres_client.execute(f"REFRESH MATERIALIZED VIEW {view_name}")
    logger.info("Materialized view refreshed: {}", view_name)


@flow(name="flow_publish_serving")
def flow_publish_serving() -> int:
    """Refresh serving materialized views in the required order.

    Returns:
        Total number of refreshed materialized views (base + domain).
    """
    configure_logging()
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    logger.info("Starting flow_publish_serving")

    try:
        postgres_client.test_connection()

        for view_name in MATERIALIZED_VIEWS:
            refresh_materialized_view(postgres_client=postgres_client, view_name=view_name)

        build_serving_domain_model()
        build_archiving_rules()
        build_cost_analysis()

        total = len(MATERIALIZED_VIEWS) + 4
        logger.info("flow_publish_serving completed, refreshed {} view(s)", total)
        return total
    except Exception:
        logger.exception("flow_publish_serving failed")
        raise


if __name__ == "__main__":
    flow_publish_serving()
