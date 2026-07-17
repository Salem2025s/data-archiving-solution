# Bloc 1 — Fiche des captures d'écran (commandes prêtes-à-l'emploi)

> Chaque bloc = une capture. Lance la commande / colle la requête, puis fais la capture.
> **Astuce lisibilité** : agrandis la police du terminal (Ctrl+molette) et de Streamlit avant de capturer.

---

## 🖥️ Captures TERMINAL

### #1 — Connexions aux bases réussies (collecte)
```powershell
python -m src.connectors.oracle_client
python -m src.connectors.postgres_client
```
➡️ Capturer les lignes `Oracle connection successful … EP92U038` et `PostgreSQL connection OK … pfe_data_ia`.

### #12 — Preuve que `.env` (secrets) est exclu du dépôt (sécurité)
```powershell
git check-ignore -v .env
git status --short
```
➡️ La 1ʳᵉ commande affiche `.gitignore:3:*.env  .env` (règle qui ignore le fichier).
La 2ᵉ montre que `.env` **n'apparaît pas** dans les fichiers suivis. Capturer les deux.

---

## 💾 Captures CONSOLE SQL du dashboard

> Dashboard → section **💾 Console SQL**. Choisir la bonne base (radio en haut), coller, **▶️ Exécuter**, capturer le tableau de résultat.

### #2 — Interroger la SOURCE Oracle en direct (collecte)
**Base : 🏛️ Oracle EP92U038**
```sql
SELECT rectype,
       CASE rectype WHEN 0 THEN 'SQL Table' WHEN 1 THEN 'SQL View'
            WHEN 2 THEN 'Derived/Work' WHEN 3 THEN 'SubRecord'
            WHEN 5 THEN 'Dynamic View' WHEN 6 THEN 'Query View'
            WHEN 7 THEN 'Temporary' ELSE 'Autre' END AS signification,
       COUNT(*) AS nb
FROM SYSADM.PSRECDEFN
WHERE recname <> 'PSDUMMY'
GROUP BY rectype ORDER BY nb DESC
```
➡️ Résultat attendu : 7 lignes (SQL View 39 319, SQL Table 26 054, …).

### #4 — Données brutes réellement chargées (collecte/stockage)
**Base : 🐘 PostgreSQL pfe_data_ia**
```sql
SELECT recname, recdescr, rectype, physical_table_name, table_exists_flag
FROM raw_oracle.record_catalog
WHERE run_id = 6
ORDER BY recname
LIMIT 15
```
➡️ Montre la couche bronze `raw_oracle` peuplée (réconciliation logique↔physique via `table_exists_flag`).

### #5 — Architecture médaillon : les 4 schémas principaux (stockage)
**Base : 🐘 PostgreSQL pfe_data_ia**
```sql
SELECT table_schema, COUNT(*) AS nb_tables
FROM information_schema.tables
WHERE table_schema IN ('admin','raw_oracle','raw_mongo','processed','serving')
GROUP BY table_schema
ORDER BY table_schema
```
➡️ Résultat attendu : admin 1 · processed 8 · raw_mongo 9 · raw_oracle 5 · serving 20.

### #7 — Réconciliation source → collecté (preuve d'exhaustivité)
**Base : 🐘 PostgreSQL pfe_data_ia**
```sql
SELECT 'raw_oracle.record_catalog' AS couche, COUNT(*) AS lignes FROM raw_oracle.record_catalog WHERE run_id = 6
UNION ALL SELECT 'raw_oracle.table_catalog',    COUNT(*) FROM raw_oracle.table_catalog    WHERE run_id = 6
UNION ALL SELECT 'processed.dim_asset',         COUNT(*) FROM processed.dim_asset         WHERE run_id = 6
UNION ALL SELECT 'processed.dim_field',         COUNT(*) FROM processed.dim_field         WHERE run_id = 6
UNION ALL SELECT 'processed.fact_asset_profile',COUNT(*) FROM processed.fact_asset_profile WHERE run_id = 6
ORDER BY lignes DESC
```
➡️ record_catalog = **87 627** (= comptage Oracle), table_catalog = **79 633** (= ALL_TABLES). Écart zéro.

### #14 — Le garde-fou « lecture seule » bloque une écriture (sécurité)
**Base : 🐘 PostgreSQL pfe_data_ia**
```sql
UPDATE processed.dim_asset SET description = 'test' WHERE run_id = 6
```
➡️ Capturer le message d'erreur rouge : **« Mot-clé d'écriture interdit détecté : UPDATE. Console en lecture seule. »**
Aucune donnée n'est modifiée — c'est la preuve du moindre accès.

---

## 🖼️ Captures INTERFACE (dashboard, sans commande)

| # | Section du dashboard | Ce qu'on voit |
|---|---|---|
| 3 | 🚀 **Pipelines** → lancer « Publier la couche serving » | Logs d'exécution en direct (automatisation) |
| 8 | 🏠 **Vue d'ensemble** | Cartographie 167 260 actifs + donut par domaine |
| 9 | 🗂️ **Domaines** | Score d'archivage + qualité par domaine |
| 10 | 🚀 **Pipelines** → Historique des exécutions | Les 5 runs journalisés (`admin.pipeline_run`) |
| 11 | Fichier Excel exporté (13 feuilles) ouvert | Livrable exploitable |

## 🖥️ Captures CODE (VS Code)

| # | Fichier | Ce qu'on montre |
|---|---|---|
| 13 | `src/export/export_dataset_asset_ml_for_labeling.py` (≈ ligne 1119) | Bloc `PII_SEMANTICS` + masquage `[*** masqué PII ***]` |

---

### Rappel avant de capturer
- **VPN actif** (pour #1 Oracle et #2).
- **Docker/PostgreSQL démarré** (pour #4, #5, #7, #14 et tout le dashboard).
- Fermer le fichier Word `~$…` s'il est ouvert avant toute régénération.
