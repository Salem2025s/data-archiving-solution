"""Populate serving.dim_domain and refresh domain-level materialized views.

Runs after the standard MV refreshes in flow_publish_serving. Idempotent:
dim_domain rows are upserted so descriptions can be updated on re-run.
"""

from __future__ import annotations

from loguru import logger

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

UPSERT_SQL = """
INSERT INTO serving.dim_domain
    (domain_label, domain_key, description, typical_objects, typical_bridge_keys)
VALUES
    (:label, :key, :description, :typical_objects, :typical_bridge_keys)
ON CONFLICT (domain_label) DO UPDATE SET
    domain_key          = EXCLUDED.domain_key,
    description         = EXCLUDED.description,
    typical_objects     = EXCLUDED.typical_objects,
    typical_bridge_keys = EXCLUDED.typical_bridge_keys
"""

DOMAINS: list[dict[str, str]] = [
    {
        "label": "Finance & Contrôle",
        "key": "finance",
        "description": (
            "Gestion de la comptabilité générale et analytique, de la trésorerie, "
            "de la budgétisation et du contrôle de gestion. Inclut les factures "
            "fournisseurs, les journaux GL, les budgets et les projets financiers."
        ),
        "typical_objects": "VOUCHER, LEDGER, BUDGET_HDR, PROJECT, JOURNAL_ENTRY, AP_PAYMENT, BANKACCOUNT, OPEN_ITEM",
        "typical_bridge_keys": "VOUCHER_ID, PROJECT_ID, BUSINESS_UNIT, LEDGER, ACCOUNTING_DT",
    },
    {
        "label": "IT & Sécurité",
        "key": "it",
        "description": (
            "Administration technique des accès, rôles, permissions et objets système "
            "PeopleSoft. Inclut la gestion des opérateurs, des listes de permissions "
            "et des définitions de workflow."
        ),
        "typical_objects": "PSOPRDEFN, ROLEDEFN, PERMISSIONLIST, PSACCESSLOG, PSCLASSDEFN, PSMSGCATALOG, PSPRCSRQST",
        "typical_bridge_keys": "OPRID, ROLENAME, CLASSID, PRCSNAME",
    },
    {
        "label": "Achats & Fournisseurs",
        "key": "procurement",
        "description": (
            "Gestion du cycle d'achat de bout en bout : demandes d'achat, commandes "
            "fournisseurs, réceptions, contrats et évaluation des fournisseurs."
        ),
        "typical_objects": "PO_HDR, PO_LINE, VENDOR, RECV_HDR, RECV_LN, CNTRCT_HDR, REQ_HDR, BIDREQ_HDR",
        "typical_bridge_keys": "PO_ID, VENDOR_ID, CONTRACT_NUM, RECEIVER_ID, REQ_ID, BUSINESS_UNIT",
    },
    {
        "label": "Supply Chain / Logistique / Production",
        "key": "supply_chain",
        "description": (
            "Gestion des stocks, des mouvements d'inventaire et de la demande. "
            "Inclut les articles, les niveaux de stocks, les transferts inter-sites "
            "et la planification des approvisionnements. Couvre également la logistique "
            "et la gestion de la production."
        ),
        "typical_objects": "INV_ITEMS, DEMAND_INF_INV, IN_DEMAND, MASTER_ITEM_TBL, MSR_HDR, PURCH_ITEM_ATTR",
        "typical_bridge_keys": "INV_ITEM_ID, BUSINESS_UNIT_IN, BUSINESS_UNIT_OUT, SHIP_ID, DEMAND_SOURCE",
    },
    {
        "label": "RH",
        "key": "hr",
        "description": (
            "Gestion des ressources humaines : données personnelles des employés, "
            "contrats, postes, rémunérations, avantages sociaux et gestion des congés."
        ),
        "typical_objects": "PERSONAL_DATA, JOB, EMPLOYMENT, COMPENSATION, LEAVE_ACCRUAL, HEALTH_PLAN, POSITION_DATA",
        "typical_bridge_keys": "EMPLID, EMPL_RCD, POSITION_NBR, JOBCODE, SETID",
    },
    {
        "label": "Ventes & Clients",
        "key": "sales",
        "description": (
            "Gestion de la relation client, des commandes de vente, de la facturation "
            "et du suivi des livraisons. Inclut les devis, commandes, factures et "
            "l'historique des paiements clients."
        ),
        "typical_objects": "CUSTOMER, ORDER_HDR, ORDER_LINE, BI_HDR, BI_LINE, CUST_ADDR, PRICE_LIST, ITEM",
        "typical_bridge_keys": "CUST_ID, ORDER_NO, INVOICE, SHIP_TO_CUST_ID, BILL_TO_CUST_ID",
    },
    {
        "label": "Other",
        "key": "other",
        "description": (
            "Assets non rattachés à un domaine métier principal. Regroupement par "
            "défaut pour les objets techniques, de configuration et les métadonnées "
            "système non classifiés."
        ),
        "typical_objects": "-",
        "typical_bridge_keys": "-",
    },
]


def build_serving_domain_model() -> dict[str, int]:
    """Upsert dim_domain and refresh mv_domain_profile + mv_domain_dependency."""
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    try:
        logger.info("Building serving domain model ({} domains)", len(DOMAINS))

        logger.info("Step 1/3 — upserting rows into serving.dim_domain")
        for domain in DOMAINS:
            pg.execute(
                UPSERT_SQL,
                {
                    "label": domain["label"],
                    "key": domain["key"],
                    "description": domain["description"],
                    "typical_objects": domain["typical_objects"],
                    "typical_bridge_keys": domain["typical_bridge_keys"],
                },
            )
        logger.info("serving.dim_domain upserted: {} row(s)", len(DOMAINS))

        logger.info("Step 2/3 — refreshing serving.mv_domain_profile")
        pg.execute("REFRESH MATERIALIZED VIEW serving.mv_domain_profile")

        logger.info("Step 3/3 — refreshing serving.mv_domain_dependency")
        pg.execute("REFRESH MATERIALIZED VIEW serving.mv_domain_dependency")

        profile_row = pg.fetch_one("SELECT COUNT(*) AS n FROM serving.mv_domain_profile")
        dep_row = pg.fetch_one("SELECT COUNT(*) AS n FROM serving.mv_domain_dependency")
        profile_count = int(profile_row["n"]) if profile_row else 0
        dep_count = int(dep_row["n"]) if dep_row else 0

        logger.info(
            "serving domain model built: {} profile row(s), {} dependency edge(s)",
            profile_count,
            dep_count,
        )
        return {"profile_rows": profile_count, "dependency_rows": dep_count}

    except Exception:
        logger.exception("Failed building serving domain model")
        raise


def main() -> None:
    """Run local test for build_serving_domain_model."""
    configure_logging()
    result = build_serving_domain_model()
    logger.info("Manual run successful. result={}", result)


if __name__ == "__main__":
    main()
