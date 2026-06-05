"""Tests for src/ml/model_reliability.py.

Guards the statistical invariants of the reliability monitoring:
- ECE formula (weighted mean absolute gap)
- Jensen-Shannon divergence properties (symmetry, zero on identical dists)
- Calibration report structure and SLA evaluation
- No DB dependency: all tests use stubs or in-memory data.
"""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile

import pytest

from src.ml.model_reliability import (
    RECALL_SLA,
    _compute_ece,
    _js_divergence,
    evaluate_calibration_with_gold,
)


# ---------------------------------------------------------------------------
# _compute_ece
# ---------------------------------------------------------------------------

def test_ece_perfect_calibration():
    bands = [{"n": 100, "mean_conf": 0.80, "accuracy": 0.80}]
    assert _compute_ece(bands) == 0.0


def test_ece_uniform_overconfidence():
    # conf=0.90, acc=0.60 → |0.90-0.60| = 0.30 weighted by 1.0
    bands = [{"n": 200, "mean_conf": 0.90, "accuracy": 0.60}]
    assert abs(_compute_ece(bands) - 0.30) < 1e-6


def test_ece_multi_band_weighted():
    # band A: n=100, gap=0.10 ; band B: n=300, gap=0.20
    # ECE = (100*0.10 + 300*0.20) / 400 = 70/400 = 0.175
    bands = [
        {"n": 100, "mean_conf": 0.80, "accuracy": 0.70},
        {"n": 300, "mean_conf": 0.90, "accuracy": 0.70},
    ]
    assert abs(_compute_ece(bands) - 0.175) < 1e-6


def test_ece_empty_bands():
    assert _compute_ece([]) == 0.0


# ---------------------------------------------------------------------------
# _js_divergence
# ---------------------------------------------------------------------------

def test_js_identical_distributions_is_zero():
    d = {"A": 0.5, "B": 0.3, "C": 0.2}
    assert _js_divergence(d, d) < 1e-6


def test_js_symmetric():
    p = {"A": 0.7, "B": 0.3}
    q = {"A": 0.4, "B": 0.6}
    assert abs(_js_divergence(p, q) - _js_divergence(q, p)) < 1e-9


def test_js_in_0_1_range():
    p = {"A": 1.0, "B": 0.0}
    q = {"A": 0.0, "B": 1.0}
    js = _js_divergence(p, q)
    assert 0.0 <= js <= 1.0


def test_js_missing_domain_handled():
    # q has no 'C' domain — should not raise
    p = {"A": 0.6, "B": 0.2, "C": 0.2}
    q = {"A": 0.5, "B": 0.5}
    js = _js_divergence(p, q)
    assert 0.0 <= js <= 1.0


# ---------------------------------------------------------------------------
# evaluate_calibration_with_gold
# ---------------------------------------------------------------------------

def _write_human_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _make_rows(
    n_correct: int, n_wrong: int, confidence: float, domain: str, model_pred: str | None = None
) -> list[dict]:
    pred = model_pred or domain
    rows = []
    for _ in range(n_correct):
        rows.append({
            "asset_id": len(rows), "technical_name": "T",
            "source_ref": "S", "column_names": "",
            "column_semantics": "", "business_domain_predicted": pred,
            "business_domain_alt": "Other", "confidence": confidence,
            "confidence_band": "high" if confidence >= 0.85 else "medium",
            "review_required": False, "model_version": "v1",
            "human_label": domain, "human_notes": "",
        })
    for _ in range(n_wrong):
        rows.append({
            "asset_id": len(rows), "technical_name": "T",
            "source_ref": "S", "column_names": "",
            "column_semantics": "", "business_domain_predicted": "Other",
            "business_domain_alt": "Other", "confidence": confidence,
            "confidence_band": "high" if confidence >= 0.85 else "medium",
            "review_required": False, "model_version": "v1",
            "human_label": domain, "human_notes": "",
        })
    return rows


def test_evaluate_perfect_recall_no_sla_violation():
    rows = _make_rows(100, 0, 0.95, "Finance & Contrôle")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        tmppath = tmp.name
    _write_human_csv(tmppath, rows)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
        outpath = out.name
    try:
        r = evaluate_calibration_with_gold([tmppath], output_json=outpath)
        assert r["overall_sla_ok"] is True
        assert r["sla_violations"] == []
        fc = r["recall_by_domain"].get("Finance & Contrôle", {})
        assert fc["recall"] == 1.0
    finally:
        os.unlink(tmppath); os.unlink(outpath)


def test_evaluate_sla_violation_detected():
    # Finance recall = 50 % < SLA 0.90
    rows = _make_rows(50, 50, 0.90, "Finance & Contrôle")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmppath = tmp.name
    _write_human_csv(tmppath, rows)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
        outpath = out.name
    try:
        r = evaluate_calibration_with_gold([tmppath], output_json=outpath)
        assert r["overall_sla_ok"] is False
        assert any("Finance" in v for v in r["sla_violations"])
    finally:
        os.unlink(tmppath); os.unlink(outpath)


def test_evaluate_ece_overconfident_model():
    # conf=0.95, acc=0.60 → large positive gap → ECE high
    rows = _make_rows(60, 40, 0.95, "IT & Sécurité")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmppath = tmp.name
    _write_human_csv(tmppath, rows)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
        outpath = out.name
    try:
        r = evaluate_calibration_with_gold([tmppath], output_json=outpath)
        assert r["ece"] > 0.05  # over-confidence detected
        assert r["ece_status"] in ("WARNING", "CRITICAL")
    finally:
        os.unlink(tmppath); os.unlink(outpath)


def test_evaluate_json_output_written():
    rows = _make_rows(80, 20, 0.80, "RH")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmppath = tmp.name
    _write_human_csv(tmppath, rows)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
        outpath = out.name
    try:
        evaluate_calibration_with_gold([tmppath], output_json=outpath)
        data = json.loads(open(outpath, encoding="utf-8").read())
        assert "ece" in data
        assert "recall_by_domain" in data
        assert "calibration_bands" in data
    finally:
        os.unlink(tmppath); os.unlink(outpath)


def test_evaluate_empty_input_returns_empty():
    r = evaluate_calibration_with_gold(["nonexistent_file.csv"])
    assert r == {}


# ---------------------------------------------------------------------------
# RECALL_SLA config
# ---------------------------------------------------------------------------

def test_recall_sla_covers_all_regulated_domains():
    regulated = {"Finance & Contrôle", "RH", "Achats & Fournisseurs", "Ventes & Clients"}
    assert regulated.issubset(set(RECALL_SLA))


def test_recall_sla_values_are_in_valid_range():
    for domain, sla in RECALL_SLA.items():
        assert 0.0 < sla <= 1.0, f"SLA for {domain} out of range: {sla}"
