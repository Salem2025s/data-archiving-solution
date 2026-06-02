"""Build `processed.dim_asset` aligned with final V1 DDL."""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.dim_asset WHERE run_id = :run_id"

INSERT_SQL = """
INSERT INTO processed.dim_asset (
    run_id,
    source_system,
    asset_type,
    technical_name,
    business_name,
    schema_name,
    owner_name,
    description,
    status,
    source_ref,
    loaded_at
)
SELECT *
FROM (
    SELECT DISTINCT
        :run_id AS run_id,
        'oracle' AS source_system,
        'oracle_table' AS asset_type,
        (tc.owner || '.' || tc.table_name) AS technical_name,
        NULL::text AS business_name,
        tc.owner AS schema_name,
        tc.owner AS owner_name,
        NULL::text AS description,
        NULL::text AS status,
        tc.table_name AS source_ref,
        now() AS loaded_at
    FROM raw_oracle.table_catalog tc
    WHERE tc.run_id = :run_id

    UNION ALL

    SELECT DISTINCT
        :run_id AS run_id,
        'peoplesoft' AS source_system,
        'ps_record' AS asset_type,
        rc.recname AS technical_name,
        rc.recdescr AS business_name,
        rc.oracle_owner AS schema_name,
        rc.oracle_owner AS owner_name,
        rc.recdescr AS description,
        NULL::text AS status,
        rc.physical_table_name AS source_ref,
        now() AS loaded_at
    FROM raw_oracle.record_catalog rc
    WHERE rc.run_id = :run_id

    UNION ALL

    SELECT DISTINCT
        :run_id AS run_id,
        'mongo' AS source_system,
        'mongo_collection' AS asset_type,
        ci.collection_name AS technical_name,
        ci.collection_name AS business_name,
        ci.db_name AS schema_name,
        NULL::text AS owner_name,
        NULL::text AS description,
        NULL::text AS status,
        ci.source_doc_id AS source_ref,
        now() AS loaded_at
    FROM raw_mongo.collection_inventory ci
    WHERE ci.run_id = :run_id

    UNION ALL

    SELECT DISTINCT
        :run_id AS run_id,
        'mongo' AS source_system,
        'mongo_object' AS asset_type,
        coalesce(mt.name, mt.object_md, mt.source_doc_id) AS technical_name,
        mt.name AS business_name,
        NULL::text AS schema_name,
        mt.add_by AS owner_name,
        NULL::text AS description,
        mt.status AS status,
        mt.source_doc_id AS source_ref,
        now() AS loaded_at
    FROM raw_mongo.metadatastable mt
    WHERE mt.run_id = :run_id
) s
"""

COUNT_SQL = "SELECT COUNT(*) AS row_count FROM processed.dim_asset WHERE run_id = :run_id"


def build_dim_asset(run_id: int) -> int:
    """Build `processed.dim_asset` for one full-reload run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.dim_asset for run_id={}", run_id)
        postgres_client.execute(DELETE_SQL, {"run_id": run_id})
        postgres_client.execute(INSERT_SQL, {"run_id": run_id})
        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0
        logger.info("processed.dim_asset built: {} row(s)", produced)
        return produced
    except Exception:
        logger.exception("Failed building processed.dim_asset for run_id={}", run_id)
        raise


def main() -> None:
    """Run local test for `build_dim_asset`."""
    configure_logging()
    count = build_dim_asset(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()
