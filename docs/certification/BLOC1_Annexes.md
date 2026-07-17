# BLOC 1 — Annexes

**Titre RNCP 39586 · Bloc 1 — Collecter, transformer et sécuriser des données**
**Candidat :** HAOUARI Salem · **Date :** 14/07/2026 · Annexes au dossier écrit (hors décompte de pages)

> Ces annexes apportent les **preuves d'exécution** du pipeline décrit dans le dossier. Les données proviennent d'exécutions réelles sur l'instance Oracle EP92U038 et l'entrepôt PostgreSQL `pfe_data_ia`.
>
> **Version image (déposée) :** `BLOC1_Annexes.docx` — les 13 captures sont embarquées et légendées. Le présent `.md` en est la version texte de référence ; chaque capture y est référencée par son numéro.

---

## Annexe A — Modules de collecte (arborescence)

Organisation du code de collecte Oracle. Chaque module encapsule une requête d'extraction et retourne des structures Python pures (aucune écriture sur la source).

```
src/
├── connectors/                     # Clients de connexion (lecture seule)
│   ├── oracle_client.py            #   Oracle thin mode + retry résilient (VPN)
│   └── postgres_client.py          #   PostgreSQL (SQLAlchemy / psycopg3)
│
├── extract/
│   └── oracle/                     # 5 catalogues Oracle (dictionnaire de données)
│       ├── extract_record_catalog.py    #   records logiques PeopleSoft ↔ tables physiques
│       ├── extract_table_catalog.py     #   ALL_TABLES (volumétrie)
│       ├── extract_column_catalog.py    #   ALL_TAB_COLUMNS
│       ├── extract_index_catalog.py     #   ALL_INDEXES
│       └── extract_segment_access.py    #   signaux d'usage / accès
│
└── load/                           # Chargement idempotent vers PostgreSQL
    └── load_raw_oracle.py
```

> **Capture #1** — Connexions Oracle (EP92U038) et PostgreSQL réussies (terminal).

---

## Annexe B — Scripts DDL de création de la base

### B.1 Création des schémas (`sql/ddl/001_schemas.sql`) — architecture médaillon

```sql
CREATE SCHEMA IF NOT EXISTS admin;        -- traçabilité des exécutions
CREATE SCHEMA IF NOT EXISTS raw_oracle;   -- bronze : copie brute Oracle
CREATE SCHEMA IF NOT EXISTS processed;    -- silver : modèle en étoile conformé
CREATE SCHEMA IF NOT EXISTS serving;      -- gold : vues / MV analytiques
```

### B.2 Modèle en étoile — extrait (`sql/ddl/040_processed.sql`)

Dimension centrale et principaux faits (le `run_id` versionne chaque instantané) :

```sql
CREATE TABLE IF NOT EXISTS processed.dim_asset (
    id             BIGSERIAL PRIMARY KEY,
    run_id         INTEGER NOT NULL,        -- clé de versionnement (idempotence)
    source_system  TEXT,                    -- oracle
    asset_type     TEXT,                    -- record logique | table physique
    technical_name TEXT,
    business_name  TEXT,
    schema_name    TEXT,
    owner_name     TEXT,
    description    TEXT,
    source_ref     TEXT,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.fact_asset_profile (
    id             BIGSERIAL PRIMARY KEY,
    run_id         INTEGER NOT NULL,
    asset_id       BIGINT,                  -- clé étrangère logique vers dim_asset
    snapshot_date  DATE,
    row_count      BIGINT,                  -- volumétrie
    size_mb        NUMERIC,                 -- taille estimée
    column_count   INTEGER,
    index_count    INTEGER,
    last_analyzed  TIMESTAMP,               -- âge / dernière activité
    source_profile_json JSONB,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- + dim_field, bridge_asset_term, fact_lineage_edge, fact_archiving_event,
--   features_asset, dataset_asset_ml (8 tables au total)
```

> **Capture #5** — Les schémas de l'entrepôt PostgreSQL et leur nb de tables.
> **Capture #6** — Colonnes et types de `processed.dim_asset` (preuve du modèle en étoile).

