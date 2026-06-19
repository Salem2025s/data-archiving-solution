"""Populate serving.dim_archiving_policy and refresh mv_archiving_recommendation.

Data-driven archiving rules engine (section D). The recommended strategy for
each asset is decided in the materialized view from six concrete dimensions:
volume (size_mb), ancienneté (age_days from last_analyzed/last_modified),
sensibilité (PII / financial semantics), dépendances hiérarchiques
(lineage_out_count), références d'objets stockés (referenced_by_count /
is_orphan) and accès réel en lecture (access_band, NULL-safe, inerte tant que
le grant DBA sur V$SEGMENT_STATISTICS est absent). Le DOMAINE est aussi un
input décisionnel via dim_domain_retention (rétention légale -> CONSERVATION_
REGLEMENTAIRE). L'archival_candidate_score est conservé pour référence mais
n'est PAS le moteur de décision (term_count=0 -> il ne différencie pas).
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
    (domain_label, jurisdiction, min_retention_years, regulated, retention_basis,
     version, effective_from, validated_by)
VALUES
    (:domain_label, :jurisdiction, :min_retention_years, :regulated, :retention_basis,
     :version, :effective_from, :validated_by)
ON CONFLICT (domain_label, jurisdiction) DO UPDATE SET
    min_retention_years = EXCLUDED.min_retention_years,
    regulated           = EXCLUDED.regulated,
    retention_basis     = EXCLUDED.retention_basis,
    version             = EXCLUDED.version,
    effective_from      = EXCLUDED.effective_from,
    validated_by        = EXCLUDED.validated_by
"""

LOG_DECISION_SQL = """
INSERT INTO serving.archiving_decision_log (
    asset_id, run_id, technical_name, domain_label,
    recommended_strategy, confidence, confidence_band, review_required,
    model_version, decision, decision_reason, decided_by, decided_at,
    jurisdiction, retention_version, min_retention_years
) VALUES (
    :asset_id, :run_id, :technical_name, :domain_label,
    :recommended_strategy, :confidence, :confidence_band, :review_required,
    :model_version, :decision, :decision_reason, :decided_by, now(),
    :jurisdiction, :retention_version, :min_retention_years
)
"""

POPULATE_QUEUE_SQL = """
INSERT INTO serving.archiving_approval_queue
    (asset_id, run_id, technical_name, domain_label, recommended_strategy,
     confidence, confidence_band, model_version, review_reason)
SELECT
    r.asset_id,
    r.run_id,
    r.technical_name,
    r.domain_label,
    r.recommended_strategy,
    r.confidence,
    -- confidence_band dérivée à la volée (non stockée dans la MV)
    CASE
        WHEN coalesce(r.confidence, 0) >= 0.85 THEN 'high'
        WHEN coalesce(r.confidence, 0) >= 0.60 THEN 'medium'
        ELSE 'low'
    END AS confidence_band,
    p.model_version,
    CASE
        WHEN dr.regulated AND r.recommended_strategy NOT LIKE 'CONSERVATION%%'
            THEN 'domaine_reglemente+strategie_archivage'
        WHEN coalesce(r.confidence, 0) < 0.60
            THEN 'confiance_faible(' || round(coalesce(r.confidence,0)::numeric,2) || ')'
        WHEN coalesce(p.review_required, false)
            THEN 'review_required_par_scoreur'
        ELSE 'autre'
    END AS review_reason
FROM serving.mv_archiving_recommendation r
LEFT JOIN serving.dim_domain_retention dr
    ON dr.domain_label = r.domain_label AND dr.jurisdiction = 'FR'
LEFT JOIN serving.asset_business_domain_prediction p
    ON p.asset_id = r.asset_id AND p.run_id = r.run_id
WHERE r.run_id = :run_id
  AND (
    (dr.regulated AND r.recommended_strategy NOT LIKE 'CONSERVATION%%')
    OR coalesce(r.confidence, 0) < 0.60
    OR coalesce(p.review_required, false)
  )
  AND NOT EXISTS (
    SELECT 1 FROM serving.archiving_approval_queue q
    WHERE q.asset_id = r.asset_id AND q.run_id = r.run_id
  )
"""

