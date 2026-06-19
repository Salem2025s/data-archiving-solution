"""Standalone inference for the XLM-RoBERTa v3 business-domain classifier.

v3 vs v1:
  * feature gating (numeric features modulate text embedding);
  * Focal Loss (gamma=2.0) during training;
  * per-class temperature calibration (7 temperatures, baked into ONNX `probs`);
  * per-class decision offsets (SLA-oriented) applied to the logits;
  * [TYPES] section in input text (column_type_signature_text).

IMPORTANT decision rule (per-class temperature changes the argmax!):
    label      = argmax(logits + offsets)          # NOT argmax(probs)
    confidence = probs[label]                       # calibrated per-class prob
The ONNX graph exposes both `logits` (raw) and `probs` (= softmax(logits / T_k)).

No PyTorch required — runs the ONNX graph with onnxruntime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from features import (
    CLASS_LABELS,
    NUMERIC_FEATURE_NAMES,
    REGULATED_LABELS,
    build_input_text,
    build_numeric_vector,
)

HERE = Path(__file__).resolve().parent
DEFAULT_ARTIFACTS = HERE / "artifacts"
MAX_LENGTH = 256


class DomainClassifier:
    def __init__(self, artifacts_dir: str | Path = DEFAULT_ARTIFACTS,
                 apply_offsets: bool = False, providers=None):
        artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir = artifacts_dir

        self.class_labels = json.loads((artifacts_dir / "class_labels.json").read_text(encoding="utf-8"))["classes"]
        assert self.class_labels == CLASS_LABELS, "class label order mismatch"

        sp = np.load(artifacts_dir / "scaler_params.npz")
        self.scaler_mean = sp["mean"].astype(np.float32)
        self.scaler_scale = sp["scale"].astype(np.float32)
        assert self.scaler_mean.shape[0] == len(NUMERIC_FEATURE_NAMES)

        # per-class temperatures (informational; already baked into ONNX `probs`)
        self.temperatures = json.loads((artifacts_dir / "temperatures.json").read_text(encoding="utf-8"))["temperatures"]

        # per-class decision offsets: label = argmax(logits + offsets)
        self.apply_offsets = apply_offsets
        off_path = artifacts_dir / "decision_offsets.json"
        if apply_offsets and off_path.exists():
            self.offsets = np.asarray(json.loads(off_path.read_text(encoding="utf-8"))["decision_offsets"], dtype=np.float32)
        else:
            self.offsets = np.zeros(len(self.class_labels), dtype=np.float32)

        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(str(artifacts_dir / "tokenizer"))

        if providers is None:
            providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(artifacts_dir / "model.onnx"), providers=providers)

    def _encode(self, rows: list[dict]):
        texts = [build_input_text(r) for r in rows]
        enc = self.tokenizer(texts, padding="max_length", truncation=True,
                             max_length=MAX_LENGTH, return_tensors="np")
        raw_num = np.stack([build_numeric_vector(r) for r in rows]).astype(np.float32)
        num = (raw_num - self.scaler_mean) / self.scaler_scale
        return (enc["input_ids"].astype(np.int64), enc["attention_mask"].astype(np.int64),
                num.astype(np.float32))

    def _run(self, rows: list[dict]):
        input_ids, attention_mask, num = self._encode(rows)
        logits, probs = self.session.run(
            ["logits", "probs"],
            {"input_ids": input_ids, "attention_mask": attention_mask, "num_features": num})
        return logits, probs

    def predict(self, rows: dict | list[dict]) -> dict | list[dict]:
        single = isinstance(rows, dict)
        rows_l = [rows] if single else list(rows)
        logits, probs = self._run(rows_l)
        labels = (logits + self.offsets).argmax(axis=1)   # decision = argmax(logits + offsets)
        results = []
        for i, k in enumerate(labels):
            k = int(k)
            results.append({
                "label": self.class_labels[k],
                "label_index": k,
                "confidence": float(probs[i, k]),         # calibrated per-class probability
                "probs": {self.class_labels[j]: float(probs[i, j]) for j in range(len(self.class_labels))},
                "review_required": self.class_labels[k] in REGULATED_LABELS and float(probs[i, k]) < 0.60,
            })
        return results[0] if single else results


if __name__ == "__main__":
    clf = DomainClassifier()
    demo = [
        {"technical_name": "PS_VENDOR_ADDR", "source_ref": "AP",
         "column_names": "vendor_id address1 city",
         "column_semantics": "VENDOR_ID:reference_identifier|ADDRESS1:postal_location",
         "field_count": 12, "numeric_field_count": 3, "row_count": 5000, "size_mb": 1.2},
        {"technical_name": "PS_GL_ACCOUNT", "source_ref": "GL",
         "column_names": "account ledger amount currency_cd",
         "column_semantics": "ACCOUNT:reference_identifier|AMOUNT:financial_amount",
         "field_count": 18, "numeric_field_count": 8, "row_count": 250000, "size_mb": 40.0},
    ]
    for r, o in zip(demo, clf.predict(demo)):
        print(f"{r['technical_name']:16s} -> {o['label']:24s} conf={o['confidence']:.3f}")