### B.3 Détail du modèle en étoile (constellation)

Le hub `dim_asset` (1 ligne = 1 actif) est entouré de dimensions et de faits, tous rattachés par la clé `asset_id` + `run_id`.

| Table | Type | Grain | Rôle / colonnes clés |
|---|---|---|---|
| `dim_asset` | Dimension (hub) | 1 actif | Entité centrale : `technical_name`, `asset_type`, `source_ref`, `description` |
| `dim_field` | Dimension | 1 colonne | Champs de chaque actif : `data_type`, `nullable_flag`, `data_length` |
| `bridge_asset_term` | Pont N–N | 1 lien | Actif ↔ terme métier : `term_name`, `domain_name`, `confidence_score` |
| `fact_asset_profile` | Fait | 1 actif × snapshot | Volumétrie & qualité : `row_count`, `size_mb`, `column_count`, `index_count` |
| `fact_lineage_edge` | Fait | 1 arête | Dépendances actif→actif : `source_asset_id`, `target_asset_id`, `lineage_level` |
| `fact_archiving_event` | Fait | 1 événement | Archivage : `event_type`, `rows_affected`, `volume_mb`, `status` |
| `features_asset` | Mart dérivé | 1 actif | Variables agrégées + scores : `lineage_out_count`, `archival_candidate_score`, `roi_score` |
| `dataset_asset_ml` | Mart dérivé | 1 actif | Table plate dénormalisée prête pour le classifieur (features + signatures texte) |

**Le versionnement par `run_id`** joue le rôle d'une dimension temps : chaque table le porte, toute requête le filtre, chaque exécution produit un instantané complet — d'où la reproductibilité et la comparaison N-1 (run 5 vs run 6).

**Exemple de requête** — « tables Finance de plus de 10 Mo, avec volume et nb de colonnes » : on part du hub et on rattache les faits par `asset_id` + `run_id`.

```sql
SELECT d.technical_name, p.size_mb, p.column_count, b.domain_name
FROM processed.dim_asset d
JOIN processed.fact_asset_profile p
     ON p.asset_id = d.id AND p.run_id = d.run_id
JOIN processed.bridge_asset_term b
     ON b.asset_id = d.id AND b.run_id = d.run_id
WHERE d.run_id = 6
  AND b.domain_name = 'Finance & Contrôle'
  AND p.size_mb > 10
ORDER BY p.size_mb DESC;
```

---

## Annexe C — Traçabilité et preuve d'exécution des runs

### C.1 Journal des exécutions (`admin.pipeline_run`)

Chaque exécution complète du pipeline est journalisée dans `admin.pipeline_run` (flow, type, statut, horodatage). La stabilité du volume entre runs (~167 k actifs) atteste de la **reproductibilité** de la collecte.

| id (run) | flow | type | statut | horodatage | actifs |
|---|---|---|---|---|---|
| 3 | flow_full_pipeline | full | success | 2026-03-13 | 167 378 |
| 4 | flow_full_pipeline | full | success | 2026-03-23 | 167 378 |
| 5 | flow_full_pipeline | full | success | 2026-04-22 | 167 381 |
| **6** | flow_full_pipeline | full | **success** | 2026-05-31 | **167 260 (run traité)** |
| 8 | flow_full_pipeline | full | failed | 2026-05-30 | — (interrompu) |
| 9 | flow_oracle_only | full | success | 2026-07-14 | extraction Oracle |

> **Note méthodologique.** La table avait été partiellement vidée en cours de projet ; les entrées des runs 3 à 6 ont été **rétablies à partir des horodatages de chargement réels** (`processed.dim_asset.loaded_at`) via un script reproductible et idempotent (`scripts/backfill_pipeline_run.py`) — aucune valeur inventée. Le run **8 (échoué)** est conservé : il illustre la **gestion des erreurs** (statut `failed` journalisé). Le run **9** est une extraction Oracle réelle postérieure.

> **Capture #10** — Historique des exécutions dans le dashboard.

