"""Build `processed.fact_asset_profile` aligned with final V1 DDL."""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.fact_asset_profile WHERE run_id = :run_id"

ORACLE_INSERT_BY_TECHNICAL_NAME_SQL = """
INSERT INTO processed.fact_asset_profile (
    run_id,
    asset_id,
    snapshot_date,
    row_count,
    size_mb,
    column_count,
    index_count,
    last_analyzed,
    source_profile_json,
    loaded_at
)
WITH oracle_column_counts AS (
    SELECT
        upper(physical_table_name) AS table_name,
        COUNT(*)::integer AS column_count
    FROM raw_oracle.column_catalog
    WHERE run_id = :run_id
    GROUP BY upper(physical_table_name)
),
oracle_index_counts AS (
    SELECT
        upper(coalesce(rc.oracle_table_name, rc.physical_table_name)) AS table_name,
        COUNT(DISTINCT ic.indexid)::integer AS index_count
    FROM raw_oracle.record_catalog rc
    JOIN raw_oracle.index_catalog ic
      ON ic.run_id = :run_id
     AND rc.run_id = :run_id
     AND ic.recname = rc.recname
    GROUP BY upper(coalesce(rc.oracle_table_name, rc.physical_table_name))
)
SELECT
    :run_id AS run_id,
    da.id AS asset_id,
    current_date AS snapshot_date,
    tc.num_rows::bigint AS row_count,
    CASE
        WHEN tc.num_rows IS NOT NULL AND tc.avg_row_len IS NOT NULL
            THEN (tc.num_rows::numeric * tc.avg_row_len::numeric) / 1024 / 1024
        ELSE NULL::numeric
    END AS size_mb,
    occ.column_count,
    oic.index_count,
    tc.last_analyzed,
    jsonb_build_object(
        'source', 'raw_oracle.table_catalog',
        'match_type', 'technical_name',
        'table_name', tc.table_name,
        'owner', tc.owner,
        'num_rows', tc.num_rows,
        'avg_row_len', tc.avg_row_len,
        'blocks', tc.blocks
    ) AS source_profile_json,
    now() AS loaded_at
FROM processed.dim_asset da
JOIN raw_oracle.table_catalog tc
  ON tc.run_id = :run_id
 AND da.run_id = :run_id
 AND da.source_system IN ('oracle', 'peoplesoft')
 AND upper(tc.owner || '.' || tc.table_name) = upper(da.technical_name)
LEFT JOIN oracle_column_counts occ
  ON occ.table_name = upper(tc.table_name)
LEFT JOIN oracle_index_counts oic
  ON oic.table_name = upper(tc.table_name);
"""

ORACLE_INSERT_BY_SOURCE_REF_SQL = """
INSERT INTO processed.fact_asset_profile (
    run_id,
    asset_id,
    snapshot_date,
    row_count,
    size_mb,
    column_count,
    index_count,
    last_analyzed,
    source_profile_json,
    loaded_at
)
WITH oracle_column_counts AS (
    SELECT
        upper(physical_table_name) AS table_name,
        COUNT(*)::integer AS column_count
    FROM raw_oracle.column_catalog
    WHERE run_id = :run_id
    GROUP BY upper(physical_table_name)
),
oracle_index_counts AS (
    SELECT
        upper(coalesce(rc.oracle_table_name, rc.physical_table_name)) AS table_name,
        COUNT(DISTINCT ic.indexid)::integer AS index_count
    FROM raw_oracle.record_catalog rc
    JOIN raw_oracle.index_catalog ic
      ON ic.run_id = :run_id
     AND rc.run_id = :run_id
     AND ic.recname = rc.recname
    GROUP BY upper(coalesce(rc.oracle_table_name, rc.physical_table_name))
)
SELECT
    :run_id AS run_id,
    da.id AS asset_id,
    current_date AS snapshot_date,
    tc.num_rows::bigint AS row_count,
    CASE
        WHEN tc.num_rows IS NOT NULL AND tc.avg_row_len IS NOT NULL
            THEN (tc.num_rows::numeric * tc.avg_row_len::numeric) / 1024 / 1024
        ELSE NULL::numeric
    END AS size_mb,
    occ.column_count,
    oic.index_count,
    tc.last_analyzed,
    jsonb_build_object(
        'source', 'raw_oracle.table_catalog',
        'match_type', 'source_ref',
        'table_name', tc.table_name,
        'owner', tc.owner,
        'num_rows', tc.num_rows,
        'avg_row_len', tc.avg_row_len,
        'blocks', tc.blocks
    ) AS source_profile_json,
    now() AS loaded_at
FROM processed.dim_asset da
JOIN raw_oracle.table_catalog tc
  ON tc.run_id = :run_id
 AND da.run_id = :run_id
 AND da.source_system IN ('oracle', 'peoplesoft')
 AND nullif(trim(coalesce(da.source_ref, '')), '') IS NOT NULL
 AND upper(tc.table_name) = upper(da.source_ref)
LEFT JOIN oracle_column_counts occ
  ON occ.table_name = upper(tc.table_name)
LEFT JOIN oracle_index_counts oic
  ON oic.table_name = upper(tc.table_name)
WHERE NOT EXISTS (
    SELECT 1
    FROM processed.fact_asset_profile f
    WHERE f.run_id = :run_id
      AND f.asset_id = da.id
);
"""

COUNT_SQL = """
SELECT COUNT(*) AS row_count
FROM processed.fact_asset_profile
WHERE run_id = :run_id
"""


def build_fact_asset_profile(run_id: int) -> int:
    """Build `processed.fact_asset_profile` for one full-reload run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.fact_asset_profile for run_id={}", run_id)

        postgres_client.execute(DELETE_SQL, {"run_id": run_id})

        logger.info(
            "Step 1/2 - loading Oracle asset profiles matched by technical_name for run_id={}",
            run_id,
        )
        postgres_client.execute(ORACLE_INSERT_BY_TECHNICAL_NAME_SQL, {"run_id": run_id})

        logger.info(
            "Step 2/2 - loading Oracle asset profiles matched by source_ref for run_id={}",
            run_id,
        )
        postgres_client.execute(ORACLE_INSERT_BY_SOURCE_REF_SQL, {"run_id": run_id})

        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0

        logger.info("processed.fact_asset_profile built: {} row(s)", produced)
        return produced

    except Exception:
        logger.exception(
            "Failed building processed.fact_asset_profile for run_id={}",
            run_id,
        )
        raise


def main() -> None:
    """Run local test for `build_fact_asset_profile`."""
    configure_logging()
    count = build_fact_asset_profile(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()