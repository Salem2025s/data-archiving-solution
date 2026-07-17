-- =====================================================================
--  C1.4.1 — Moindre privilège : comptes PostgreSQL lecture / écriture séparés
--
--  · pfe_reader  → LECTURE SEULE  (dashboard, analystes, Console SQL)
--  · pfe_writer  → ÉCRITURE       (pipeline ETL uniquement)
--
--  Exécution (en tant que superutilisateur postgres) :
--    docker exec -i <conteneur_pg> psql -U postgres -d pfe_data_ia \
--        -f - < sql/security/020_roles_least_privilege.sql
-- =====================================================================

-- Sortie propre : masque les NOTICE lors des relances
SET client_min_messages TO WARNING;

-- ---------------------------------------------------------------------
-- 1) Compte LECTURE SEULE — consultation analytique
--    Idempotent : créé s'il n'existe pas, sinon mot de passe réaligné.
--    (On NE fait PAS de DROP ROLE : impossible tant que des privilèges
--     dépendent du rôle — et inutile, les GRANT sont idempotents.)
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pfe_reader') THEN
        CREATE ROLE pfe_reader WITH LOGIN PASSWORD 'reader_demo_2026';
    ELSE
        ALTER ROLE pfe_reader WITH LOGIN PASSWORD 'reader_demo_2026';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE pfe_data_ia TO pfe_reader;
GRANT USAGE ON SCHEMA serving, processed, admin TO pfe_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA serving, processed, admin TO pfe_reader;

-- Les futures tables restent en lecture seule pour ce rôle
ALTER DEFAULT PRIVILEGES IN SCHEMA serving  GRANT SELECT ON TABLES TO pfe_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA processed GRANT SELECT ON TABLES TO pfe_reader;

-- ---------------------------------------------------------------------
-- 2) Compte ÉCRITURE — réservé au pipeline ETL (idempotent, cf. supra)
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pfe_writer') THEN
        CREATE ROLE pfe_writer WITH LOGIN PASSWORD 'writer_demo_2026';
    ELSE
        ALTER ROLE pfe_writer WITH LOGIN PASSWORD 'writer_demo_2026';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE pfe_data_ia TO pfe_writer;
GRANT USAGE, CREATE ON SCHEMA raw_oracle, processed, serving, admin TO pfe_writer;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA raw_oracle, processed, serving, admin TO pfe_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES
    IN SCHEMA raw_oracle, processed, serving, admin TO pfe_writer;

-- ---------------------------------------------------------------------
-- 3) Vérification des privilèges attribués
-- ---------------------------------------------------------------------
SELECT grantee, table_schema, string_agg(DISTINCT privilege_type, ', ' ORDER BY privilege_type) AS privileges
FROM information_schema.role_table_grants
WHERE grantee IN ('pfe_reader', 'pfe_writer')
GROUP BY grantee, table_schema
ORDER BY grantee, table_schema;
