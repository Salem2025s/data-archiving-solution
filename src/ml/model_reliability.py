"""Model reliability monitoring (Phase 1).

Three production-grade quality signals computed after every scoring run:

1. **Calibration** — does confidence=0.90 really mean 90% correct?
   Measures ECE (Expected Calibration Error) and per-band accuracy gaps.
   An ECE > 0.05 on a reference sample warrants recalibration.

2. **Recall SLA by regulated domain** — before any archiving action is
   authorised on Finance/RH/Achats/Ventes, their recall must meet the
   configured minimum (default 0.90). Violations block the gate.

3. **Drift monitoring** — at each scoring run, a distribution snapshot is
   persisted to serving.model_drift_snapshot. JS divergence vs the
   reference distribution triggers an alert when it exceeds the threshold.

All results are stored in serving.model_quality_report (one row per run)
and exposed via serving.v_model_quality_latest for the dashboard.

Usage:
    from src.ml.model_reliability import compute_and_persist_quality_report
    report = compute_and_persist_quality_report(pg, run_id, model_version)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from src.connectors.postgres_client import PostgresClient

# ---------------------------------------------------------------------------
# SLA configuration — minimum recall per regulated domain before any
# archiving action may be approved. Raise via config / env if needed.
# ---------------------------------------------------------------------------
RECALL_SLA: dict[str, float] = {
    "Finance & Contrôle": 0.90,
    "RH": 0.90,
    "Achats & Fournisseurs": 0.90,
    "Ventes & Clients": 0.90,
}

# JS divergence threshold above which a DRIFT alert is raised.
DRIFT_JS_THRESHOLD: float = 0.05

# Confidence bands matching those in score_business_domain.py.
CONF_BANDS = [
    ("very_low",  0.00, 0.40),
    ("low",       0.40, 0.60),
    ("medium",    0.60, 0.85),
    ("high",      0.85, 1.01),
]

# ---------------------------------------------------------------------------
# DDL queries (tables created by 050_serving.sql — idempotent ALTER fallback)
# ---------------------------------------------------------------------------
_CREATE_QUALITY_REPORT = """
CREATE TABLE IF NOT EXISTS serving.model_quality_report (
    id              BIGSERIAL   PRIMARY KEY,
    run_id          INTEGER     NOT NULL,
    model_version   TEXT        NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_scored        INTEGER,
    -- Calibration
    ece             NUMERIC,    -- Expected Calibration Error (lower = better)
    calibration_json TEXT,      -- per-band {conf_mean, accuracy, n} as JSON
    -- Recall SLA
    sla_ok          BOOLEAN,    -- true if ALL regulated domains meet their SLA
    recall_json     TEXT,       -- per-domain {recall, n, sla, ok} as JSON
    -- Drift
    js_divergence   NUMERIC,    -- Jensen-Shannon vs reference distribution
    drift_alert     BOOLEAN,
    distribution_json TEXT,     -- current pred distribution as JSON
    -- Overall
    alerts_json     TEXT        -- list of alert strings
);
"""

_CREATE_DRIFT_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS serving.model_drift_snapshot (
    id              BIGSERIAL   PRIMARY KEY,
    run_id          INTEGER     NOT NULL UNIQUE,
    model_version   TEXT        NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_scored        INTEGER,
    distribution_json TEXT      -- {domain: fraction} as JSON
);
"""

_INSERT_QUALITY_REPORT = """
INSERT INTO serving.model_quality_report
    (run_id, model_version, computed_at, n_scored,
     ece, calibration_json,
     sla_ok, recall_json,
     js_divergence, drift_alert, distribution_json,
     alerts_json)
VALUES
    (:run_id, :model_version, :computed_at, :n_scored,
     :ece, :calibration_json,
     :sla_ok, :recall_json,
     :js_divergence, :drift_alert, :distribution_json,
     :alerts_json)
"""

_UPSERT_DRIFT_SNAPSHOT = """
INSERT INTO serving.model_drift_snapshot
    (run_id, model_version, captured_at, n_scored, distribution_json)
VALUES
    (:run_id, :model_version, :computed_at, :n_scored, :distribution_json)
ON CONFLICT (run_id) DO UPDATE SET
    model_version     = EXCLUDED.model_version,
    captured_at       = EXCLUDED.captured_at,
    n_scored          = EXCLUDED.n_scored,
    distribution_json = EXCLUDED.distribution_json
"""

