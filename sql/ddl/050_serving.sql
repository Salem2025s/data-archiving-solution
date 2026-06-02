-- V1 serving layer aligned with flow_publish_serving materialized views

DROP MATERIALIZED VIEW IF EXISTS serving.mv_cost_analysis CASCADE;
DROP MATERIALIZED VIEW IF EXISTS serving.mv_archiving_recommendation CASCADE;
DROP MATERIALIZED VIEW IF EXISTS serving.mv_domain_dependency CASCADE;
DROP MATERIALIZED VIEW IF EXISTS serving.mv_domain_profile CASCADE;
DROP MATERIALIZED VIEW IF EXISTS serving.mv_roi_summary CASCADE;
DROP MATERIALIZED VIEW IF EXISTS serving.mv_archivability_ranking CASCADE;
DROP MATERIALIZED VIEW IF EXISTS serving.mv_asset_inventory CASCADE;

CREATE MATERIALIZED VIEW serving.mv_asset_inventory AS
SELECT
    da.run_id,
    da.id AS asset_id,
    da.source_system,
    da.asset_type,
    da.technical_name,
    da.business_name,
    da.schema_name,
    da.owner_name,
    da.description,
    da.status,
    da.source_ref,
    fa.snapshot_date,
    fa.row_count,
    fa.size_mb,
    fa.column_count,
    fa.index_count,
    fa.lineage_in_count,
    fa.lineage_out_count,
    fa.term_count,
    fa.purge_event_count,
    fa.total_purged_rows,
    fa.archival_candidate_score,
    fa.roi_score,
    fa.loaded_at AS features_loaded_at
FROM processed.dim_asset da
LEFT JOIN processed.features_asset fa
  ON fa.run_id = da.run_id
 AND fa.asset_id = da.id
WITH NO DATA;

CREATE MATERIALIZED VIEW serving.mv_archivability_ranking AS
SELECT
    da.run_id,
    da.id AS asset_id,
    da.source_system,
    da.asset_type,
    da.technical_name,
    da.business_name,
    fa.snapshot_date,
    fa.row_count,
    fa.size_mb,
    fa.lineage_out_count,
    fa.term_count,
    fa.purge_event_count,
    fa.total_purged_rows,
    fa.archival_candidate_score,
    dense_rank() OVER (
        PARTITION BY da.run_id
        ORDER BY fa.archival_candidate_score DESC NULLS LAST, da.id
    ) AS archival_rank
FROM processed.dim_asset da
JOIN processed.features_asset fa
  ON fa.run_id = da.run_id
 AND fa.asset_id = da.id
WITH NO DATA;

CREATE MATERIALIZED VIEW serving.mv_roi_summary AS
SELECT
    da.run_id,
    da.source_system,
    da.asset_type,
    COUNT(*)::bigint AS asset_count,
    COALESCE(SUM(fa.row_count), 0)::bigint AS total_rows,
    COALESCE(SUM(fa.size_mb), 0)::numeric AS total_size_mb,
    COALESCE(SUM(fa.total_purged_rows), 0)::bigint AS total_purged_rows,
    COALESCE(AVG(fa.roi_score), 0)::numeric AS avg_roi_score,
    COALESCE(MAX(fa.roi_score), 0)::numeric AS max_roi_score
FROM processed.dim_asset da
LEFT JOIN processed.features_asset fa
  ON fa.run_id = da.run_id
 AND fa.asset_id = da.id
GROUP BY da.run_id, da.source_system, da.asset_type
WITH NO DATA;

CREATE INDEX IF NOT EXISTS idx_mv_asset_inventory_run_asset
    ON serving.mv_asset_inventory (run_id, asset_id);
CREATE INDEX IF NOT EXISTS idx_mv_archivability_ranking_run_rank
    ON serving.mv_archivability_ranking (run_id, archival_rank);
CREATE INDEX IF NOT EXISTS idx_mv_roi_summary_run_source_type
    ON serving.mv_roi_summary (run_id, source_system, asset_type);

