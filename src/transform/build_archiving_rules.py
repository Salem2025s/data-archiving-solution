"""Populate serving.dim_archiving_policy and refresh mv_archiving_recommendation.

Data-driven archiving rules engine (section D). The recommended strategy for
each asset is decided in the materialized view from four concrete dimensions:
volume (size_mb), ancienneté (age_days from last_analyzed), sensibilité
(PII / financial semantics) and dépendances (lineage_out_count). The
archival_candidate_score is kept for reference but is NOT the decision driver
because it does not differentiate assets in the current run (term_count=0).
"""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

UPSERT_SQL = """
INSERT INTO serving.dim_archiving_policy
    (strategy_code, strategy_label, description, handling, retention_years, priority)
VALUES
    (:code, :label, :description, :handling, :retention_years, :priority)
ON CONFLICT (strategy_code) DO UPDATE SET
    strategy_label  = EXCLUDED.strategy_label,
    description     = EXCLUDED.description,
    handling        = EXCLUDED.handling,
    retention_years = EXCLUDED.retention_years,
    priority        = EXCLUDED.priority
"""

POLICIES: list[dict[str, object]] = [
    {
        "code": "NON_APPLICABLE",
        "label": "Non applicable",
        "description": "Objet logique PeopleSoft sans donnée physique (vue, sous-record, record dérivé ou de travail).",
        "handling": "Aucune action d'archivage — l'objet n'occupe aucun stockage physique.",
        "retention_years": None,
        "priority": 0,
    },
    {
        "code": "CONSERVATION_CRITIQUE",
        "label": "Conservation critique",
        "description": "Objet fortement référencé (≥ 10 dépendants directs). Pilier structurel de l'ERP.",
        "handling": "Conserver en stockage actif — ne jamais archiver. Archiver casserait les objets dépendants.",
        "retention_years": None,
        "priority": 1,
    },
    {
        "code": "ARCHIVAGE_CHIFFRE",
        "label": "Archivage chiffré",
        "description": "Données personnelles (PII) anciennes (> 1 an sans analyse). Soumises au RGPD.",
        "handling": "Déplacer vers un stockage froid avec chiffrement au repos. Tracer la durée de rétention légale.",
        "retention_years": 7,
        "priority": 2,
    },
    {
        "code": "CONSERVATION_SECURISEE",
        "label": "Conservation sécurisée",
        "description": "Données personnelles (PII) actives ou récentes.",
        "handling": "Conserver en stockage actif avec contrôle d'accès renforcé et journalisation.",
        "retention_years": None,
        "priority": 3,
    },
    {
        "code": "CONSERVATION_REGLEMENTAIRE",
        "label": "Conservation réglementaire",
        "description": "Donnée d'un domaine réglementé (Finance, RH, Achats, Ventes) encore dans sa fenêtre de rétention légale.",
        "handling": "Conserver en stockage actif jusqu'à expiration de la rétention légale du domaine. Ne pas archiver à froid ni purger (risque de non-conformité). Réévaluer ensuite.",
        "retention_years": None,  # plancher piloté par serving.dim_domain_retention
        "priority": 3,
    },
    {
        "code": "ARCHIVAGE_FROID",
        "label": "Archivage à froid",
        "description": "Données anciennes non analysées depuis plus de 3 ans, peu sollicitées.",
        "handling": "Déplacer vers stockage froid (object storage S3-compatible ou bande). Restauration sur demande.",
        "retention_years": 10,
        "priority": 4,
    },
    {
        "code": "COMPRESSION",
        "label": "Compression / externalisation",
        "description": "Données moyennement anciennes (> 1 an, ou > 3 mois et volumineuses).",
        "handling": "Compression en place (Oracle Advanced Compression) ou externalisation partielle.",
        "retention_years": 5,
        "priority": 5,
    },
    {
        "code": "A_EVALUER",
        "label": "À évaluer",
        "description": "Volume important mais ancienneté indéterminée (statistiques Oracle absentes).",
        "handling": "Analyse manuelle requise : rafraîchir les statistiques Oracle puis re-scorer.",
        "retention_years": None,
        "priority": 6,
    },
    {
        "code": "CONSERVATION",
        "label": "Conservation",
        "description": "Données récentes ou faible potentiel d'archivage.",
        "handling": "Conserver en stockage actif. Réévaluer au prochain run.",
        "retention_years": None,
        "priority": 7,
    },
]

