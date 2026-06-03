"""Tests for the E3 Monte-Carlo ROI projection and the E2 growth estimator.

These guard the statistical invariants we rely on in the report:
- the projection is deterministic (seeded) and reproducible,
- the percentile band is ordered (P10 <= P50 <= P90),
- the growth estimator only trusts the OBSERVED CAGR when the snapshot series
  is long enough and actually growing — otherwise it falls back to the
  configured assumption.
"""

import numpy as np
import pytest

from src.transform import build_cost_analysis as bca
from src.transform.build_cost_analysis import _compute_projection, _estimate_growth


PARAMS = {
    "storage_cost_per_gb_per_year": 0.30,
    "cold_storage_cost_per_gb_year": 0.05,
    "implementation_cost_one_shot": 5000.0,
    "data_growth_rate_pct_per_year": 15.0,
    "data_growth_std_pct_per_year": 5.0,
}


class _StubPG:
    """Minimal PostgresClient stand-in: only fetch_all is used by _estimate_growth."""

    def __init__(self, sizes):
        # sizes: chronological TOTAL volumes (oldest first), as the SQL would return
        self._rows = [{"total_size_gb": s} for s in sizes]

    def fetch_all(self, sql, params=None):
        return self._rows


def _project(years=5):
    return _compute_projection(
        run_id=6,
        total_gb=1000.0,
        archivable_gb=400.0,
        params=PARAMS,
        years=years,
        growth_mean=0.15,
        growth_std=0.05,
        source="assumption",
    )


# --- _compute_projection ---------------------------------------------------

def test_projection_has_one_row_per_year_in_order():
    rows = _project(years=5)
    assert [r["year_offset"] for r in rows] == [0, 1, 2, 3, 4, 5]


def test_projection_percentile_band_is_ordered():
    for r in _project():
        assert r["net_p10"] <= r["net"] <= r["net_p90"]


def test_projection_breakeven_probability_is_a_probability():
    for r in _project():
        assert 0.0 <= r["breakeven_probability"] <= 1.0


def test_projection_cumulative_no_action_cost_is_non_decreasing():
    cumul = [r["cumul_no"] for r in _project()]
    assert cumul == sorted(cumul)


def test_projection_is_reproducible():
    """Same inputs -> byte-identical net curve (seeded RNG)."""
    a = [r["net"] for r in _project()]
    b = [r["net"] for r in _project()]
    assert a == b


def test_projection_propagates_growth_metadata():
    r = _project()[0]
    assert r["growth_mean_pct"] == 15.0
    assert r["growth_std_pct"] == 5.0
    assert r["growth_source"] == "assumption"
    assert r["n_simulations"] == bca.N_SIMULATIONS


def test_projection_savings_grow_over_the_horizon():
    """With archivable volume and positive growth, the median net saving at the
    end of the horizon exceeds the first year."""
    rows = _project()
    assert rows[-1]["net"] > rows[0]["net"]


# --- _estimate_growth ------------------------------------------------------

def test_growth_uses_observed_cagr_when_series_grows():
    # 100 -> 200 over 4 periods -> CAGR = 2^(1/4) - 1 ~= 0.1892
    pg = _StubPG([100.0, 120.0, 150.0, 175.0, 200.0])
    mean, std, source = _estimate_growth(pg, PARAMS)
    assert source == "observed"
    assert mean == pytest.approx(2.0 ** 0.25 - 1.0, rel=1e-6)
    assert std > 0


def test_growth_falls_back_to_assumption_when_too_few_points():
    pg = _StubPG([100.0])
    mean, std, source = _estimate_growth(pg, PARAMS)
    assert source == "assumption"
    assert mean == pytest.approx(0.15)
    assert std == pytest.approx(0.05)


def test_growth_falls_back_to_assumption_when_series_shrinks():
    # decreasing series -> non-positive CAGR -> not a reliable forward signal
    pg = _StubPG([200.0, 150.0, 120.0, 100.0])
    mean, std, source = _estimate_growth(pg, PARAMS)
    assert source == "assumption"
    assert mean == pytest.approx(0.15)


def test_growth_two_points_uses_assumed_std():
    pg = _StubPG([100.0, 130.0])
    mean, std, source = _estimate_growth(pg, PARAMS)
    assert source == "observed"
    assert mean == pytest.approx(0.30)  # single period CAGR = 130/100 - 1
    assert std == pytest.approx(0.05)   # <3 points -> assumed std
