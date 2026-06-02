"""Unit tests for RawOracleLoader pure helpers (no DB connection)."""

import pytest

from src.load.load_raw_oracle import ALLOWED_TABLES, RawOracleLoader


@pytest.fixture
def loader():
    # Pure helpers under test never touch the client.
    return RawOracleLoader(postgres_client=None)


def test_normalize_table_name_plain_and_qualified(loader):
    assert loader._normalize_table_name("table_catalog") == "table_catalog"
    assert loader._normalize_table_name("raw_oracle.column_catalog") == "column_catalog"
    assert loader._normalize_table_name("SEGMENT_ACCESS") == "segment_access"


def test_normalize_table_name_rejects_unknown(loader):
    with pytest.raises(ValueError):
        loader._normalize_table_name("evil_table")


def test_resolve_columns_excludes_run_id_and_lowercases():
    rows = [{"RecName": "X", "run_id": 9, "Field": 1}]
    cols = RawOracleLoader._resolve_columns(rows)
    assert "run_id" not in cols
    assert "recname" in cols
    assert "field" in cols


def test_resolve_columns_empty_raises():
    with pytest.raises(ValueError):
        RawOracleLoader._resolve_columns([{"run_id": 1}])


def test_build_batch_params_adds_run_id():
    rows = [{"recname": "A"}, {"recname": "B"}]
    params = RawOracleLoader._build_batch_params(rows, ["recname"], run_id=7)
    assert params == [
        {"run_id": 7, "recname": "A"},
        {"run_id": 7, "recname": "B"},
    ]


def test_segment_access_is_allowed():
    assert "segment_access" in ALLOWED_TABLES
