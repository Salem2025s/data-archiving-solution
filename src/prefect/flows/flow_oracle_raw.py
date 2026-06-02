"""Prefect flow for Oracle raw extraction and loading (V1 full reload)."""

from __future__ import annotations

from loguru import logger
from prefect import flow

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.connectors.postgres_client import PostgresClient
from src.extract.oracle.extract_column_catalog import extract_column_catalog
from src.extract.oracle.extract_index_catalog import extract_index_catalog
from src.extract.oracle.extract_record_catalog import extract_record_catalog
from src.extract.oracle.extract_segment_access import extract_segment_access
from src.extract.oracle.extract_table_catalog import extract_table_catalog
from src.load.load_raw_oracle import RawOracleLoader
from src.utils.logging_utils import configure_logging

PREFIX_QUERY = """
SELECT DISTINCT SUBSTR(recname, 1, 2) AS recname_prefix
FROM SYSADM.PSRECDEFN
WHERE recname <> 'PSDUMMY'
ORDER BY 1
""".strip()


def fetch_recname_prefixes(settings_owner: str) -> list[str]:
    """Fetch real 2-char record prefixes from Oracle metadata."""
    settings = get_settings()
    client = OracleClient(settings=settings)

    rows = client.fetch_all(sql=PREFIX_QUERY)
    prefixes = [str(row.get("recname_prefix", "")).strip().upper() for row in rows]
    prefixes = [prefix for prefix in prefixes if prefix]

    logger.info(
        "Fetched {} Oracle recname prefix(es) for owner={}",
        len(prefixes),
        settings_owner,
    )
    return prefixes


def loaded_column_prefixes(
    postgres_client: PostgresClient,
    run_id: int,
    prefix_len: int = 2,
) -> set[str]:
    """Return recname prefixes already fully loaded in column_catalog for a run.

    Because each prefix is loaded atomically (DELETE+INSERT in one transaction),
    a prefix present here is guaranteed complete — so it can be safely skipped
    when resuming a partially-extracted run.
    """
    rows = postgres_client.fetch_all(
        "SELECT DISTINCT SUBSTR(recname, 1, :n) AS p "
        "FROM raw_oracle.column_catalog "
        "WHERE run_id = :run_id AND recname IS NOT NULL",
        {"n": int(prefix_len), "run_id": int(run_id)},
    )
    return {str(r["p"]).strip().upper() for r in rows if r.get("p")}


@flow(name="flow_oracle_raw")
def flow_oracle_raw(run_id: int, resume: bool = True) -> int:
    """Run Oracle raw pipeline for one full-reload run.

    Robust to VPN drops during the multi-hour ``column_catalog`` extraction:
    - cheap catalogs (record/table/index) are extracted and loaded *first*, so
      a later column failure never loses them;
    - the column catalog is paginated by recname prefix and each prefix is
      loaded atomically and idempotently — a failed prefix is logged and the
      others continue;
    - with ``resume=True`` (default), prefixes already loaded for this run_id
      are skipped, so re-running finishes only the missing prefixes instead of
      restarting the whole extraction.

    Args:
        run_id: Current run identifier.
        resume: Skip recname prefixes already loaded for ``run_id``.

    Returns:
        Total number of loaded rows across Oracle raw target tables.

    Raises:
        RuntimeError: When one or more prefixes still failed after retries.
    """
    configure_logging()
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    loader = RawOracleLoader(postgres_client=postgres_client)
    owner = settings.oracle_owner

    logger.info("Starting flow_oracle_raw for run_id={} (resume={})", run_id, resume)

    try:
        # 1) Cheap catalogs first (idempotent) — never lost to a column failure.
        loaded_record = loader.load_record_catalog(rows=extract_record_catalog(), run_id=run_id)
        loaded_table = loader.load_table_catalog(rows=extract_table_catalog(), run_id=run_id)
        loaded_index = loader.load_index_catalog(rows=extract_index_catalog(), run_id=run_id)
        # Optional read-access signal (V$SEGMENT_STATISTICS). Returns [] and stays
        # inert if SYSADM lacks the grant — never blocks the run.
        loaded_access = loader.load_segment_access(rows=extract_segment_access(owner=owner), run_id=run_id)

        # 2) Column catalog — paginated, idempotent & resumable per recname prefix.
        recname_prefixes = fetch_recname_prefixes(settings_owner=owner)
        already_done = (
            loaded_column_prefixes(postgres_client, run_id) if resume else set()
        )
        if already_done:
            logger.info(
                "Resume: {} prefix(es) already loaded for run_id={} -> skipped",
                len(already_done),
                run_id,
            )

        column_catalog_total = 0
        failed_prefixes: list[str] = []
        total_prefixes = len(recname_prefixes)
        for position, prefix in enumerate(recname_prefixes, start=1):
            if prefix in already_done:
                logger.info("[{}/{}] prefix={} already loaded -> skip", position, total_prefixes, prefix)
                continue
            try:
                column_rows = extract_column_catalog(owner=owner, recname_prefix=prefix)
                loaded_batch = loader.load_column_catalog(
                    rows=column_rows, run_id=run_id, recname_prefix=prefix
                )
                column_catalog_total += loaded_batch
                logger.info(
                    "[{}/{}] prefix={} -> {} column_catalog row(s) loaded",
                    position,
                    total_prefixes,
                    prefix,
                    loaded_batch,
                )
            except Exception as exc:  # tolerate a single prefix failure, keep going
                logger.exception(
                    "[{}/{}] prefix={} FAILED ({}); continuing with remaining prefixes",
                    position,
                    total_prefixes,
                    prefix,
                    exc,
                )
                failed_prefixes.append(prefix)

        total_loaded = loaded_record + loaded_table + column_catalog_total + loaded_index + loaded_access

        if failed_prefixes:
            raise RuntimeError(
                f"flow_oracle_raw: {len(failed_prefixes)} prefix(es) failed after retries: "
                f"{failed_prefixes}. Loaded prefixes are persisted — re-run "
                f"flow_oracle_raw(run_id={run_id}, resume=True) to finish the missing ones."
            )

        logger.info(
            "flow_oracle_raw completed for run_id={} with column_catalog_total={} and total_loaded={}",
            run_id,
            column_catalog_total,
            total_loaded,
        )
        return total_loaded
    except Exception:
        logger.exception("flow_oracle_raw failed for run_id={}", run_id)
        raise


if __name__ == "__main__":
    flow_oracle_raw(run_id=1)
