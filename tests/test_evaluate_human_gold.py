"""Tests for the reference-label evaluation metrics."""

import csv

from src.ml.evaluate_human_gold import evaluate

FIELDS = ["asset_id", "business_domain_predicted", "confidence_band",
          "review_required", "human_label"]


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_accuracy_and_counts(tmp_path):
    rows = [
        {"asset_id": 1, "business_domain_predicted": "RH", "confidence_band": "high",
         "review_required": False, "human_label": "RH"},
        {"asset_id": 2, "business_domain_predicted": "Finance & Contrôle", "confidence_band": "high",
         "review_required": False, "human_label": "Finance & Contrôle"},
        {"asset_id": 3, "business_domain_predicted": "RH", "confidence_band": "low",
         "review_required": True, "human_label": "Finance & Contrôle"},  # wrong
        {"asset_id": 4, "business_domain_predicted": "IT & Sécurité", "confidence_band": "high",
         "review_required": False, "human_label": "IT & Sécurité"},
    ]
    csv_path = tmp_path / "ann.csv"
    _write(csv_path, rows)
    rep = evaluate(input_path=str(csv_path), output_path=str(tmp_path / "rep.json"))
    assert rep["rows_scored"] == 4
    assert rep["accuracy"] == 0.75  # 3 correct / 4
    assert 0.0 <= rep["cohen_kappa_human_vs_model"] <= 1.0
    # calibration breakdown present
    assert "high" in rep["accuracy_by_confidence_band"]


def test_excludes_ambiguous_and_empty(tmp_path):
    rows = [
        {"asset_id": 1, "business_domain_predicted": "RH", "confidence_band": "high",
         "review_required": False, "human_label": "RH"},
        {"asset_id": 2, "business_domain_predicted": "RH", "confidence_band": "high",
         "review_required": False, "human_label": "Ambigu/Inconnu"},
        {"asset_id": 3, "business_domain_predicted": "RH", "confidence_band": "high",
         "review_required": False, "human_label": ""},  # not annotated
    ]
    csv_path = tmp_path / "ann.csv"
    _write(csv_path, rows)
    rep = evaluate(input_path=str(csv_path), output_path=str(tmp_path / "rep.json"))
    assert rep["rows_annotated"] == 2   # RH + Ambigu (empty excluded)
    assert rep["rows_ambiguous"] == 1
    assert rep["rows_scored"] == 1      # only the non-ambiguous RH
