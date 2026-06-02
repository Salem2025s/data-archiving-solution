"""Oracle extraction of a real ACCESS (read) signal per table.

Source: ``V$SEGMENT_STATISTICS`` — logical/physical reads accumulated per segment
since instance startup. This is part of the base product (NO Diagnostics Pack
licence required), but the ``V$`` views are SYS-owned, so the PeopleSoft
application user (SYSADM) only sees them if a DBA grants access:

    GRANT SELECT ON SYS.V_$SEGMENT_STATISTICS TO SYSADM;

Probed on EP92U038 (2026-06): SYSADM currently has NO access (ORA-00942) to any
segment-stat view. This extractor is therefore **defensive**: if the view is
inaccessible it logs the activation hint and returns ``[]`` (no rows), so the
downstream archiving rule stays inert (signal "unknown") — exactly like the
``referenced_by_count`` pattern. It "lights up" automatically once the grant is
in place, providing the genuine read-frequency dimension the spec asks for.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import oracledb
from loguru import logger

from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging

# Aggregate reads per table (rolling up partitions/subpartitions to the table).
SEGMENT_ACCESS_QUERY = """
SELECT
    s.owner,
    s.object_name AS table_name,
    SUM(CASE WHEN s.statistic_name = 'logical reads'  THEN s.value ELSE 0 END) AS logical_reads,
    SUM(CASE WHEN s.statistic_name = 'physical reads' THEN s.value ELSE 0 END) AS physical_reads
FROM v$segment_statistics s
WHERE s.owner = :owner
  AND s.object_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION')
  AND s.statistic_name IN ('logical reads', 'physical reads')
GROUP BY s.owner, s.object_name
""".strip()

GRANT_HINT = "GRANT SELECT ON SYS.V_$SEGMENT_STATISTICS TO {owner};"


def compute_row_hash(record: dict[str, Any]) -> str:
    """Deterministic SHA-256 of one row (sorted-key JSON)."""
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_access_denied(exc: oracledb.Error) -> bool:
    """True when the failure means 'view not visible / no privilege' (not transient)."""
    text = str(exc).upper()
    return "ORA-00942" in text or "ORA-01031" in text  # table/view missing, or insufficient privileges


def extract_segment_access(owner: str | None = None) -> list[dict[str, Any]]:
    """Extract per-table read counts from V$SEGMENT_STATISTICS.

    Returns:
        Normalized rows ``{owner, table_name, logical_reads, physical_reads,
        row_hash}``. Returns an empty list (with an activation hint logged) when
        SYSADM lacks access to the view — the signal is then simply disabled.
    """
    settings = get_settings()
    effective_owner = (owner or settings.oracle_owner).upper().strip()
    client = OracleClient(settings=settings)

    try:
        logger.info("Starting Oracle segment-access extraction for owner={}", effective_owner)
        raw_rows = client.fetch_all(sql=SEGMENT_ACCESS_QUERY, params={"owner": effective_owner})
    except oracledb.Error as exc:
        if _is_access_denied(exc):
            logger.warning(
                "Segment-access signal DISABLED: SYSADM cannot read V$SEGMENT_STATISTICS "
                "(ORA-00942/01031). To enable a real read-frequency signal, ask a DBA to run: {}",
                GRANT_HINT.format(owner=effective_owner),
            )
            return []
        logger.exception("Segment-access extraction failed (non-permission error)")
        raise

    extracted: list[dict[str, Any]] = []
    for row in raw_rows:
        normalized = {str(k).lower(): v for k, v in row.items()}
        normalized["row_hash"] = compute_row_hash(normalized)
        extracted.append(normalized)

    logger.info("Segment-access extraction completed: {} table(s) with read stats", len(extracted))
    return extracted


def main() -> None:
    """Manual run for local validation (prints whether the signal is available)."""
    configure_logging()
    rows = extract_segment_access()
    if rows:
        logger.info("Access signal AVAILABLE — sample: {}", rows[:3])
    else:
        logger.info("Access signal UNAVAILABLE (no grant) — downstream rules stay inert.")


if __name__ == "__main__":
    main()
