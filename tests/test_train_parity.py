"""Guard: the production trainer must reuse the inference feature order.

This is the structural safeguard against the train/inference mismatch class of
bug — both paths derive the numeric matrix from the same builder/order.
"""

from src.transform.score_business_domain import _build_numeric_values
from src.ml.train_production_classifier import _numeric_feature_order


def test_trainer_feature_order_matches_inference():
    probe = {"technical_name": "", "source_ref": "", "column_names_text": ""}
    inference_order = list(_build_numeric_values(probe).keys())
    assert _numeric_feature_order() == inference_order
    assert len(inference_order) == 129