# Planchers de rétention légale/métier par domaine.
# IMPORTANT : ces valeurs sont des DÉFAUTS FR à valider par le service juridique.
# validated_by = None jusqu'à validation explicite.
# Pour ajouter une juridiction : dupliquer les lignes avec jurisdiction='BE' etc.
DOMAIN_RETENTION: list[dict[str, object]] = [
    {"domain_label": "Finance & Contrôle", "jurisdiction": "FR",
     "min_retention_years": 10, "regulated": True,
     "retention_basis": "Pièces comptables — Code de commerce (FR) art. L123-22 : 10 ans",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
    {"domain_label": "Ventes & Clients", "jurisdiction": "FR",
     "min_retention_years": 10, "regulated": True,
     "retention_basis": "Factures clients : 10 ans (Code de commerce)",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
    {"domain_label": "Achats & Fournisseurs", "jurisdiction": "FR",
     "min_retention_years": 10, "regulated": True,
     "retention_basis": "Factures / contrats fournisseurs : 10 ans",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
    {"domain_label": "RH", "jurisdiction": "FR",
     "min_retention_years": 5, "regulated": True,
     "retention_basis": "Bulletins de paie / contrats : 5 ans min. (Code du travail)",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
    {"domain_label": "Supply Chain / Logistique / Production", "jurisdiction": "FR",
     "min_retention_years": 3, "regulated": False,
     "retention_basis": "Documents logistiques / production : ~3 ans (usage)",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
    {"domain_label": "IT & Sécurité", "jurisdiction": "FR",
     "min_retention_years": 1, "regulated": False,
     "retention_basis": "Logs techniques : ~1 an (rétention courte)",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
    {"domain_label": "Other", "jurisdiction": "FR",
     "min_retention_years": 3, "regulated": False,
     "retention_basis": "Défaut prudent (domaine non rattaché)",
     "version": 1, "effective_from": "2026-01-01", "validated_by": None},
]


def log_decision(
    pg: PostgresClient,
    asset_id: int,
    run_id: int,
    technical_name: str,
    domain_label: str,
    recommended_strategy: str,
    decision: str,
    *,
    confidence: float | None = None,
    confidence_band: str | None = None,
    review_required: bool | None = None,
    model_version: str | None = None,
    decision_reason: str | None = None,
    decided_by: str | None = None,
    jurisdiction: str = "FR",
    retention_version: int | None = None,
    min_retention_years: int | None = None,
) -> None:
    """Append one row to the immutable archiving decision audit trail."""
    pg.execute(LOG_DECISION_SQL, {
        "asset_id": asset_id, "run_id": run_id,
        "technical_name": technical_name, "domain_label": domain_label,
        "recommended_strategy": recommended_strategy,
        "confidence": confidence, "confidence_band": confidence_band,
        "review_required": review_required, "model_version": model_version,
        "decision": decision, "decision_reason": decision_reason,
        "decided_by": decided_by, "jurisdiction": jurisdiction,
        "retention_version": retention_version,
        "min_retention_years": min_retention_years,
    })


def build_archiving_rules(populate_queue: bool = True) -> dict[str, int]:
    """Upsert archiving policies, refresh the recommendation MV, and populate
    the approval queue for assets requiring human sign-off.

    Six decision dimensions (volume, age, sensitivity, dependencies, references,
    access) + domain-driven retention (CONSERVATION_REGLEMENTAIRE) + fail-safe
    on low-confidence predictions (A_EVALUER when confidence < 0.60 or
    review_required).
    """
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    try:
        logger.info("Building archiving rules ({} policies)", len(POLICIES))

        logger.info("Step 1/4 — upserting serving.dim_archiving_policy")
        for policy in POLICIES:
            pg.execute(UPSERT_SQL, policy)

        logger.info("Step 2/4 — upserting serving.dim_domain_retention ({} domains, FR)", len(DOMAIN_RETENTION))
        unvalidated = [r["domain_label"] for r in DOMAIN_RETENTION if r.get("validated_by") is None]
        if unvalidated:
            logger.warning(
                "dim_domain_retention: {} domain(s) NOT yet validated by legal team: {}",
                len(unvalidated), unvalidated,
            )
        for retention in DOMAIN_RETENTION:
            pg.execute(UPSERT_RETENTION_SQL, retention)

        logger.info("Step 3/4 — refreshing serving.mv_archiving_recommendation")
        pg.execute("REFRESH MATERIALIZED VIEW serving.mv_archiving_recommendation")

        reco_row = pg.fetch_one(
            "SELECT COUNT(*) AS n FROM serving.mv_archiving_recommendation"
        )
        reco_count = int(reco_row["n"]) if reco_row else 0

        queue_count = 0
        if populate_queue:
            logger.info("Step 4/4 — populating serving.archiving_approval_queue")
            run_row = pg.fetch_one(
                "SELECT MAX(run_id) AS r FROM serving.mv_archiving_recommendation"
            )
            run_id = int(run_row["r"]) if run_row and run_row.get("r") else None
            if run_id is not None:
                pg.execute(POPULATE_QUEUE_SQL, {"run_id": run_id})
                q_row = pg.fetch_one(
                    "SELECT COUNT(*) AS n FROM serving.archiving_approval_queue "
                    "WHERE status = 'PENDING' AND run_id = :run_id",
                    {"run_id": run_id},
                )
                queue_count = int(q_row["n"]) if q_row else 0
                logger.info(
                    "{} asset(s) added to approval queue for run_id={} "
                    "(regulated domains + low confidence + review_required)",
                    queue_count, run_id,
                )

        logger.info("archiving rules built: {} recommendation(s), {} in approval queue",
                    reco_count, queue_count)
        return {
            "policy_count": len(POLICIES),
            "recommendation_rows": reco_count,
            "approval_queue_pending": queue_count,
        }

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
