"""Build `processed.features_asset` aligned with final V1 DDL."""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.features_asset WHERE run_id = :run_id"

INSERT_SQL = """
INSERT INTO processed.features_asset (
    run_id,
    asset_id,
    snapshot_date,
    row_count,
    size_mb,
    column_count,
    index_count,
    lineage_in_count,
    lineage_out_count,
    term_count,
    purge_event_count,
    total_purged_rows,
    archival_candidate_score,
    roi_score,
    loaded_at
)
WITH profile AS (
    SELECT
        asset_id,
        max(snapshot_date) AS snapshot_date,
        max(row_count) AS row_count,
        max(size_mb) AS size_mb,
        max(column_count) AS column_count,
        max(index_count) AS index_count
    FROM processed.fact_asset_profile
    WHERE run_id = :run_id
    GROUP BY asset_id
),
lineage_in AS (
    SELECT target_asset_id AS asset_id, COUNT(*) AS lineage_in_count
    FROM processed.fact_lineage_edge
    WHERE run_id = :run_id
      AND target_asset_id IS NOT NULL
    GROUP BY target_asset_id
),
lineage_out AS (
    SELECT source_asset_id AS asset_id, COUNT(*) AS lineage_out_count
    FROM processed.fact_lineage_edge
    WHERE run_id = :run_id
      AND source_asset_id IS NOT NULL
    GROUP BY source_asset_id
),
term_cte AS (
    SELECT asset_id, COUNT(*) AS term_count
    FROM processed.bridge_asset_term
    WHERE run_id = :run_id
    GROUP BY asset_id
),
purge_cte AS (
    SELECT
        asset_id,
        COUNT(*) AS purge_event_count,
        coalesce(sum(rows_affected), 0)::bigint AS total_purged_rows
    FROM processed.fact_archiving_event
    WHERE run_id = :run_id
    GROUP BY asset_id
)
SELECT
    :run_id AS run_id,
    da.id AS asset_id,
    coalesce(p.snapshot_date, current_date) AS snapshot_date,
    p.row_count,
    p.size_mb,
    p.column_count,
    p.index_count,
    coalesce(li.lineage_in_count, 0) AS lineage_in_count,
    coalesce(lo.lineage_out_count, 0) AS lineage_out_count,
    coalesce(t.term_count, 0) AS term_count,
    coalesce(pc.purge_event_count, 0) AS purge_event_count,
    coalesce(pc.total_purged_rows, 0) AS total_purged_rows,
    (
        least(coalesce(p.size_mb, 0) / 100.0, 30)
        + least(coalesce(pc.purge_event_count, 0) * 5, 25)
        + greatest(20 - coalesce(lo.lineage_out_count, 0) * 2, 0)
        + greatest(25 - coalesce(t.term_count, 0) * 3, 0)
    )::numeric AS archival_candidate_score,
    (
        least(coalesce(p.size_mb, 0) / 100.0, 40)
        + least(coalesce(pc.total_purged_rows, 0) / 100000.0, 30)
        + greatest(30 - coalesce(lo.lineage_out_count, 0) * 2, 0)
    )::numeric AS roi_score,
    now() AS loaded_at
FROM processed.dim_asset da
LEFT JOIN profile p ON p.asset_id = da.id
LEFT JOIN lineage_in li ON li.asset_id = da.id
LEFT JOIN lineage_out lo ON lo.asset_id = da.id
LEFT JOIN term_cte t ON t.asset_id = da.id
LEFT JOIN purge_cte pc ON pc.asset_id = da.id
WHERE da.run_id = :run_id
"""

COUNT_SQL = "SELECT COUNT(*) AS row_count FROM processed.features_asset WHERE run_id = :run_id"


def build_features_asset(run_id: int) -> int:
    """Build `processed.features_asset` for one full-reload run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.features_asset for run_id={}", run_id)
        postgres_client.execute(DELETE_SQL, {"run_id": run_id})
        postgres_client.execute(INSERT_SQL, {"run_id": run_id})
        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0
        logger.info("processed.features_asset built: {} row(s)", produced)
        return produced
    except Exception:
        logger.exception("Failed building processed.features_asset for run_id={}", run_id)
        raise


def main() -> None:
    """Run local test for `build_features_asset`."""
    configure_logging()
    count = build_features_asset(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()
