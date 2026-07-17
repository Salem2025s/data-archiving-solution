-- =====================================================================
--  C1.4.1 / C1.4.2 — Chiffrement au repos d'une donnée personnelle (PII)
--  Démonstration pgcrypto : la valeur est illisible en base, seule la clé
--  permet de la déchiffrer.
--
--  Exécution :
--    docker exec -it <conteneur_pg> psql -U postgres -d pfe_data_ia \
--        -v cle="'ma_cle_demo_2026'" -f /tmp/010_pgcrypto_demo.sql
--  ou, plus simple, en session psql interactive :
--    \set cle 'ma_cle_demo_2026'
--    \i sql/security/010_pgcrypto_demo.sql
--
--  ⚠️ En production, la clé NE doit PAS être passée en clair : elle vient
--     d'un coffre (vault) ou d'une variable d'environnement côté serveur.
-- =====================================================================

-- Sortie propre : masque les NOTICE (« extension déjà existante »…) lors des relances
SET client_min_messages TO WARNING;

-- 1) Activation de l'extension de chiffrement
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 2) Schéma dédié à la sécurité : le coffre PII n'est PAS un objet analytique,
--    il n'a donc pas sa place dans la couche `serving` (séparation des responsabilités).
CREATE SCHEMA IF NOT EXISTS security;

-- 3) Table de coffre PII : la colonne est de type BYTEA (chiffrée)
CREATE TABLE IF NOT EXISTS security.pii_vault (
    id              BIGSERIAL PRIMARY KEY,
    asset_id        BIGINT,
    label           TEXT,
    email_encrypted BYTEA NOT NULL,          -- chiffré au repos
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Repartir propre à chaque démonstration (ids réinitialisés à 1)
TRUNCATE security.pii_vault RESTART IDENTITY;

-- 3) Insertion CHIFFRÉE (chiffrement symétrique PGP)
INSERT INTO security.pii_vault (asset_id, label, email_encrypted)
VALUES
    (1, 'contact_responsable_finance',
        pgp_sym_encrypt('jean.dupont@corp.com', :'cle')),
    (2, 'contact_responsable_rh',
        pgp_sym_encrypt('marie.martin@corp.com', :'cle'));

-- =====================================================================
--  PREUVE 1 — AU REPOS : la donnée est ILLISIBLE
-- =====================================================================
SELECT id, label, email_encrypted
FROM security.pii_vault;

-- =====================================================================
--  PREUVE 2 — AVEC LA CLÉ : la donnée est déchiffrable
-- =====================================================================
SELECT id,
       label,
       pgp_sym_decrypt(email_encrypted, :'cle') AS email_dechiffre
FROM security.pii_vault;

-- =====================================================================
--  PREUVE 3 — SANS LA BONNE CLÉ : le déchiffrement ÉCHOUE
--  (attendu : ERROR "Wrong key or corrupt data")
-- =====================================================================
SELECT pgp_sym_decrypt(email_encrypted, 'mauvaise_cle') AS tentative
FROM security.pii_vault;