CREATE TABLE IF NOT EXISTS serving.asset_business_domain_prediction (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL,
    asset_id BIGINT NOT NULL,
    business_domain_predicted TEXT NOT NULL,
    business_domain_alt TEXT,
    confidence NUMERIC,
    confidence_band TEXT,
    review_required BOOLEAN NOT NULL DEFAULT false,
    review_reason TEXT,
    model_version TEXT NOT NULL,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_asset_business_domain_prediction_asset
        FOREIGN KEY (asset_id) REFERENCES processed.dim_asset (id) ON DELETE CASCADE
);

ALTER TABLE serving.asset_business_domain_prediction
    DROP CONSTRAINT IF EXISTS fk_asset_business_domain_prediction_asset;

ALTER TABLE serving.asset_business_domain_prediction
    ADD CONSTRAINT fk_asset_business_domain_prediction_asset
        FOREIGN KEY (asset_id) REFERENCES processed.dim_asset (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_asset_business_domain_prediction_run_id
    ON serving.asset_business_domain_prediction (run_id);
CREATE INDEX IF NOT EXISTS idx_asset_business_domain_prediction_run_asset
    ON serving.asset_business_domain_prediction (run_id, asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_business_domain_prediction_review_required
    ON serving.asset_business_domain_prediction (review_required);
-- Supporte la FK ON DELETE CASCADE vers processed.dim_asset(id).
-- Sans index sur asset_id seul, le DELETE de dim_asset (rebuild d'un run)
-- déclenche un seq-scan de cette table par ligne supprimée -> O(n^2) (plusieurs heures).
CREATE INDEX IF NOT EXISTS idx_abdp_asset_id
    ON serving.asset_business_domain_prediction (asset_id);

CREATE OR REPLACE VIEW serving.v_asset_business_domain_scored AS
SELECT
    ds.run_id,
    ds.asset_id,
    ds.source_system,
    ds.asset_type,
    ds.technical_name,
    ds.source_ref,
    p.business_domain_predicted,
    p.business_domain_alt,
    p.confidence,
    p.confidence_band,
    p.review_required,
    p.review_reason,
    p.model_version,
    p.scored_at
FROM processed.dataset_asset_ml ds
JOIN serving.asset_business_domain_prediction p
  ON p.run_id = ds.run_id
 AND p.asset_id = ds.asset_id;

-- ==========================================================================
-- Domain modeling layer
-- ==========================================================================

CREATE TABLE IF NOT EXISTS serving.dim_domain (
    domain_id           SERIAL PRIMARY KEY,
    domain_label        TEXT NOT NULL UNIQUE,
    domain_key          TEXT NOT NULL UNIQUE,
    description         TEXT,
    typical_objects     TEXT,
    typical_bridge_keys TEXT
);

CREATE MATERIALIZED VIEW IF NOT EXISTS serving.mv_domain_profile AS
WITH latest AS (
    SELECT MAX(run_id) AS run_id FROM processed.dim_asset
),
domain_assets AS (
    SELECT
        p.business_domain_predicted AS domain_label,
        da.description,
        f.size_mb,
        f.archival_candidate_score,
        f.roi_score,
        f.lineage_out_count,
        ml.field_count,
        ml.nullable_field_count
    FROM latest
    JOIN processed.dim_asset da
      ON da.run_id = latest.run_id
    JOIN serving.asset_business_domain_prediction p
      ON p.run_id = da.run_id
     AND p.asset_id = da.id
    LEFT JOIN processed.features_asset f
      ON f.run_id = da.run_id
     AND f.asset_id = da.id
    LEFT JOIN processed.dataset_asset_ml ml
      ON ml.run_id = da.run_id
     AND ml.asset_id = da.id
)
SELECT
    domain_label,
    COUNT(*)::bigint                                          AS asset_count,
    COALESCE(SUM(size_mb), 0)::numeric                       AS total_size_mb,
    COUNT(*) FILTER (WHERE archival_candidate_score > 60)    AS archival_candidates,
    COALESCE(SUM(size_mb) FILTER (
        WHERE archival_candidate_score > 60), 0)::numeric    AS estimated_gain_mb,
    ROUND(AVG(archival_candidate_score)::numeric, 2)         AS avg_archival_score,
    ROUND(AVG(roi_score)::numeric, 2)                        AS avg_roi_score,
    ROUND(AVG(lineage_out_count)::numeric, 2)                AS avg_lineage_out,
    ROUND(AVG(
        CASE WHEN field_count > 0
             THEN nullable_field_count::numeric / field_count
             ELSE NULL END
    )::numeric, 4)                                           AS avg_nullable_ratio,
    COUNT(*) FILTER (
        WHERE description IS NULL OR trim(description) = ''
    )                                                        AS assets_without_description,
    CASE
        WHEN AVG(lineage_out_count) >= 10 THEN 'HIGH'
        WHEN AVG(lineage_out_count) >= 3  THEN 'MEDIUM'
        ELSE 'LOW'
    END                                                      AS risk_level
FROM domain_assets
GROUP BY domain_label
WITH NO DATA;

-- Graphe des CLÉS MÉTIER PARTAGÉES entre domaines (vocabulaire commun), PAS des
-- dépendances référentielles : PeopleSoft ne déclare aucune FK. Une arête = deux
-- domaines utilisant le même nom de champ en clé primaire (ex. SETID). Nom d'objet
-- conservé (`mv_domain_dependency`) pour compatibilité, mais sémantique = clés partagées.
CREATE MATERIALIZED VIEW IF NOT EXISTS serving.mv_domain_dependency AS
WITH latest AS (
    SELECT MAX(run_id) AS run_id FROM processed.dim_asset
),
pk_fields AS (
    SELECT DISTINCT
        upper(ic.recname)   AS recname,
        upper(ic.fieldname) AS fieldname
    FROM raw_oracle.index_catalog ic
    JOIN latest ON ic.run_id = latest.run_id
    WHERE ic.indexid = '0'
),
record_domains AS (
    SELECT
        upper(da.technical_name)            AS recname,
        p.business_domain_predicted         AS domain_label
    FROM latest
    JOIN processed.dim_asset da
      ON da.run_id = latest.run_id
     AND da.asset_type = 'ps_record'
    JOIN serving.asset_business_domain_prediction p
      ON p.run_id = da.run_id
     AND p.asset_id = da.id
),
field_domain_counts AS (
    SELECT
        pf.fieldname,
        rd.domain_label,
        COUNT(DISTINCT pf.recname) AS record_count
    FROM pk_fields pf
    JOIN record_domains rd ON rd.recname = pf.recname
    GROUP BY pf.fieldname, rd.domain_label
),
multi_domain_fields AS (
    SELECT fieldname
    FROM field_domain_counts
    GROUP BY fieldname
    HAVING COUNT(DISTINCT domain_label) >= 2
       AND SUM(record_count) >= 10
),
domain_pairs AS (
    SELECT
        a.domain_label                        AS source_domain,
        b.domain_label                        AS target_domain,
        a.fieldname                           AS bridge_field,
        (a.record_count + b.record_count)     AS shared_asset_count
    FROM field_domain_counts a
    JOIN field_domain_counts b
      ON b.fieldname = a.fieldname
     AND b.domain_label > a.domain_label
    JOIN multi_domain_fields mf ON mf.fieldname = a.fieldname
)
SELECT
    source_domain,
    target_domain,
    bridge_field,
    shared_asset_count
FROM domain_pairs
ORDER BY shared_asset_count DESC, bridge_field
WITH NO DATA;

CREATE OR REPLACE VIEW serving.v_archivability_by_domain AS
WITH latest AS (
    SELECT MAX(run_id) AS run_id FROM processed.dim_asset
),
ranked AS (
    SELECT
        p.business_domain_predicted             AS domain_label,
        da.technical_name,
        da.business_name,
        da.source_system,
        da.asset_type,
        f.archival_candidate_score,
        f.roi_score,
        f.size_mb,
        f.lineage_out_count,
        f.row_count,
        RANK() OVER (
            PARTITION BY p.business_domain_predicted
            ORDER BY f.archival_candidate_score DESC NULLS LAST
        ) AS domain_rank
    FROM latest
    JOIN processed.dim_asset da
      ON da.run_id = latest.run_id
    JOIN serving.asset_business_domain_prediction p
      ON p.run_id = da.run_id
     AND p.asset_id = da.id
    LEFT JOIN processed.features_asset f
      ON f.run_id = da.run_id
     AND f.asset_id = da.id
    -- Recentrage économique : ne classer que les actifs PHYSIQUES (mêmes critères
    -- que mv_archiving_recommendation). Sinon les records logiques (size=0) captent
    -- ~45 pts via les composantes inverses du score et polluent le top candidats.
    WHERE coalesce(f.size_mb, 0) > 0 OR coalesce(f.row_count, 0) > 0
)
SELECT * FROM ranked
WHERE domain_rank <= 20;

CREATE INDEX IF NOT EXISTS idx_serving_dim_domain_label
    ON serving.dim_domain (domain_label);
CREATE INDEX IF NOT EXISTS idx_serving_mv_domain_profile_label
    ON serving.mv_domain_profile (domain_label);
CREATE INDEX IF NOT EXISTS idx_serving_mv_domain_dependency_source
    ON serving.mv_domain_dependency (source_domain, target_domain);

-- ==========================================================================
-- Archiving rules layer (section D — data-driven archiving policies)
-- ==========================================================================

CREATE TABLE IF NOT EXISTS serving.dim_archiving_policy (
    policy_id       SERIAL PRIMARY KEY,
    strategy_code   TEXT NOT NULL UNIQUE,
    strategy_label  TEXT NOT NULL,
    description     TEXT,
    handling        TEXT,
    retention_years INTEGER,
    priority        INTEGER NOT NULL
);

-- Rétention légale/métier par domaine : rend le DOMAINE acteur de la décision
-- d'archivage (ex. Finance/RH réglementés ≠ IT). Peuplée par build_archiving_rules.py.
CREATE TABLE IF NOT EXISTS serving.dim_domain_retention (
    domain_label        TEXT PRIMARY KEY,
    min_retention_years INTEGER NOT NULL,
    regulated           BOOLEAN NOT NULL DEFAULT false,
    retention_basis     TEXT
);

CREATE MATERIALIZED VIEW IF NOT EXISTS serving.mv_archiving_recommendation AS
WITH latest AS (
    SELECT MAX(run_id) AS run_id FROM processed.dim_asset
),
base AS (
    SELECT
        da.id                               AS asset_id,
        da.run_id,
        da.technical_name,
        da.business_name,
        da.source_system,
        da.asset_type,
        p.business_domain_predicted         AS domain_label,
        p.confidence,
        coalesce(f.size_mb, 0)              AS size_mb,
        coalesce(f.row_count, 0)            AS row_count,
        coalesce(f.lineage_out_count, 0)    AS lineage_out_count,
        coalesce(f.lineage_in_count, 0)     AS lineage_in_count,
        coalesce(f.archival_candidate_score, 0) AS archival_candidate_score,
        coalesce(f.roi_score, 0)            AS roi_score,
        prof.last_analyzed,
        tcx.last_modified,
        tcx.referenced_by_count,
        -- Signal d'activité = dernière trace la plus récente (écriture OU analyse).
        -- GREATEST ignore les NULL en PostgreSQL -> repli auto sur last_analyzed.
        CASE
            WHEN GREATEST(prof.last_analyzed, tcx.last_modified) IS NULL THEN NULL
            ELSE (current_date - GREATEST(prof.last_analyzed, tcx.last_modified)::date)
        END AS age_days,
        ml.column_value_semantics_text,
        coalesce(dr.min_retention_years, 3) AS min_retention_years,
        coalesce(dr.regulated, false)       AS regulated,
        dr.retention_basis
    FROM latest
    JOIN processed.dim_asset da
      ON da.run_id = latest.run_id
    JOIN serving.asset_business_domain_prediction p
      ON p.run_id = da.run_id AND p.asset_id = da.id
    LEFT JOIN processed.features_asset f
      ON f.run_id = da.run_id AND f.asset_id = da.id
    LEFT JOIN processed.dataset_asset_ml ml
      ON ml.run_id = da.run_id AND ml.asset_id = da.id
    LEFT JOIN LATERAL (
        SELECT max(fap.last_analyzed) AS last_analyzed
        FROM processed.fact_asset_profile fap
        WHERE fap.run_id = da.run_id AND fap.asset_id = da.id
    ) prof ON true
    LEFT JOIN raw_oracle.table_catalog tcx
      ON tcx.run_id     = da.run_id
     AND tcx.owner      = da.owner_name
     AND tcx.table_name = da.source_ref
    LEFT JOIN serving.dim_domain_retention dr
      ON dr.domain_label = p.business_domain_predicted
    -- Recentrage économique : ne conserver que les actifs PHYSIQUES (qui occupent
    -- réellement du stockage). Écarte les ~150k records logiques PeopleSoft (vues,
    -- sous-records, records de travail) sans donnée physique, hors périmètre de
    -- l'archivage et du coût. Les métriques archivage/coût/ROI portent ainsi sur les
    -- ~17k tables réelles → alignées sur l'objectif économique du projet.
    WHERE coalesce(f.size_mb, 0) > 0 OR coalesce(f.row_count, 0) > 0
),
dims AS (
    SELECT
        base.*,
        -- orpheline = aucun objet stocké (vue/procédure/package) ne la référence.
        -- NULL-safe : referenced_by_count NULL (non extrait) -> is_orphan NULL (inconnu).
        (base.referenced_by_count = 0) AS is_orphan,
        CASE
            WHEN age_days IS NULL  THEN 'inconnu'
            WHEN age_days > 1095   THEN 'tres_ancien'
            WHEN age_days > 365    THEN 'ancien'
            WHEN age_days > 90     THEN 'moyen'
            ELSE 'recent'
        END AS age_band,
        CASE
            WHEN column_value_semantics_text ~ 'person_identifier|email_address|phone_number|person_first_name|person_last_name|person_full_name'
                THEN 'HAUTE'
            WHEN column_value_semantics_text ~ 'financial_amount|user_identifier'
                THEN 'MOYENNE'
            WHEN column_value_semantics_text IS NOT NULL AND column_value_semantics_text <> ''
                THEN 'FAIBLE'
            ELSE 'AUCUNE'
        END AS sensitivity_level
    FROM base
)
SELECT
    dims.*,
    CASE
        WHEN size_mb = 0 AND row_count = 0
            THEN 'NON_APPLICABLE'
        WHEN lineage_out_count >= 10
            THEN 'CONSERVATION_CRITIQUE'
        WHEN referenced_by_count >= 20
            THEN 'CONSERVATION_CRITIQUE'
        WHEN sensitivity_level = 'HAUTE' AND age_band IN ('ancien', 'tres_ancien')
            THEN 'ARCHIVAGE_CHIFFRE'
        WHEN sensitivity_level = 'HAUTE'
            THEN 'CONSERVATION_SECURISEE'
        -- DOMAINE = INPUT DE DÉCISION : une donnée d'un domaine RÉGLEMENTÉ
        -- (Finance/RH/Achats/Ventes) encore dans sa fenêtre de rétention légale ne
        -- doit pas être archivée à froid (risque de non-conformité). age_days inconnu
        -- -> prudence = conserver. C'est le seuil d'archivabilité qui dépend du domaine.
        WHEN regulated AND (age_days IS NULL OR age_days < min_retention_years * 365)
            THEN 'CONSERVATION_REGLEMENTAIRE'
        WHEN age_band = 'tres_ancien'
            THEN 'ARCHIVAGE_FROID'
        WHEN is_orphan AND age_band IN ('ancien', 'moyen') AND size_mb > 0
            THEN 'ARCHIVAGE_FROID'
        WHEN age_band = 'inconnu' AND size_mb >= 50
            THEN 'A_EVALUER'
        WHEN age_band = 'ancien' OR (age_band = 'moyen' AND size_mb >= 10)
            THEN 'COMPRESSION'
        ELSE 'CONSERVATION'
    END AS recommended_strategy,
    array_to_string(array_remove(ARRAY[
        CASE WHEN size_mb >= 100 THEN 'volume_eleve(' || round(size_mb) || 'Mo)' END,
        CASE WHEN size_mb = 0 AND row_count = 0 THEN 'aucune_donnee_physique' END,
        CASE WHEN age_band = 'tres_ancien' THEN 'inactif_>3ans' END,
        CASE WHEN age_band = 'ancien' THEN 'inactif_>1an' END,
        CASE WHEN is_orphan THEN 'orpheline(0_objet_dependant)' END,
        CASE WHEN referenced_by_count >= 20 THEN 'tres_reference(' || referenced_by_count || '_objets)' END,
        CASE WHEN sensitivity_level = 'HAUTE' THEN 'donnees_personnelles' END,
        CASE WHEN sensitivity_level = 'MOYENNE' THEN 'donnees_financieres' END,
        CASE WHEN regulated AND (age_days IS NULL OR age_days < min_retention_years * 365)
             THEN 'retention_legale_' || min_retention_years || 'ans' END,
        CASE WHEN lineage_out_count >= 10 THEN 'fortement_reference(' || lineage_out_count || '_dependants)' END,
        CASE WHEN lineage_out_count = 0 AND size_mb > 0 THEN 'aucune_dependance_sortante' END
    ], NULL), '; ') AS rationale
FROM dims
WITH NO DATA;

CREATE OR REPLACE VIEW serving.v_archiving_policy_summary AS
SELECT
    r.domain_label,
    r.recommended_strategy,
    pol.strategy_label,
    pol.handling,
    pol.retention_years,
    -- Rétention effective = max(rétention de la stratégie, plancher légal du domaine)
    GREATEST(coalesce(pol.retention_years, 0), MAX(r.min_retention_years))::int AS effective_retention_years,
    bool_or(r.regulated)                   AS regulated_domain,
    COUNT(*)::bigint                       AS asset_count,
    ROUND(SUM(r.size_mb)::numeric, 1)      AS total_size_mb
FROM serving.mv_archiving_recommendation r
LEFT JOIN serving.dim_archiving_policy pol
  ON pol.strategy_code = r.recommended_strategy
GROUP BY r.domain_label, r.recommended_strategy, pol.strategy_label,
         pol.handling, pol.retention_years, pol.priority
ORDER BY r.domain_label, pol.priority;

CREATE INDEX IF NOT EXISTS idx_serving_mv_archiving_reco_strategy
    ON serving.mv_archiving_recommendation (recommended_strategy);
CREATE INDEX IF NOT EXISTS idx_serving_mv_archiving_reco_domain
    ON serving.mv_archiving_recommendation (domain_label);
CREATE INDEX IF NOT EXISTS idx_serving_mv_archiving_reco_asset
    ON serving.mv_archiving_recommendation (asset_id);

-- ==========================================================================
-- Cost & ROI analytics layer (section E — gains, N-1, ROI projection, répartition)
-- Devise : USD. Coûts exprimés en $/Go/an.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS serving.dim_cost_params (
    param_id    SERIAL PRIMARY KEY,
    param_name  TEXT NOT NULL UNIQUE,
    param_value NUMERIC NOT NULL,
    unit        TEXT,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- E1 : analyse de coût par domaine (basée sur les recommandations section D)
CREATE MATERIALIZED VIEW IF NOT EXISTS serving.mv_cost_analysis AS
WITH params AS (
    SELECT
        MAX(CASE WHEN param_name = 'storage_cost_per_gb_per_year'  THEN param_value END) AS cost_active,
        MAX(CASE WHEN param_name = 'cold_storage_cost_per_gb_year' THEN param_value END) AS cost_cold,
        MAX(CASE WHEN param_name = 'compression_ratio'            THEN param_value END) AS compression_ratio
    FROM serving.dim_cost_params
),
asset_cost AS (
    SELECT
        r.domain_label,
        r.size_mb / 1024.0                              AS size_gb,
        r.recommended_strategy,
        (r.size_mb / 1024.0) * p.cost_active            AS cost_current,
        CASE
            WHEN r.recommended_strategy IN ('ARCHIVAGE_FROID', 'ARCHIVAGE_CHIFFRE')
                THEN (r.size_mb / 1024.0) * p.cost_cold
            WHEN r.recommended_strategy = 'COMPRESSION'
                THEN (r.size_mb / 1024.0) * p.compression_ratio * p.cost_active
            ELSE (r.size_mb / 1024.0) * p.cost_active
        END                                             AS cost_after
    FROM serving.mv_archiving_recommendation r
    CROSS JOIN params p
    WHERE r.size_mb > 0
)
SELECT
    domain_label,
    ROUND(SUM(size_gb)::numeric, 4)                                  AS total_size_gb,
    ROUND(SUM(size_gb) FILTER (
        WHERE recommended_strategy IN ('ARCHIVAGE_FROID','ARCHIVAGE_CHIFFRE','COMPRESSION')
    )::numeric, 4)                                                   AS archivable_size_gb,
    ROUND(SUM(cost_current)::numeric, 2)                             AS current_cost_usd_year,
    ROUND(SUM(cost_after)::numeric, 2)                               AS cost_after_archiving_usd_year,
    ROUND(SUM(cost_current - cost_after)::numeric, 2)                AS annual_savings_usd,
    ROUND((SUM(cost_current - cost_after) * 100.0
           / NULLIF(SUM(cost_current), 0))::numeric, 1)             AS savings_pct
FROM asset_cost
GROUP BY domain_label
ORDER BY current_cost_usd_year DESC
WITH NO DATA;

-- E1 : synthèse globale (+ normalisation au To pour scalabilité)
CREATE OR REPLACE VIEW serving.v_storage_impact_summary AS
WITH params AS (
    SELECT
        MAX(CASE WHEN param_name = 'storage_cost_per_gb_per_year'  THEN param_value END) AS cost_active,
        MAX(CASE WHEN param_name = 'cold_storage_cost_per_gb_year' THEN param_value END) AS cost_cold
    FROM serving.dim_cost_params
)
SELECT
    ROUND(SUM(total_size_gb)::numeric, 4)              AS total_patrimoine_gb,
    ROUND(SUM(archivable_size_gb)::numeric, 4)         AS total_archivable_gb,
    ROUND(SUM(current_cost_usd_year)::numeric, 2)      AS current_cost_usd_year,
    ROUND(SUM(cost_after_archiving_usd_year)::numeric, 2) AS cost_after_usd_year,
    ROUND(SUM(annual_savings_usd)::numeric, 2)         AS annual_savings_usd,
    ROUND((SUM(annual_savings_usd) * 100.0
           / NULLIF(SUM(current_cost_usd_year), 0))::numeric, 1) AS reduction_pct,
    (SELECT cost_active FROM params)                   AS cost_active_usd_per_gb_year,
    (SELECT cost_cold FROM params)                     AS cost_cold_usd_per_gb_year,
    ROUND(((SELECT cost_active FROM params) - (SELECT cost_cold FROM params)) * 1024, 2)
                                                       AS savings_usd_per_tb_archived_year
FROM serving.mv_cost_analysis;

-- E2 : comparaison N-1 simulée (taux de croissance appliqué à l'envers)
CREATE OR REPLACE VIEW serving.v_n1_comparison AS
WITH params AS (
    SELECT MAX(CASE WHEN param_name = 'data_growth_rate_pct_per_year' THEN param_value END) AS growth
    FROM serving.dim_cost_params
)
SELECT
    ca.domain_label,
    ca.total_size_gb                                                   AS size_gb_n,
    ROUND((ca.total_size_gb / (1 + p.growth/100))::numeric, 4)         AS size_gb_n1,
    ROUND((ca.total_size_gb - ca.total_size_gb / (1 + p.growth/100))::numeric, 4) AS growth_gb,
    ca.current_cost_usd_year                                           AS cost_n_usd,
    ROUND((ca.current_cost_usd_year / (1 + p.growth/100))::numeric, 2) AS cost_n1_usd,
    ROUND((ca.current_cost_usd_year - ca.current_cost_usd_year / (1 + p.growth/100))::numeric, 2) AS cost_increase_usd,
    p.growth                                                           AS growth_rate_pct
FROM serving.mv_cost_analysis ca
CROSS JOIN params p
ORDER BY ca.current_cost_usd_year DESC;

-- E4 : répartition des coûts par domaine (+ Pareto + potentiel d'optimisation)
CREATE OR REPLACE VIEW serving.v_cost_by_domain AS
WITH totals AS (
    SELECT SUM(current_cost_usd_year) AS tot_cost,
           SUM(total_size_gb)         AS tot_size,
           SUM(annual_savings_usd)    AS tot_savings
    FROM serving.mv_cost_analysis
)
SELECT
    ca.domain_label,
    ca.total_size_gb,
    ca.current_cost_usd_year,
    ca.annual_savings_usd,
    ca.savings_pct,
    ROUND((ca.total_size_gb * 100.0 / NULLIF(t.tot_size, 0))::numeric, 2)         AS volume_share_pct,
    ROUND((ca.current_cost_usd_year * 100.0 / NULLIF(t.tot_cost, 0))::numeric, 2) AS cost_share_pct,
    ROUND((ca.annual_savings_usd * 100.0 / NULLIF(t.tot_savings, 0))::numeric, 2) AS savings_share_pct,
    DENSE_RANK() OVER (ORDER BY ca.current_cost_usd_year DESC)                    AS cost_rank,
    ROUND(SUM(ca.current_cost_usd_year * 100.0 / NULLIF(t.tot_cost, 0))
          OVER (ORDER BY ca.current_cost_usd_year DESC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)::numeric, 1)    AS cumulative_cost_pct,
    CASE
        WHEN ca.savings_pct >= 40 THEN 'Très élevé'
        WHEN ca.savings_pct >= 20 THEN 'Élevé'
        WHEN ca.savings_pct >= 10 THEN 'Modéré'
        ELSE 'Faible'
    END                                                                          AS optimization_potential
FROM serving.mv_cost_analysis ca
CROSS JOIN totals t
ORDER BY ca.current_cost_usd_year DESC;

-- E3 : projection ROI multi-années (peuplée par build_cost_analysis.py)
CREATE TABLE IF NOT EXISTS serving.roi_projection (
    projection_id                 SERIAL PRIMARY KEY,
    computed_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id                        INTEGER NOT NULL,
    year_offset                   INTEGER NOT NULL,
    volume_no_action_gb           NUMERIC,
    cost_no_action_usd            NUMERIC,
    cumul_cost_no_action_usd      NUMERIC,
    volume_active_gb              NUMERIC,
    volume_cold_gb                NUMERIC,
    cost_with_archiving_usd       NUMERIC,
    cumul_cost_with_archiving_usd NUMERIC,
    net_savings_usd               NUMERIC,
    roi_pct                       NUMERIC,
    breakeven                     BOOLEAN
);

CREATE OR REPLACE VIEW serving.v_roi_projection_summary AS
SELECT
    year_offset,
    volume_no_action_gb,
    cost_no_action_usd,
    cumul_cost_no_action_usd,
    ROUND((volume_active_gb + volume_cold_gb)::numeric, 4) AS total_volume_with_archiving_gb,
    cost_with_archiving_usd,
    cumul_cost_with_archiving_usd,
    net_savings_usd,
    roi_pct,
    breakeven
FROM serving.roi_projection
WHERE computed_at = (SELECT MAX(computed_at) FROM serving.roi_projection)
ORDER BY year_offset;

CREATE INDEX IF NOT EXISTS idx_serving_mv_cost_analysis_domain
    ON serving.mv_cost_analysis (domain_label);
CREATE INDEX IF NOT EXISTS idx_serving_roi_projection_run
    ON serving.roi_projection (run_id, year_offset);
