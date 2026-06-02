"""Tests for the defensive segment-access extractor helpers."""

import oracledb

from src.extract.oracle.extract_segment_access import _is_access_denied, compute_row_hash


def test_is_access_denied_detects_missing_view():
    err = oracledb.DatabaseError("ORA-00942: table or view does not exist")
    assert _is_access_denied(err) is True


def test_is_access_denied_detects_insufficient_privileges():
    err = oracledb.DatabaseError("ORA-01031: insufficient privileges")
    assert _is_access_denied(err) is True


def test_is_access_denied_false_for_transient_error():
    err = oracledb.DatabaseError("ORA-12170: TNS:Connect timeout occurred")
    assert _is_access_denied(err) is False


def test_compute_row_hash_is_deterministic_and_sensitive():
    row = {"owner": "SYSADM", "table_name": "X", "logical_reads": 5}
    assert compute_row_hash(row) == compute_row_hash(dict(row))
    assert compute_row_hash(row) != compute_row_hash({**row, "logical_reads": 6})
