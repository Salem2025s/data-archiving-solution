-- =====================================================================
--  C1.4.1 — PREUVE du moindre privilège
--  À exécuter CONNECTÉ EN TANT QUE pfe_reader :
--
--    docker exec -it <conteneur_pg> psql -U pfe_reader -d pfe_data_ia
--    (mot de passe : reader_demo_2026)
--    puis : \i /tmp/021_preuve_lecture_seule.sql
-- =====================================================================

-- Qui suis-je ?
SELECT current_user AS compte_connecte;

-- =====================================================================
--  PREUVE 1 — La LECTURE fonctionne
-- =====================================================================
SELECT COUNT(*) AS assets_lisibles
FROM processed.dim_asset
WHERE run_id = 6;

-- =====================================================================
--  PREUVE 2 — L'ÉCRITURE est REFUSÉE
--  (attendu : ERROR "permission denied for table dim_asset")
-- =====================================================================
INSERT INTO processed.dim_asset (run_id, technical_name)
VALUES (999, 'TENTATIVE_ECRITURE_INTERDITE');

-- =====================================================================
--  PREUVE 3 — La SUPPRESSION est REFUSÉE
--  (attendu : ERROR "permission denied for table dim_asset")
-- =====================================================================
DELETE FROM processed.dim_asset WHERE run_id = 6;
