"""Build `processed.dim_field` aligned with final V1 DDL."""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.dim_field WHERE run_id = :run_id"

ORACLE_RECORD_INSERT_SQL = """
INSERT INTO processed.dim_field (
    run_id,
    asset_id,
    technical_name,
    business_name,
    data_type,
    data_length,
    nullable_flag,
    source_ref,
    loaded_at
)
SELECT
    :run_id AS run_id,
    da.id AS asset_id,
    cc.column_name AS technical_name,
    cc.field_descrlong AS business_name,
    cc.data_type,
    coalesce(cc.ps_field_length, cc.data_length) AS data_length,
    CASE
        WHEN upper(coalesce(cc.nullable_flag, 'Y')) = 'Y' THEN true
        WHEN upper(coalesce(cc.nullable_flag, 'N')) = 'N' THEN false
        ELSE NULL
    END AS nullable_flag,
    cc.recname || '.' || cc.column_name AS source_ref,
    now() AS loaded_at
FROM processed.dim_asset da
JOIN raw_oracle.column_catalog cc
  ON cc.run_id = :run_id
 AND da.run_id = :run_id
 AND da.source_system = 'peoplesoft'
 AND da.asset_type = 'ps_record'
 AND upper(da.technical_name) = upper(cc.recname)
WHERE cc.recname IS NOT NULL
  AND cc.column_name IS NOT NULL
"""

ORACLE_TABLE_INSERT_SQL = """
INSERT INTO processed.dim_field (
    run_id,
    asset_id,
    technical_name,
    business_name,
    data_type,
    data_length,
    nullable_flag,
    source_ref,
    loaded_at
)
WITH dedup_columns AS (
    SELECT
        cc.physical_table_name,
        cc.column_name,
        cc.data_type,
        cc.ps_field_length,
        cc.data_length,
        cc.nullable_flag,
        max(cc.field_descrlong) AS field_descrlong
    FROM raw_oracle.column_catalog cc
    WHERE cc.run_id = :run_id
      AND cc.physical_table_name IS NOT NULL
      AND cc.column_name IS NOT NULL
    GROUP BY cc.physical_table_name, cc.column_name, cc.data_type, cc.ps_field_length, cc.data_length, cc.nullable_flag
)
SELECT
    :run_id AS run_id,
    da.id AS asset_id,
    dc.column_name AS technical_name,
    dc.field_descrlong AS business_name,
    dc.data_type,
    coalesce(dc.ps_field_length, dc.data_length) AS data_length,
    CASE
        WHEN upper(coalesce(dc.nullable_flag, 'Y')) = 'Y' THEN true
        WHEN upper(coalesce(dc.nullable_flag, 'N')) = 'N' THEN false
        ELSE NULL
    END AS nullable_flag,
    tc.owner || '.' || tc.table_name || '.' || dc.column_name AS source_ref,
    now() AS loaded_at
FROM processed.dim_asset da
JOIN raw_oracle.table_catalog tc
  ON tc.run_id = :run_id
 AND da.run_id = :run_id
 AND da.source_system = 'oracle'
 AND da.asset_type = 'oracle_table'
 AND upper(da.technical_name) = upper(tc.owner || '.' || tc.table_name)
JOIN dedup_columns dc
  ON upper(dc.physical_table_name) = upper(tc.table_name)
"""

COUNT_SQL = "SELECT COUNT(*) AS row_count FROM processed.dim_field WHERE run_id = :run_id"


def build_dim_field(run_id: int) -> int:
    """Build `processed.dim_field` for one full-reload run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.dim_field for run_id={}", run_id)

        postgres_client.execute(DELETE_SQL, {"run_id": run_id})

        logger.info(
            "Step 1/2 - loading PeopleSoft record fields for run_id={}",
            run_id,
        )
        postgres_client.execute(ORACLE_RECORD_INSERT_SQL, {"run_id": run_id})

        logger.info(
            "Step 2/2 - loading Oracle physical table fields for run_id={}",
            run_id,
        )
        postgres_client.execute(ORACLE_TABLE_INSERT_SQL, {"run_id": run_id})

        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0

        logger.info("processed.dim_field built: {} row(s)", produced)
        return produced

    except Exception:
        logger.exception(
            "Failed building processed.dim_field for run_id={}",
            run_id,
        )
        raise


def main() -> None:
    """Run local test for `build_dim_field`."""
    configure_logging()
    count = build_dim_field(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()