UPSERT_RETENTION_SQL = """
INSERT INTO serving.dim_domain_retention
    (domain_label, min_retention_years, regulated, retention_basis)
VALUES
    (:domain_label, :min_retention_years, :regulated, :retention_basis)
ON CONFLICT (domain_label) DO UPDATE SET
    min_retention_years = EXCLUDED.min_retention_years,
    regulated           = EXCLUDED.regulated,
    retention_basis     = EXCLUDED.retention_basis
"""

# Planchers de rétention légale/métier par domaine (FR, valeurs par défaut configurables).
# Rendent le DOMAINE acteur de la décision d'archivage : un domaine réglementé dans sa
# fenêtre de rétention n'est pas archivable à froid (-> CONSERVATION_REGLEMENTAIRE).
DOMAIN_RETENTION: list[dict[str, object]] = [
    {"domain_label": "Finance & Contrôle", "min_retention_years": 10, "regulated": True,
     "retention_basis": "Pièces comptables — Code de commerce (FR) art. L123-22 : 10 ans"},
    {"domain_label": "Ventes & Clients", "min_retention_years": 10, "regulated": True,
     "retention_basis": "Factures clients : 10 ans (Code de commerce)"},
    {"domain_label": "Achats & Fournisseurs", "min_retention_years": 10, "regulated": True,
     "retention_basis": "Factures / contrats fournisseurs : 10 ans"},
    {"domain_label": "RH", "min_retention_years": 5, "regulated": True,
     "retention_basis": "Bulletins de paie / contrats : 5 ans min. (Code du travail) ; certains documents bien plus"},
    {"domain_label": "Supply Chain / Logistique / Production", "min_retention_years": 3, "regulated": False,
     "retention_basis": "Documents logistiques / production : ~3 ans (usage)"},
    {"domain_label": "IT & Sécurité", "min_retention_years": 1, "regulated": False,
     "retention_basis": "Logs techniques : ~1 an (rétention courte)"},
    {"domain_label": "Other", "min_retention_years": 3, "regulated": False,
     "retention_basis": "Défaut prudent (domaine non rattaché)"},
]


def build_archiving_rules() -> dict[str, int]:
    """Upsert archiving policies and refresh the recommendation MV."""
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    try:
        logger.info("Building archiving rules ({} policies)", len(POLICIES))

        logger.info("Step 1/3 — upserting serving.dim_archiving_policy")
        for policy in POLICIES:
            pg.execute(UPSERT_SQL, policy)

        logger.info("Step 2/3 — upserting serving.dim_domain_retention (rétention par domaine)")
        for retention in DOMAIN_RETENTION:
            pg.execute(UPSERT_RETENTION_SQL, retention)

        logger.info("Step 3/3 — refreshing serving.mv_archiving_recommendation")
        pg.execute("REFRESH MATERIALIZED VIEW serving.mv_archiving_recommendation")

        reco_row = pg.fetch_one(
            "SELECT COUNT(*) AS n FROM serving.mv_archiving_recommendation"
        )
        reco_count = int(reco_row["n"]) if reco_row else 0

        logger.info("archiving rules built: {} asset recommendation(s)", reco_count)
        return {"policy_count": len(POLICIES), "recommendation_rows": reco_count}

    except Exception:
        logger.exception("Failed building archiving rules")
        raise


def main() -> None:
    """Run local test for build_archiving_rules."""
    configure_logging()
    result = build_archiving_rules()
    logger.info("Manual run successful. result={}", result)


if __name__ == "__main__":
    main()
