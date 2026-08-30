# pfe-data-ia — Pipeline de gouvernance des données

Classification des actifs de données Oracle PeopleSoft EP92U038 par domaine métier
(**holdout : macro-F1 0,885 · accuracy 0,922 · AUC 0,991** ; labels générés par LLM local,
**échantillon validé par un expert**), règles d'archivage **pilotées par le domaine**
(rétention légale), et KPI/coûts sur une couche serving PostgreSQL. Source unique : Oracle PeopleSoft EP92U038.

> **Nature & portée :** prototype data-driven de bout en bout. La valeur vient des
> **règles + supervision humaine** (le LLM n'est qu'une amorce d'annotation). Pour la
> lecture honnête (valeur réelle, proxys, limites), voir
> [docs/INDEX.md → Lecture critique](docs/INDEX.md#lecture-critique--valeur-réelle-proxys-et-portée).

---

## Table des matières

1. [Prérequis & Installation](#1-prérequis--installation)
2. [Base de données PostgreSQL (Docker)](#2-base-de-données-postgresql-docker)
3. [Configuration (.env)](#3-configuration-env)
4. [Initialisation de la base](#4-initialisation-de-la-base)
5. [Pipeline complet](#5-pipeline-complet)
6. [Flows individuels](#6-flows-individuels)
7. [Scoring ML + keywords → serving](#7-scoring-ml--keywords--serving)
8. [Reclassification par base de termes (audit CSV)](#8-reclassification-par-base-de-termes-audit-csv)
9. [Export du dataset pour labélisation](#9-export-du-dataset-pour-labélisation)
10. [Entraînement & analyse du modèle ML](#10-entraînement--analyse-du-modèle-ml)
11. [Modifier la base de termes](#11-modifier-la-base-de-termes)
12. [Structure du projet](#12-structure-du-projet)
13. [Schémas PostgreSQL](#13-schémas-postgresql)
14. [Variables d'environnement](#14-variables-denvironnement)
15. [Artefacts ML](#15-artefacts-ml)

---

## 1. Prérequis & Installation

| Outil | Version |
|---|---|
| Python | 3.13 |
| Docker Desktop | 4.x+ |
| Oracle (thin mode) | aucun driver natif requis |

### Créer l'environnement Python

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Tests

Socle de tests unitaires (sans base de données — rapides, déterministes) couvrant
les briques à risque : feature-builders de scoring (+ **régression** sur le bug
train/inférence), loader Oracle, settings, base de termes, évaluation humaine,
extracteur d'accès, projection Monte-Carlo / estimateur de croissance (E3),
**calibration + SLA de rappel + drift (model_reliability)**.

```bash
pip install -r requirements-dev.txt
pytest                     # 61 tests, ~10 s
```

---

## 2. Base de données PostgreSQL (Docker)

La base PostgreSQL tourne dans le container Docker `pfe-postgres`.

```bash
# Démarrer le container
docker start pfe-postgres

# Arrêter le container
docker stop pfe-postgres

# Voir l'état
docker ps -a --filter "name=pfe-postgres"

# Démarrage automatique au boot (à faire une fois)
docker update --restart unless-stopped pfe-postgres

# Se connecter en ligne de commande
docker exec -it pfe-postgres psql -U postgres -d pfe_data_ia

# Voir les logs PostgreSQL
docker logs pfe-postgres --tail 50
```

> **Note :** Sans `docker start pfe-postgres`, toutes les commandes Python
> retournent une erreur de connexion (connection timeout expired).

---

## 3. Configuration (.env)

Copier `.env.example` en `.env` et remplir les secrets :

```ini
# ── Application ──────────────────────────────────────────────────────
APP_ENV=dev
LOG_LEVEL=INFO

# ── PostgreSQL (base cible — Docker) ─────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=pfe_data_ia
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change_me

# ── Oracle PeopleSoft EP92U038 (source) ───────────────────────────────
ORACLE_HOST=192.168.11.111
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=EP92U038
ORACLE_USER=SYSADM
ORACLE_PASSWORD=change_me
ORACLE_OWNER=SYSADM

# ── Pipeline ──────────────────────────────────────────────────────────
LOG_LEVEL=INFO
RUN_ID=          # laisser vide → UUID auto-généré
```

---

## 4. Initialisation de la base

À exécuter **une seule fois** sur un environnement vierge.
Crée les 4 schémas et toutes les tables/vues.

```bash
python -m src.prefect.flows.flow_init_db
```

---

## 5. Pipeline complet

Lance en séquence : extraction Oracle → chargement raw →
couche processed → scoring ML → refresh vues serving.

```bash
python -m src.prefect.flows.flow_oracle_only
```

---

## 6. Flows individuels

### 6a. Extraction Oracle → raw_oracle

```bash
python -m src.prefect.flows.flow_oracle_raw
```

Extrait les 5 catalogues Oracle :
`record_catalog`, `table_catalog`, `column_catalog`, `index_catalog`, `segment_access`
(le 5ᵉ, signal d'accès, est branché mais reste vide tant que `SYSADM` n'a pas le
`GRANT SELECT ON SYS.V_$SEGMENT_STATISTICS`).

### 6b. Construction de la couche processed

```bash
python -m src.prefect.flows.flow_build_processed
```

Chaîne de 10 étapes dans l'ordre :

```
dim_asset → dim_field → bridge_asset_term →
fact_asset_profile → fact_lineage_edge → fact_archiving_event →
features_asset → dataset_asset_ml → score_business_domain
```

### 6c. Refresh des vues matérialisées (serving)

```bash
python -m src.prefect.flows.flow_publish_serving
```

Rafraîchit `mv_asset_inventory`, `mv_archivability_ranking`, `mv_roi_summary`.

---

## 7. Scoring ML + keywords → serving

Applique la classification en deux passes sur `processed.dataset_asset_ml`
et écrit les résultats dans `serving.asset_business_domain_prediction` :

1. **Passe 1 — keywords** : chaque ligne est comparée à `DOMAIN_TERMS`
   (base de termes dans `src/ml/domain_term_base.py`).
   Si un domaine domine clairement → label assigné avec une confiance **graduée
   0,70–0,90** selon la force du signal (nombre d'occurrences + dominance sur le
   2ᵉ domaine), et non plus un forfait fixe.
2. **Passe 2 — modèle ML** : les lignes non classifiées par keywords
   passent dans le modèle de production (TF-IDF + features numériques).

### Commandes

```bash
# Run_id automatique (dernier run en base) + modèle baseline
python -m src.transform.score_business_domain

# Run_id et modèle explicites (recommandé en production)
python -m src.transform.score_business_domain \
    --run-id 5 \
    --model-path "LLM/artifacts_business_domain/production_pipeline_latest.joblib"

# Run_id 5, modèle baseline
python -m src.transform.score_business_domain \
    --run-id 5 \
    --model-path "artifacts/business_domain_model.joblib"
```

### Résultats en base (run_id=5, dernier scoring)

| Méthode | Lignes | % |
|---|---|---|
| Keywords (DOMAIN_TERMS) | 44 568 | 26.6 % |
| Modèle ML | 122 695 | 73.4 % |
| **Total** | **167 263** | 100 % |

### Consulter les prédictions

```sql
-- Répartition par domaine
SELECT business_domain_predicted,
       confidence_band,
       COUNT(*)                                           AS total,
       SUM(CASE WHEN model_version LIKE 'keyword%'
               THEN 1 ELSE 0 END)                        AS par_keywords,
       SUM(CASE WHEN review_required THEN 1 ELSE 0 END)  AS a_reviser
FROM serving.asset_business_domain_prediction
WHERE run_id = 5
GROUP BY business_domain_predicted, confidence_band
ORDER BY total DESC;

-- Vue complète avec features
SELECT * FROM serving.v_asset_business_domain_scored
WHERE run_id = 5
LIMIT 100;

-- Lignes à réviser manuellement
SELECT technical_name, business_domain_predicted, confidence, review_reason
FROM serving.v_asset_business_domain_scored
WHERE run_id = 5
  AND review_required = true
ORDER BY confidence ASC;
```

---

## 8. Reclassification par base de termes (audit CSV)

Reclassifie **toutes les lignes depuis zéro** uniquement par mots-clés,
sans toucher à la base. Utile pour auditer/valider la base de termes
avant de relancer le scoring complet.

### Depuis la base PostgreSQL

```bash
# Dernier run_id automatique
python -m src.ml.reclassify_by_terms

# Run_id explicite
python -m src.ml.reclassify_by_terms --run-id 5
```

### Depuis un fichier CSV enrichi

Le CSV doit contenir `column_names_text` et `column_value_semantics_text`.

```bash
python -m src.ml.reclassify_by_terms \
    --csv "exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_annotated.csv"
```

### Fichiers produits dans `exports/reclassified/`

| Fichier | Contenu |
|---|---|
| `<source>_all.csv` | Toutes les lignes avec leur nouveau label keyword |
| `<source>_focus_domains.csv` | Lignes classifiées supply_chain ou procurement |
| `<source>_unclassified.csv` | Lignes sans correspondance claire |

### Colonnes de sortie

| Colonne | Description |
|---|---|
| `kw_domain` | Domaine gagnant (`finance`, `hr`, `supply_chain`…) |
| `kw_label` | Label ML correspondant |
| `kw_confidence` | confiance graduée `0,70–0,90` si classifié, vide sinon |
| `classified` | `True` si les seuils sont atteints |
| `is_focus_domain` | `True` pour supply_chain / procurement / risk / marketing |
| `matched_terms` | Termes ayant déclenché la classification |
| `hits_<domain>` | Nombre de correspondances par domaine |

---

## 9. Export du dataset pour labélisation

Exporte `processed.dataset_asset_ml` en CSV enrichi (avec `column_names_text`,
valeurs observées, patterns) pour annotation manuelle ou LLM.

```bash
# Export complet du dernier run
python -m src.export.export_dataset_asset_ml_for_labeling

# Avec run_id et taille d'échantillon
python -m src.export.export_dataset_asset_ml_for_labeling \
    --run-id 5 \
    --sample-size 1000 \
    --output exports/mon_export_1000.csv

# Export sans échantillonnage (toutes les lignes)
python -m src.export.export_dataset_asset_ml_for_labeling \
    --run-id 5 \
    --output exports/export_complet_run5.csv
```

---

## 10. Entraînement & analyse du modèle ML

### Préparer le dataset labelisé

Nettoie et normalise un fichier annoté (labels LLM ou manuels)
vers les labels officiels : `Finance`, `RH`, `Paie`, `Achats`, `Technique`, `Inconnu`.

```bash
python -m src.ml.prepare_labeled_dataset \
    --input  exports/mon_fichier_annote.csv \
    --output artifacts/labeled_dataset_clean.csv
```

### Entraîner le modèle baseline

```bash
# Entraînement avec les paramètres par défaut
python -m src.ml.train_business_domain_classifier

# Avec chemins explicites
python -m src.ml.train_business_domain_classifier \
    --input  artifacts/labeled_dataset_clean.csv \
    --output artifacts/business_domain_model.joblib
```

Génère dans `artifacts/` :
- `business_domain_model.joblib` — modèle sérialisé
- `business_domain_test_predictions.csv` — prédictions sur le jeu de test
- `business_domain_metrics.json` — accuracy, F1, rapport de classification

### Analyser les erreurs du modèle

```bash
python -m src.ml.analyze_business_domain_errors
```

Génère dans `artifacts/` :
- `errors_all.csv` — toutes les erreurs de prédiction
- `errors_true_technique_pred_finance.csv` — cas Technique prédit Finance
- `errors_true_rh_pred_finance.csv` — cas RH prédit Finance
- `correct_technique.csv` — cas Technique bien classifiés

### Construire la file de re-labélisation prioritaire

Identifie les lignes les plus incertaines pour une révision manuelle.

```bash
python -m src.ml.build_relabeling_priority_set
```

Génère `artifacts/relabeling_priority_set.csv`.

---

## 11. Modifier la base de termes

Fichier à éditer : [`src/ml/domain_term_base.py`](src/ml/domain_term_base.py)

```python
DOMAIN_TERMS: dict[str, list[str]] = {
    "finance":      [...],   # → "Finance & Contrôle"
    "hr":           [...],   # → "RH"  (termes Paie inclus ici)
    "it":           [...],   # → "IT & Sécurité"
    "procurement":  [...],   # → "Achats & Fournisseurs"
    "sales":        [...],   # → "Ventes & Clients"
    "marketing":    [...],   # → "Ventes & Clients"
    "risk":         [...],   # → "Finance & Contrôle"
    "supply_chain": [...],   # → "Supply Chain / Logistique / Production"
}
```

> **Règle importante :** `DOMAIN_TERMS` est utilisé **uniquement** pour la
> pré-classification keywords. `DOMAIN_KEYWORDS` dans `score_business_domain.py`
> alimente les features numériques du modèle ML — **ne jamais modifier
> `DOMAIN_KEYWORDS` sans réentraîner le modèle**.

### Workflow recommandé après modification

```bash
# 1. Valider sur CSV (rapide, sans écrire en base)
python -m src.ml.reclassify_by_terms \
    --csv "exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_annotated.csv"

# 2. Vérifier exports/reclassified/*_focus_domains.csv
#    → contrôler la qualité des nouvelles classifications

# 3. Si OK, relancer le scoring complet en base
python -m src.transform.score_business_domain \
    --run-id 5 \
    --model-path "LLM/artifacts_business_domain/production_pipeline_latest.joblib"
```

---

## 12. Structure du projet

```
Projet/
├── src/
│   ├── config/
│   │   ├── settings.py                  # Configuration Pydantic (settings centralisés)
│   │   └── logging.py                   # Configuration Loguru
│   ├── connectors/
│   │   ├── postgres_client.py           # Client PostgreSQL (SQLAlchemy + retry)
│   │   └── oracle_client.py             # Client Oracle oracledb (thin mode)
│   ├── extract/
│   │   ├── oracle/                      # 5 extracteurs (record/table/column/index/segment_access)
│   │   ├── external/                    # API publique Azure Retail Prices
│   │   └── web/                         # Scraping tarifaire (Backblaze B2)
│   ├── load/
│   │   └── load_raw_oracle.py           # Chargeur raw_oracle (4 tables)
│   ├── transform/
│   │   ├── build_dim_asset.py
│   │   ├── build_dim_field.py
│   │   ├── build_bridge_asset_term.py
│   │   ├── build_fact_asset_profile.py
│   │   ├── build_fact_lineage_edge.py
│   │   ├── build_fact_archiving_event.py
│   │   ├── build_features_asset.py
│   │   ├── build_dataset_asset_ml.py
│   │   └── score_business_domain.py     # Scoring keywords + ML → serving
│   ├── ml/
│   │   ├── domain_term_base.py          # ← BASE DE TERMES (éditer ici)
│   │   ├── reclassify_by_terms.py       # ← Reclassification audit CSV/DB
│   │   ├── train_business_domain_classifier.py
│   │   ├── prepare_labeled_dataset.py
│   │   ├── analyze_business_domain_errors.py
│   │   └── build_relabeling_priority_set.py
│   ├── prefect/flows/
│   │   ├── flow_oracle_only.py          # Pipeline complet (Oracle)
│   │   ├── flow_init_db.py              # Initialisation DB
│   │   ├── flow_oracle_raw.py           # Extraction Oracle
│   │   ├── flow_build_processed.py      # Couche processed
│   │   └── flow_publish_serving.py      # Refresh vues serving
│   └── export/
│       └── export_dataset_asset_ml_for_labeling.py
├── sql/ddl/
│   ├── 001_schemas.sql                  # Création des 4 schémas
│   ├── 010_admin.sql                    # Table pipeline_run
│   ├── 020_raw_oracle.sql               # Tables raw_oracle
│   ├── 040_processed.sql                # Tables processed
│   └── 050_serving.sql                  # Tables + vues serving
├── sql/security/                        # pgcrypto (PII) + rôles moindre privilège
├── artifacts/
│   ├── business_domain_model.joblib     # Modèle baseline
│   ├── labeled_dataset_clean.csv        # Dataset d'entraînement nettoyé
│   └── ...                              # Métriques, erreurs, relabeling
├── exports/
│   ├── dataset_asset_ml_..._v4.csv      # Gold LLM (18 473 lignes, consensus ≥ 0.7)
│   ├── domain_model_run6.xlsx           # Export Excel des vues domaine/archivage/coûts
│   └── reclassified/                    # (régénérable à la demande via reclassify_by_terms)
├── LLM/
│   └── artifacts_business_domain/
│       └── production_pipeline_latest.joblib  # Modèle de production déployé (v3.4-human)
├── .env                                 # Secrets (ne pas committer)
├── .env.example                         # Template de configuration
├── requirements.txt
└── README.md
```

---

## 13. Schémas PostgreSQL

| Schéma | Tables / Vues | Description |
|---|---|---|
| `admin` | `pipeline_run` | Suivi des runs (run_id, status, timestamps) |
| `raw_oracle` | `record_catalog`, `table_catalog`, `column_catalog`, `index_catalog`, `segment_access` | Données PeopleSoft/Oracle brutes (5 catalogues) |
| `processed` | `dim_asset`, `dim_field`, `bridge_asset_term`, `fact_asset_profile`, `fact_lineage_edge`, `fact_archiving_event`, `features_asset`, `dataset_asset_ml` | Données transformées |
| `serving` | `asset_business_domain_prediction`, `mv_asset_inventory`, `mv_archivability_ranking`, `mv_roi_summary`, `v_asset_business_domain_scored` | Prédictions et KPIs |

---

## 14. Variables d'environnement

| Variable | Défaut | Obligatoire | Description |
|---|---|---|---|
| `APP_ENV` | `dev` | | `dev` / `staging` / `prod` |
| `LOG_LEVEL` | `INFO` | | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `POSTGRES_HOST` | `localhost` | | Hôte PostgreSQL |
| `POSTGRES_PORT` | `5432` | | Port PostgreSQL |
| `POSTGRES_DB` | `pfe_data_ia` | | Nom de la base |
| `POSTGRES_USER` | `postgres` | | Utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | — | **oui** | Mot de passe PostgreSQL |
| `ORACLE_HOST` | `192.168.11.111` | | Hôte Oracle PeopleSoft |
| `ORACLE_PORT` | `1521` | | Port Oracle |
| `ORACLE_SERVICE_NAME` | `EP92U038` | | Service Oracle |
| `ORACLE_USER` | `SYSADM` | | Utilisateur Oracle |
| `ORACLE_PASSWORD` | — | **oui** | Mot de passe Oracle |
| `ORACLE_OWNER` | `SYSADM` | | Schéma propriétaire Oracle |
| `RUN_ID` | *(UUID auto)* | | ID de run — laisser vide pour auto-génération |

---

## 15. Artefacts ML

### 15a. Modèle de production (scoring pipeline — LinearSVC)

| Fichier | Description |
|---|---|
| `LLM/artifacts_business_domain/production_pipeline_latest.joblib` | **Modèle de production déployé = v3.4-human** (LinearSVC+Platt, gold LLM + corrections d'apprentissage actif) — **utiliser pour le scoring** |
| `LLM/artifacts_business_domain/production_pipeline_v3.4-human_*.joblib` | Version horodatée du modèle déployé |
| `LLM/artifacts_business_domain/production_pipeline_v3.3-human_*.joblib`, `…v3.0_*.joblib` | Versions précédentes conservées en repli |
| `artifacts/production_model_card.md` | **Fiche du modèle déployé** (identité, vraies métriques, mises en garde) — source de vérité |
| `src/ml/train_production_classifier.py` | **Entraînement de production reproductible** (`--human-csv`, `--human-weight`, `--human-test-csv`, `--promote-latest`) |
| `src/ml/build_human_eval_sample.py` · `evaluate_human_gold.py` | Validation d'échantillon : génération d'un échantillon de labels (option `--disagreement-vs`) + comparaison des labels |
| `artifacts/human_eval_sample*.csv` · `human_eval_report*.json` | Échantillons de labels (3 lots) + rapports de validation d'échantillon |
| `src/ml/domain_term_base.py` | Base de termes pour la pré-classification keywords |
| `artifacts/business_domain_model.joblib`, `…_metrics.json`, `labeled_dataset_clean.csv`, `relabeling_priority_set.csv` | Piste **baseline** (obsolète, taxonomie 3-4 classes — ne pas confondre avec la production) |

### 15b. Modèle deep learning — XLM-RoBERTa v3 (inférence standalone, ONNX)

Classifieur XLM-R large fine-tuné sur PeopleSoft avec feature gating, Focal Loss (γ=2,0), calibration par température per-classe et offsets de décision SLA. **Ne nécessite pas PyTorch en inférence** — exécuté via ONNX Runtime.

| Fichier | Description |
|---|---|
| `artifacts/xlmr_v3/predict.py` | Point d'entrée inférence : `DomainClassifier(apply_offsets=False\|True).predict(row)` |
| `artifacts/xlmr_v3/features.py` | Feature builder vendorisé (129 features numériques + texte, identique au training) |
| `artifacts/xlmr_v3/artifacts/model.onnx` | Graphe ONNX (opset 17, ~215 Ko sans poids) |
| `artifacts/xlmr_v3/artifacts/temperatures.json` | 7 températures per-classe calibrées (ECE 0,052 → **0,011**) |
| `artifacts/xlmr_v3/artifacts/decision_offsets.json` | Offsets per-classe SLA-strict (Finance +2,26, RH +4,42, Ventes +5,42…) |
| `artifacts/xlmr_v3/artifacts/scaler_params.npz` | Paramètres StandardScaler pour les 129 features numériques |
| `artifacts/xlmr_v3/artifacts/class_labels.json` | Ordre canonique des 7 classes |
| `artifacts/xlmr_v3/requirements-inference.txt` | Dépendances inférence uniquement (`onnxruntime`, `transformers`, `numpy`) |
| `artifacts/xlmr_v3/README.md` | Architecture, métriques, modes équilibré / SLA-strict |
| `artifacts/xlmr_v1/` | Version v1 (température globale unique, sans offsets) — conservée pour comparaison |
| `artifacts/calibration_report.json` | Rapport ECE avant/après calibration (v1 vs v3) |
| `src/ml/model_reliability.py` | Phase 1 : calibration, SLA rappel, drift monitoring (`ModelReliabilityMonitor`) |

```bash
# Tester le modèle directement (standalone, sans base de données)
cd artifacts/xlmr_v3
pip install -r requirements-inference.txt
python predict.py        # demo sur 2 exemples prédéfinis

# Ou via le dashboard Streamlit (section "🤖 Test du modèle")
streamlit run app/streamlit_dashboard.py
```

> **Deux modes d'inférence :**
> - `apply_offsets=False` (défaut) — mode équilibré, optimise le macro-F1 global
> - `apply_offsets=True` — mode SLA-strict, élève le rappel sur les domaines réglementés (Finance, RH, Achats, Ventes)
