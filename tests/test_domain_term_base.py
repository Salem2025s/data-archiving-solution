"""Consistency tests for the keyword term base."""

from src.ml.domain_term_base import DOMAIN_TERMS, KEYWORD_TO_LABEL

PRODUCTION_LABELS = {
    "Finance & Contrôle",
    "RH",
    "IT & Sécurité",
    "Achats & Fournisseurs",
    "Ventes & Clients",
    "Supply Chain / Logistique / Production",
}


def test_domain_terms_keys_are_known_in_label_map():
    assert set(DOMAIN_TERMS).issubset(set(KEYWORD_TO_LABEL))


def test_label_map_targets_only_production_labels():
    assert set(KEYWORD_TO_LABEL.values()).issubset(PRODUCTION_LABELS)


def test_no_empty_term_lists():
    for domain, terms in DOMAIN_TERMS.items():
        assert terms, f"domain '{domain}' has no terms"
        assert all(isinstance(t, str) and t for t in terms)