_PRED_DISTRIBUTION_SQL = """
SELECT business_domain_predicted AS domain, COUNT(*) AS n
FROM serving.asset_business_domain_prediction
WHERE run_id = :run_id
GROUP BY business_domain_predicted
"""

_CONFIDENCE_DISTRIBUTION_SQL = """
SELECT
    business_domain_predicted AS domain,
    confidence,
    confidence_band
FROM serving.asset_business_domain_prediction
WHERE run_id = :run_id
"""

_REFERENCE_SNAPSHOT_SQL = """
SELECT distribution_json, n_scored
FROM serving.model_drift_snapshot
WHERE run_id < :run_id
ORDER BY run_id DESC
LIMIT 1
"""

_CREATE_QUALITY_VIEW = """
CREATE OR REPLACE VIEW serving.v_model_quality_latest AS
SELECT * FROM serving.model_quality_report
WHERE run_id = (SELECT MAX(run_id) FROM serving.model_quality_report);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_tables(pg: PostgresClient) -> None:
    for ddl in (_CREATE_QUALITY_REPORT, _CREATE_DRIFT_SNAPSHOT, _CREATE_QUALITY_VIEW):
        pg.execute(ddl)


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence between two label distributions (symmetric, 0–1)."""
    domains = sorted(set(p) | set(q))
    eps = 1e-10
    pv = np.array([p.get(d, 0.0) + eps for d in domains])
    qv = np.array([q.get(d, 0.0) + eps for d in domains])
    pv /= pv.sum(); qv /= qv.sum()
    m = 0.5 * (pv + qv)
    kl_pm = float(np.sum(pv * np.log(pv / m)))
    kl_qm = float(np.sum(qv * np.log(qv / m)))
    return round(0.5 * (kl_pm + kl_qm), 6)


def _compute_ece(band_data: list[dict[str, Any]]) -> float:
    """ECE from per-band stats {n, mean_conf, accuracy}."""
    total = sum(b["n"] for b in band_data)
    if total == 0:
        return 0.0
    ece = sum(b["n"] / total * abs(b["accuracy"] - b["mean_conf"]) for b in band_data)
    return round(ece, 4)


# ---------------------------------------------------------------------------
# Core: compute quality metrics from the DB for one scoring run
# ---------------------------------------------------------------------------