### C.2 Détail du run traité #6 — comptages par couche

| Couche / table | Lignes (run 6) | Rôle |
|---|---|---|
| `raw_oracle.record_catalog` | 87 627 | Records logiques bruts |
| `raw_oracle.table_catalog` | 79 633 | Tables physiques brutes |
| `raw_oracle.column_catalog` | 1 124 499 | Colonnes brutes |
| `processed.dim_asset` | 167 260 | Actifs conformés (dimension centrale) |
| `processed.dim_field` | 1 806 699 | Champs/colonnes conformés |
| `processed.fact_asset_profile` | 109 775 | Profils de volumétrie/qualité |
| `processed.fact_lineage_edge` | 4 590 | Dépendances (hiérarchie records) |
| `processed.features_asset` | 167 260 | Variables ML dérivées |
| `processed.dataset_asset_ml` | 167 260 | Dataset ML prêt |

---

## Annexe D — Comptages de contrôle : preuve de qualité de la collecte

### D.1 Exhaustivité — réconciliation source ↔ collecté

Comparaison directe entre les **comptages sur la source Oracle** et les **volumes chargés** en base pour le run 6. L'égalité stricte prouve qu'aucune donnée n'a été perdue à la collecte.

| Objet | Compté sur Oracle (source) | Chargé en base (run 6) | Écart |
|---|---|---|---|
| Records logiques (`PSRECDEFN` hors `PSDUMMY`) | 87 627 | 87 627 | **0 ✓** |
| Tables physiques (`ALL_TABLES` SYSADM) | 79 633 | 79 633 | **0 ✓** |

Requêtes de contrôle exécutées sur la source :

```sql
-- Records logiques
SELECT COUNT(*) FROM SYSADM.PSRECDEFN WHERE recname <> 'PSDUMMY';   -- → 87 627
-- Tables physiques
SELECT COUNT(*) FROM ALL_TABLES WHERE owner = 'SYSADM';             -- → 79 633
-- Champs du dictionnaire
SELECT COUNT(*) FROM SYSADM.PSDBFIELD;                              -- → 107 206
-- Associations record ↔ champ
SELECT COUNT(*) FROM SYSADM.PSRECFIELDDB;                           -- → 1 404 127
```

### D.2 Exactitude — mécanismes de contrôle

