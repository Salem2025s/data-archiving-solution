"""Build `processed.fact_lineage_edge` from PeopleSoft PARENTRECNAME hierarchy.

Produces ps_parent_record edges: for each record in PSRECDEFN that declares a
PARENTRECNAME, an edge is created from the parent asset to the child asset.
This correctly marks widely-used parent records (e.g. VOUCHER, PROJECT) as
non-archivable via their high lineage_out_count, and leaves leaf records with a
low lineage_out_count so they remain archiving candidates.

Bridge-key relationships (PSKEYDEFN shared fields) are NOT stored here because
the O(n²) pair explosion (>3M edges) would distort archival scores. They are
computed on-demand at the domain modeling layer directly from
raw_oracle.index_catalog.
"""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

DELETE_SQL = "DELETE FROM processed.fact_lineage_edge WHERE run_id = :run_id"

# source = parent ps_record, target = child ps_record
INSERT_SQL = """
INSERT INTO processed.fact_lineage_edge (
    run_id,
    source_asset_id,
    target_asset_id,
    lineage_type,
    lineage_level,
    loaded_at
)
SELECT
    :run_id,
    parent_da.id        AS source_asset_id,
    child_da.id         AS target_asset_id,
    'ps_parent_record'  AS lineage_type,
    1                   AS lineage_level,
    now()
FROM raw_oracle.record_catalog rc
JOIN processed.dim_asset parent_da
  ON parent_da.run_id         = :run_id
 AND parent_da.source_system  = 'peoplesoft'
 AND parent_da.asset_type     = 'ps_record'
 AND upper(parent_da.technical_name) = upper(rc.parentrecname)
JOIN processed.dim_asset child_da
  ON child_da.run_id          = :run_id
 AND child_da.source_system   = 'peoplesoft'
 AND child_da.asset_type      = 'ps_record'
 AND upper(child_da.technical_name) = upper(rc.recname)
WHERE rc.run_id         = :run_id
  AND rc.parentrecname IS NOT NULL
  AND trim(rc.parentrecname) <> ''
"""

COUNT_SQL = """
SELECT COUNT(*) AS row_count
FROM processed.fact_lineage_edge
WHERE run_id = :run_id
"""


def build_fact_lineage_edge(run_id: int) -> int:
    """Build `processed.fact_lineage_edge` for one full-reload run."""
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)

    try:
        logger.info("Building processed.fact_lineage_edge for run_id={}", run_id)

        logger.info("Step 1/2 - deleting existing rows for run_id={}", run_id)
        postgres_client.execute(DELETE_SQL, {"run_id": run_id})

        logger.info(
            "Step 2/2 - inserting ps_parent_record edges from PARENTRECNAME for run_id={}",
            run_id,
        )
        postgres_client.execute(INSERT_SQL, {"run_id": run_id})

        row = postgres_client.fetch_one(COUNT_SQL, {"run_id": run_id})
        produced = int(row["row_count"]) if row else 0

        logger.info(
            "processed.fact_lineage_edge built: {} ps_parent_record edge(s)",
            produced,
        )
        return produced

    except Exception:
        logger.exception(
            "Failed building processed.fact_lineage_edge for run_id={}",
            run_id,
        )
        raise


def main() -> None:
    """Run local test for `build_fact_lineage_edge`."""
    configure_logging()
    count = build_fact_lineage_edge(run_id=1)
    logger.info("Manual run successful. Row count={}", count)


if __name__ == "__main__":
    main()