def compute_and_persist_quality_report(
    pg: PostgresClient,
    run_id: int,
    model_version: str,
) -> dict[str, Any]:
    """Compute calibration + SLA + drift for run_id and persist the results.

    Returns the quality report dict (same structure as the DB row).
    """
    _ensure_tables(pg)
    alerts: list[str] = []
    computed_at = datetime.now(timezone.utc)

    # --- Prediction distribution for this run ---
    rows = pg.fetch_all(_PRED_DISTRIBUTION_SQL, {"run_id": run_id})
    if not rows:
        logger.warning("No predictions found for run_id={} — skipping quality report", run_id)
        return {}

    total = sum(int(r["n"]) for r in rows)
    distribution = {r["domain"]: round(int(r["n"]) / total, 6) for r in rows}

    # --- Calibration (requires confidence values) ---
    conf_rows = pg.fetch_all(_CONFIDENCE_DISTRIBUTION_SQL, {"run_id": run_id})
    band_data: list[dict[str, Any]] = []
    for band_name, lo, hi in CONF_BANDS:
        band_confs = [
            float(r["confidence"]) for r in conf_rows
            if r["confidence"] is not None
            and lo <= float(r["confidence"]) < hi
        ]
        if band_confs:
            band_data.append({
                "band": band_name, "n": len(band_confs),
                "mean_conf": round(float(np.mean(band_confs)), 4),
                # accuracy unknown at inference time — stored as None, filled by eval step
                "accuracy": None,
            })

    ece = None  # computed by evaluate_calibration_with_gold() when gold available
    low_conf_pct = round(
        sum(b["n"] for b in band_data if b["band"] in ("very_low", "low")) / max(total, 1), 4
    )
    if low_conf_pct > 0.15:
        alerts.append(f"calibration:low_confidence_pct={low_conf_pct:.1%}")

    # --- Recall SLA (requires a reference eval — checked via existing eval reports) ---
    sla_results: dict[str, Any] = {}
    sla_ok = True
    for report_path in [
        "artifacts/human_eval_report_2.json",
        "artifacts/human_eval_report.json",
    ]:
        p = Path(report_path)
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        per_class = data.get("per_class", {})
        if not per_class:
            continue
        for domain, sla_thresh in RECALL_SLA.items():
            cls_data = per_class.get(domain, {})
            recall = cls_data.get("recall")
            n = int(cls_data.get("support", 0))
            if recall is None or n == 0:
                continue
            ok = float(recall) >= sla_thresh
            sla_results[domain] = {
                "recall": round(float(recall), 4),
                "n": n,
                "sla": sla_thresh,
                "ok": ok,
                "eval_source": report_path,
            }
            if not ok:
                sla_ok = False
                alerts.append(
                    f"sla_violation:{domain}:recall={recall:.3f}<{sla_thresh}"
                )
        break  # use most recent available report only

    if not sla_results:
        alerts.append("sla:no_reference_eval_available — SLA cannot be certified")
        sla_ok = False

    # --- Drift vs previous run ---
    ref_row = pg.fetch_one(_REFERENCE_SNAPSHOT_SQL, {"run_id": run_id})
    js_div = None
    drift_alert = False
    if ref_row and ref_row.get("distribution_json"):
        ref_dist = json.loads(ref_row["distribution_json"])
        js_div = _js_divergence(distribution, ref_dist)
        if js_div > DRIFT_JS_THRESHOLD:
            drift_alert = True
            alerts.append(f"drift:JS={js_div:.4f}>{DRIFT_JS_THRESHOLD}")
            logger.warning(
                "DRIFT ALERT run_id={}: JS divergence={:.4f} exceeds threshold={} vs previous run",
                run_id, js_div, DRIFT_JS_THRESHOLD,
            )

    # --- Persist snapshot + report ---
    pg.execute(_UPSERT_DRIFT_SNAPSHOT, {
        "run_id": run_id, "model_version": model_version,
        "computed_at": computed_at, "n_scored": total,
        "distribution_json": json.dumps(distribution, ensure_ascii=False),
    })

    report: dict[str, Any] = {
        "run_id": run_id, "model_version": model_version,
        "computed_at": computed_at, "n_scored": total,
        "ece": ece,
        "calibration_json": json.dumps(band_data, ensure_ascii=False),
        "sla_ok": sla_ok,
        "recall_json": json.dumps(sla_results, ensure_ascii=False),
        "js_divergence": js_div,
        "drift_alert": drift_alert,
        "distribution_json": json.dumps(distribution, ensure_ascii=False),
        "alerts_json": json.dumps(alerts, ensure_ascii=False),
    }
    pg.execute(_INSERT_QUALITY_REPORT, report)

    if alerts:
        logger.warning("Quality report run_id={} — {} alert(s): {}", run_id, len(alerts), alerts)
    else:
        logger.info("Quality report run_id={} OK (no alerts)", run_id)

    logger.info(
        "run_id={} | n={} | low_conf={:.1%} | sla_ok={} | JS_div={} | alerts={}",
        run_id, total, low_conf_pct, sla_ok, js_div, alerts,
    )
    return report


# ---------------------------------------------------------------------------
# Calibration evaluation against a reference sample (call after label validation)
# ---------------------------------------------------------------------------

