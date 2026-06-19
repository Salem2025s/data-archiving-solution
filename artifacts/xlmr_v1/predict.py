"""Standalone inference for the XLM-RoBERTa v1 business-domain classifier.

No PyTorch required — runs the calibrated ONNX graph with onnxruntime.

Usage
-----
    from predict import DomainClassifier
    clf = DomainClassifier()                       # loads ./artifacts by default
    out = clf.predict({
        "technical_name": "PS_VENDOR_ADDR",
        "source_ref": "AP",
        "column_names": "vendor_id address1 city",            # or column_names_text
        "column_semantics": "VENDOR_ID:reference_identifier|ADDRESS1:postal_location",
        # schema metrics (present in production; omit/None -> imputed to 0):
        "field_count": 12, "numeric_field_count": 3, "row_count": 5000, "size_mb": 1.2,
        # ... the other schema columns (see README)
    })
    print(out["label"], out["confidence"])

    # batch:
    outs = clf.predict([row1, row2, ...])

The ONNX ``probs`` output is ALREADY temperature-calibrated (T baked into the
graph), so ``out["probs"]`` are deployable probabilities.
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
    def __init__(self, artifacts_dir: str | Path = DEFAULT_ARTIFACTS, providers=None):
        artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir = artifacts_dir

        # 7-class order (sanity-checked against the vendored features module)
        self.class_labels = json.loads((artifacts_dir / "class_labels.json").read_text(encoding="utf-8"))["classes"]
        assert self.class_labels == CLASS_LABELS, "class label order mismatch"

        # StandardScaler params (mean_/scale_) — no sklearn dependency needed
        sp = np.load(artifacts_dir / "scaler_params.npz")
        self.scaler_mean = sp["mean"].astype(np.float32)
        self.scaler_scale = sp["scale"].astype(np.float32)
        assert self.scaler_mean.shape[0] == len(NUMERIC_FEATURE_NAMES)

        # tokenizer (fast tokenizer.json is self-contained; transformers used only
        # for tokenization — no torch required)
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(str(artifacts_dir / "tokenizer"))

        # ONNX runtime session (model.onnx must sit next to model.onnx.data)
        if providers is None:
            providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(artifacts_dir / "model.onnx"), providers=providers)

        # informational (T is already applied inside the graph's `probs` output)
        self.temperature = json.loads((artifacts_dir / "temperature.json").read_text())["temperature"]

    # -- internals ------------------------------------------------------------
    def _encode(self, rows: list[dict]):
        texts = [build_input_text(r) for r in rows]
        enc = self.tokenizer(
            texts, padding="max_length", truncation=True,
            max_length=MAX_LENGTH, return_tensors="np",
        )
        raw_num = np.stack([build_numeric_vector(r) for r in rows]).astype(np.float32)
        num = (raw_num - self.scaler_mean) / self.scaler_scale  # StandardScaler
        return (
            enc["input_ids"].astype(np.int64),
            enc["attention_mask"].astype(np.int64),
            num.astype(np.float32),
        )

    # -- public API -----------------------------------------------------------
    def predict_proba(self, rows: dict | list[dict]) -> np.ndarray:
        single = isinstance(rows, dict)
        rows = [rows] if single else list(rows)
        input_ids, attention_mask, num = self._encode(rows)
        logits, probs = self.session.run(
            ["logits", "probs"],
            {"input_ids": input_ids, "attention_mask": attention_mask, "num_features": num},
        )
        return probs[0] if single else probs

    def predict(self, rows: dict | list[dict]) -> dict | list[dict]:
        single = isinstance(rows, dict)
        probs = self.predict_proba(rows)
        probs2d = probs[None, :] if single else probs
        results = []
        for p in probs2d:
            k = int(p.argmax())
            results.append({
                "label": self.class_labels[k],
                "label_index": k,
                "confidence": float(p[k]),
                "probs": {self.class_labels[i]: float(p[i]) for i in range(len(self.class_labels))},
                "review_required": self.class_labels[k] in REGULATED_LABELS and float(p[k]) < 0.60,
            })
        return results[0] if single else results


if __name__ == "__main__":  # tiny smoke test
    clf = DomainClassifier()
    demo = [
        {"technical_name": "PS_VENDOR_ADDR", "source_ref": "AP",
         "column_names": "vendor_id address1 city",
         "column_semantics": "VENDOR_ID:reference_identifier|ADDRESS1:postal_location",
         "field_count": 12, "numeric_field_count": 3, "row_count": 5000, "size_mb": 1.2},
        {"technical_name": "PS_JOB", "source_ref": "HR",
         "column_names": "emplid jobcode deptid",
         "column_semantics": "EMPLID:user_identifier|JOBCODE:processing_identifier",
         "field_count": 20, "numeric_field_count": 5, "row_count": 100000, "size_mb": 8.0},
    ]
    for r, o in zip(demo, clf.predict(demo)):
        print(f"{r['technical_name']:16s} -> {o['label']:24s} conf={o['confidence']:.3f}")