- **Empreinte SHA-256** calculée sur chaque lot extrait (détection d'altération).
- **`table_exists_flag`** : réconciliation logique ↔ physique (aucune définition perdue silencieusement).
- **Normalisation** : noms en minuscules, `TRIM`, `NULLIF`, lecture intégrale des LOB.

> **Capture #7** — Réconciliation par couche : 87 627 et 79 633 identiques.
> **Capture #2** — Interrogation directe de la source Oracle (types de records).
> **Capture #4** — Données brutes chargées dans `raw_oracle.record_catalog`.

---

## Annexe E — Valorisation (dashboard)

Données transformées rendues exploitables via l'application de gouvernance (`streamlit run app/streamlit_dashboard.py`).

> **Capture #3** — Centre de contrôle des pipelines / logs en direct (automatisation).
> **Capture #8** — Vue d'ensemble : cartographie 167 260 actifs.
> **Capture #9** — Profil par domaine métier.
>
> **Artefact #11** — export Excel `domain_model_run9.xlsx` (13 feuilles) fourni en pièce jointe : livrable exploitable issu de la couche serving.

---

## Annexe F — Preuves de sécurisation

### F.1 Gestion des secrets — modèle `.env.example` (versionné, sans secret réel)

Le fichier `.env` réel (contenant les identifiants) est **gitignoré** ; seul le modèle est versionné, et ses variables correspondent exactement aux champs de `settings.py` :

```ini
ORACLE_HOST=192.168.11.111
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=EP92U038
ORACLE_USER=SYSADM
ORACLE_PASSWORD=change_me
ORACLE_OWNER=SYSADM

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=pfe_data_ia
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change_me
```

### F.2 Exclusion des secrets du dépôt (`.gitignore`)

```gitignore
# ---- Secrets ----
.env
*.env
!.env.example
```

### F.3 Masquage des données personnelles (RGPD) — Phase 0

Extrait de `src/export/export_dataset_asset_ml_for_labeling.py` : les valeurs réelles des colonnes de catégorie PII sont remplacées par un jeton avant tout export vers un annotateur (le signal sémantique est conservé, pas la donnée personnelle) :

```python
PII_SEMANTICS = frozenset({
    "email_address", "phone_number", "person_identifier", "person_first_name",
    "person_last_name", "person_full_name", "user_identifier", "postal_location",
    "geo_latitude", "geo_longitude",
})
for part in sample_parts:
    col_name = part.split(":")[0].strip() if ":" in part else ""
    col_sem  = ...  # sémantique détectée de la colonne
    if col_sem in PII_SEMANTICS:
        masked_sample_parts.append(f"{col_name}:[*** masqué PII ***]")
    else:
        masked_sample_parts.append(part)
```

### F.4 Chiffrement au repos des données personnelles (`pgcrypto`)

La valeur PII est stockée chiffrée (`BYTEA`) dans **`security.pii_vault`** — un schéma dédié, distinct de la couche analytique `serving` :

```sql
CREATE SCHEMA IF NOT EXISTS security;
INSERT INTO security.pii_vault (asset_id, label, email_encrypted)
VALUES (1, 'contact_responsable_finance', pgp_sym_encrypt('jean.dupont@corp.com', :'cle'));
```

| Preuve | Résultat obtenu |
|---|---|
| Illisible au repos | `\xc30d040703024182cf37dae0345c60d24501b78d…` |
| Déchiffrable avec la clé | `jean.dupont@corp.com` |
| Sans la bonne clé | `ERROR: Wrong key or corrupt data` |

### F.5 Moindre privilège : comptes lecture / écriture séparés

| Rôle | Privilèges | Usage |
|---|---|---|
| `pfe_reader` | `SELECT` seul (`admin`, `processed`, `serving`) | Dashboard, analystes |
| `pfe_writer` | `SELECT, INSERT, UPDATE, DELETE` + séquences | Pipeline ETL |

Vérification connecté en `pfe_reader` :

```
SELECT COUNT(*) FROM processed.dim_asset;  ->  167260
INSERT INTO processed.dim_asset …          ->  ERROR: permission denied for table dim_asset
DELETE FROM processed.dim_asset …          ->  ERROR: permission denied for table dim_asset
```

### F.6 Accès source en lecture seule

Le connecteur Oracle n'exécute que des `SELECT` ; la Console SQL du dashboard rejette tout mot-clé d'écriture (INSERT/UPDATE/DELETE/DROP…). Aucune écriture n'atteint l'ERP de production.

> **Capture #12** — `.env` exclu du dépôt (règle `*.env`, fichier non suivi).
> **Capture #13** — Bloc `PII_SEMANTICS` et masquage `[*** masqué PII ***]`.
> **Capture #14** — `UPDATE` rejeté « lecture seule » dans la Console SQL.
> **Capture #16** — pgcrypto : les 3 preuves enchaînées.
> **Capture #17** — Privilèges séparés `pfe_reader` / `pfe_writer`.
> **Capture #18** — `permission denied` en écriture depuis `pfe_reader`.

> **Limites assumées.** Les mots de passe des rôles et la clé `pgcrypto` sont passés en clair aux scripts de démonstration ; en production ils proviendraient d'un **coffre à secrets**. `pgcrypto` chiffre au **niveau colonne** : le chiffrement de volume (TDE) reste une mesure d'infrastructure complémentaire.

---

## Annexe G — Requête d'extraction commentée (jointure logique ↔ physique)

Extrait de `src/extract/oracle/extract_record_catalog.py`. Cette requête est au cœur de la collecte : elle réconcilie la structure **logique** PeopleSoft (`PSRECDEFN`) et la structure **physique** Oracle (`ALL_TABLES`), que PeopleSoft ne lie pas automatiquement.

```sql
SELECT
    r.recname,                         -- nom du record logique
    r.recdescr,                        -- description
    r.rectype,                         -- type (0=table, 1=vue, 7=temporaire…)
    -- Reconstruction du nom physique : sqltablename sinon convention 'PS_' + recname
    CASE WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
         THEN TRIM(r.sqltablename)
         ELSE 'PS_' || r.recname
    END AS physical_table_name,
    t.owner       AS oracle_owner,
    t.table_name  AS oracle_table_name,
    -- Drapeau de réconciliation : la table physique existe-t-elle vraiment ?
    CASE WHEN t.table_name IS NOT NULL THEN 1 ELSE 0 END AS table_exists_flag,
    NULLIF(TRIM(r.parentrecname), ' ') AS parentrecname   -- hiérarchie parent/enfant
FROM SYSADM.PSRECDEFN r
LEFT JOIN ALL_TABLES t                 -- LEFT JOIN : on garde les records sans table physique
       ON t.owner = :owner
      AND t.table_name = CASE
            WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
                THEN TRIM(r.sqltablename)
                ELSE 'PS_' || r.recname
          END
WHERE r.recname <> 'PSDUMMY'           -- exclusion du record technique factice
ORDER BY r.recname
```

**Points clés :** requête **paramétrée** (`:owner`, anti-injection), `LEFT JOIN` pour ne perdre aucune définition, `table_exists_flag` pour la réconciliation, `NULLIF`/`TRIM` pour la normalisation.

---

## Annexe H — Collecte externe : API publique et web scraping

Les coûts de stockage du modèle de ROI ne sont plus des constantes codées en dur : ils proviennent de **sources externes réelles et rejouables** (C1.1.2).

### H.1 API externe — Azure Retail Prices (publique, sans clé)

Tarifs officiels convertis en $/Go/an et injectés dans `serving.dim_cost_params` (`--apply`), ce qui alimente `roi_score` :

| Palier | Compteur Azure | $/Go/mois | $/Go/an |
|---|---|---|---|
| actif | `Hot LRS Data Stored` | 0,0177 | **0,2120** |
| tiède | `Cool LRS Data Stored` | 0,0105 | 0,1260 |
| archive | `Archive LRS Data Stored` | 0,0018 | **0,0216** |

**Écart actif/archive : ×9,8** → gain potentiel de **0,1904 $/Go/an** par Go archivé.

### H.2 Web scraping responsable — Backblaze B2

`robots.txt` vérifié **avant** toute requête ; une seule requête ; User-Agent explicite ; aucune donnée personnelle collectée.

| Source | Technique | $/Go/an |
|---|---|---|
| Azure Archive | API officielle | 0,0216 |
| Backblaze B2 | Scraping HTML | 0,1200 |

→ **Fourchette de marché retenue pour l'archivage : 0,0216 – 0,1200 $/Go/an.**

> **SSL en environnement d'entreprise.** Le proxy inspecte le TLS ; les modules utilisent **`truststore`** (magasin de certificats de l'OS) pour **conserver la vérification SSL** plutôt que de la désactiver.

> **Capture #19** — API Azure : 229 tarifs reçus, écart ×9,8.
> **Capture #20** — Scraping : robots.txt autorisé, fourchette de marché.

---

## Annexe I — Tâches planifiées (déploiements cron Prefect)

Deux déploiements Prefect planifiés répondent au critère « tâches planifiées » (C1.1.3).

| Déploiement | Flow | CRON | Fréquence |
|---|---|---|---|
| `pipeline-oracle-quotidien` | `flow_oracle_only` | `0 2 * * *` | Chaque nuit à 02h00 |
| `serving-refresh-horaire` | `flow_publish_serving` | `0 * * * *` | Toutes les heures |

**Fréquences motivées** : la collecte Oracle est lourde (~87 000 records, VPN requis) donc planifiée **de nuit** hors heures ouvrées ; le recalcul analytique est léger et sans dépendance réseau, donc **horaire**.

> **Capture #15** — Interface Prefect : les 2 déploiements à l'état `Ready` avec leurs planifications.