def evaluate_calibration_with_gold(
    human_csv_paths: list[str],
    output_json: str = "artifacts/calibration_report.json",
) -> dict[str, Any]:
    """Compute per-band calibration accuracy from human-annotated CSVs.

    Writes a JSON report and returns the dict. Call this after each
    human annotation batch to update the ECE measurement.
    """
    try:
        import pandas as pd  # local import — optional dep in pure-DB contexts
    except ImportError:
        logger.error("pandas required for calibration evaluation")
        return {}

    frames = []
    for p in human_csv_paths:
        if not Path(p).exists():
            logger.warning("Human CSV not found: {}", p)
            continue
        frames.append(pd.read_csv(p, encoding="utf-8-sig"))
    if not frames:
        return {}

    h = pd.concat(frames, ignore_index=True)
    h["human_label"] = h["human_label"].astype("string").fillna("").str.strip()
    scored = h[(h["human_label"] != "") & (h["human_label"] != "Ambigu/Inconnu")].copy()
    if scored.empty:
        return {}

    scored["correct"] = scored["human_label"].astype(str) == scored["business_domain_predicted"].astype(str)
    scored["confidence"] = pd.to_numeric(scored["confidence"], errors="coerce")

    band_stats: list[dict[str, Any]] = []
    for band_name, lo, hi in CONF_BANDS:
        mask = (scored["confidence"] >= lo) & (scored["confidence"] < hi)
        sub = scored[mask]
        if len(sub) == 0:
            continue
        band_stats.append({
            "band": band_name, "lo": lo, "hi": hi,
            "n": int(len(sub)),
            "mean_conf": round(float(sub["confidence"].mean()), 4),
            "accuracy": round(float(sub["correct"].mean()), 4),
            "gap": round(float(sub["confidence"].mean() - sub["correct"].mean()), 4),
        })

    ece = _compute_ece(band_stats)

    # Recall by domain
    recall_by_domain: dict[str, Any] = {}
    for dom in sorted(scored["human_label"].unique()):
        sub = scored[scored["human_label"] == dom]
        recall_by_domain[dom] = {
            "n": int(len(sub)),
            "recall": round(float(sub["correct"].mean()), 4),
            "sla": RECALL_SLA.get(dom),
            "sla_ok": float(sub["correct"].mean()) >= RECALL_SLA.get(dom, 0.0),
        }

    sla_violations = [
        f"{d}: {v['recall']:.3f} < {v['sla']}"
        for d, v in recall_by_domain.items()
        if v["sla"] and not v["sla_ok"]
    ]

    report = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_scored": int(len(scored)),
        "ece": ece,
        "ece_status": "OK" if ece <= 0.05 else ("WARNING" if ece <= 0.15 else "CRITICAL"),
        "calibration_bands": band_stats,
        "recall_by_domain": recall_by_domain,
        "sla_violations": sla_violations,
        "overall_sla_ok": len(sla_violations) == 0,
    }

    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Calibration report: ECE={} ({}) | SLA violations: {}",
        ece, report["ece_status"], sla_violations or "none",
    )
    return report


# ---------------------------------------------------------------------------
# Active learning: export approval queue items for human annotation
# ---------------------------------------------------------------------------

_EXPORT_QUEUE_SQL = """
SELECT
    q.id AS queue_id, q.asset_id, q.run_id, q.technical_name, q.domain_label,
    q.recommended_strategy, q.confidence, q.confidence_band, q.review_reason,
    ml.source_system, ml.asset_type, ml.source_ref,
    ml.column_names_text, ml.column_type_signature_text,
    ml.column_value_semantics_text, ml.field_count,
    ml.row_count, ml.size_mb,
    '' AS human_label, '' AS human_notes
FROM serving.archiving_approval_queue q
JOIN processed.dataset_asset_ml ml
    ON ml.asset_id = q.asset_id AND ml.run_id = q.run_id
WHERE q.status = 'PENDING'
  AND q.run_id = :run_id
ORDER BY
    CASE
        WHEN q.review_reason LIKE 'domaine_reglemente%%' THEN 1
        WHEN q.confidence_band = 'low' THEN 2
        ELSE 3
    END,
    q.confidence ASC NULLS LAST
LIMIT :limit
"""


def export_queue_for_annotation(
    pg: PostgresClient,
    run_id: int,
    output_path: str,
    limit: int = 500,
) -> int:
    """Export PENDING queue items as a human-annotation CSV.

    Output format matches human_eval_sample*.csv (asset_id, technical_name,
    human_label, human_notes) so the existing evaluate_human_gold.py and
    train_production_classifier.py --human-csv pipeline consumes it directly.
    Sorted by criticality: regulated domains first, then lowest confidence.
    """
    try:
        import csv
    except ImportError:
        return 0

    rows = pg.fetch_all(_EXPORT_QUEUE_SQL, {"run_id": run_id, "limit": limit})
    if not rows:
        logger.info("No PENDING queue items for run_id={}", run_id)
        return 0

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        fieldnames = list(rows[0].keys()) if rows else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    logger.info("Exported {} queue items for annotation -> {}", len(rows), output_path)
    return len(rows)
