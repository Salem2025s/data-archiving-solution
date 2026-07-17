"""Unit tests for the scoring feature-builders — the riskiest code path.

Includes the regression test for the train/inference mismatch fix: engineered
text features (shape, prefix, keyword counts) MUST be computed on normalized text.
"""

from src.transform import score_business_domain as sbd


# --- pure helpers ----------------------------------------------------------

def test_normalize_text():
    assert sbd.normalize_text("PS_GL_ACCOUNT") == "ps gl account"
    assert sbd.normalize_text("VCHR-ACCTG.LINE") == "vchr acctg line"
    assert sbd.normalize_text("A|B/C") == "a b c"
    assert sbd.normalize_text(None) == ""


def test_safe_div():
    assert sbd.safe_div(10, 2) == 5
    assert sbd.safe_div(1, 0) == 0.0


def test_extract_prefix():
    assert sbd.extract_prefix("PS_GL_ACCOUNT") == "GL"
    assert sbd.extract_prefix("SYSADM.PS_AP_VOUCHER") == "AP"
    assert sbd.extract_prefix(None) == ""


def test_parse_semantic_counts():
    counts = sbd._parse_semantic_counts(
        "c1:financial_amount|c2:person_identifier|c3:financial_amount"
    )
    assert counts["financial_amount"] == 2
    assert counts["person_identifier"] == 1
    assert len(sbd._parse_semantic_counts("")) == 0


# --- numeric feature matrix ------------------------------------------------

def test_build_numeric_values_feature_count_is_129():
    probe = {"technical_name": "", "source_ref": "", "column_names_text": ""}
    assert len(sbd._build_numeric_values(probe)) == 129


def test_engineered_features_computed_on_NORMALIZED_text():
    """REGRESSION (train/inference fix): shape/keyword features use normalized text.

    'PS_GL_ACCOUNT' -> 'ps gl account': 'gl'/'account' match the finance keywords
    via word boundaries, and the underscore/upper counts collapse to zero. On RAW
    text the underscores would break \\bgl\\b (the bug we fixed).
    """
    row = {
        "technical_name": "PS_GL_ACCOUNT",
        "source_ref": "PS_GL_ACCOUNT",
        "column_names_text": "",
        "column_value_semantics_text": "",
    }
    vals = sbd._build_numeric_values(row)
    assert vals["finance_keyword_count"] >= 1
    assert vals["has_finance_keyword"] == 1.0
    assert vals["technical_name_underscore_count"] == 0.0
    assert vals["technical_name_upper_ratio"] == 0.0


def test_semantic_features_present():
    row = {
        "technical_name": "T", "source_ref": "T", "column_names_text": "",
        "column_value_semantics_text": "c1:financial_amount|c2:financial_amount",
    }
    vals = sbd._build_numeric_values(row)
    assert vals["sem_financial_amount"] == 2.0
    assert vals["ratio_financial_amount"] > 0.0


# --- keyword pre-classification -------------------------------------------

def test_keyword_classify_finance_dominant():
    row = {
        "technical_name": "X", "source_ref": "Y",
        "column_names_text": "LEDGER|AMOUNT|TAX|INVOICE",
        "column_value_semantics_text": "",
    }
    result = sbd._keyword_classify(row)
    assert result is not None
    label, _alt, confidence = result
    assert label == "Finance & Contrôle"
    # Confiance graduée (plus de valeur fixe 0.95) : bornée et jamais une certitude.
    assert sbd._KEYWORD_RULE_BASE_CONFIDENCE <= confidence <= sbd._KEYWORD_RULE_MAX_CONFIDENCE


def test_keyword_classify_ambiguous_returns_none():
    row = {
        "technical_name": "ZZTMP", "source_ref": "ZZTMP",
        "column_names_text": "COL1|COL2|DATA",
        "column_value_semantics_text": "",
    }
    assert sbd._keyword_classify(row) is None


# --- confidence banding + review flags ------------------------------------

def test_confidence_band():
    assert sbd._confidence_band(0.90) == "high"
    assert sbd._confidence_band(0.85) == "high"
    assert sbd._confidence_band(0.70) == "medium"
    assert sbd._confidence_band(0.60) == "medium"
    assert sbd._confidence_band(0.50) == "low"
    assert sbd._confidence_band(None) == "unknown"


def test_review_flags_low_confidence():
    req, reason = sbd._review_flags("Finance & Contrôle", "low", 0.4, 0.1, 0.05)
    assert req is True and "low_model_confidence" in reason


def test_review_flags_predicted_other():
    req, reason = sbd._review_flags("Other", "high", 0.9, 0.05, 0.05)
    assert req is True and "predicted_other" in reason


def test_review_flags_clean_high_confidence():
    req, reason = sbd._review_flags("Finance & Contrôle", "high", 0.9, 0.2, 0.05)
    assert req is False and reason is None


def test_review_flags_close_top2():
    req, reason = sbd._review_flags("Finance & Contrôle", "high", 0.50, 0.48, 0.05)
    assert req is True and "close_top2_scores" in reason
