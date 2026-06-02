# Guide de travail — PFE Data IA
## Pipeline de gouvernance des données Oracle PeopleSoft EP92U038

> Ce guide documente l'ensemble du projet PFE. Chaque section contient deux fichiers :
> - **`_technique.md`** — implémentation, code, paramètres, commandes
> - **`_metier.md`** — explication accessible, valeur pour le projet, décisions

---

## Statut global

| Section | Description | Statut |
|---|---|---|
| [A](A_connexion_preparation/) | Connexion & préparation des données | ✅ Complet |
| [B](B_classification_ml/) | Classification ML par objet métier | ✅ Complet |
| [C](C_modelisation_domaine/) | Modélisation logique par objet métier | ✅ Complet |
| [D](D_regles_archivage/) | Règles d'archivage data-driven | ✅ Complet |
| [E1](E1_gains_stockage/) | Gains de stockage et coût avant/après | ✅ Complet |
| [E2](E2_comparaison_n1/) | Comparaison N-1 | ✅ Complet (simulé) |
| [E3](E3_projection_roi/) | Projection ROI multi-années | ✅ Complet |
| [E4](E4_repartition_couts/) | Répartition des coûts par objet métier | ✅ Complet |

---

## Architecture du projet

```
Oracle PeopleSoft EP92U038
        │
        ▼ (extract/oracle/ — 4 extracteurs)
raw_oracle.{record_catalog, table_catalog, column_catalog, index_catalog}
        │
        ▼ (transform/ — 8 étapes)
processed.{dim_asset, dim_field, bridge_asset_term, fact_asset_profile,
           fact_lineage_edge, fact_archiving_event, features_asset, dataset_asset_ml}
        │
        ▼ (ML — score_business_domain.py)
serving.asset_business_domain_prediction  [167 263 assets classifiés]
        │
        ▼ (flow_publish_serving + build_serving_domain_model)
serving.{mv_asset_inventory, mv_archivability_ranking, mv_roi_summary,
         dim_domain, mv_domain_profile, mv_domain_dependency,
         v_archivability_by_domain, v_asset_business_domain_scored,
         dim_archiving_policy, mv_archiving_recommendation,
         v_archiving_policy_summary,
         dim_cost_params, mv_cost_analysis, v_storage_impact_summary,
         v_n1_comparison, v_cost_by_domain, roi_projection,
         v_roi_projection_summary}
        │
        ▼ (export/ — 13 feuilles dont Dashboard avec 5 graphiques)
exports/domain_model_run5.xlsx
```

---

## Run courant

| Paramètre | Valeur |
|---|---|
| `run_id` actif | 6 (ré-extraction Oracle avec `referenced_by_count`) |
| Modèle de domaine déployé | **v3.4-human** (LinearSVC+Platt, gold LLM + 1 130 corrections humaines) — justesse réelle ~75 % sur cas durs |
| Assets classifiés | 167 260 |
| Arêtes de lignage (`ps_parent_record`) | 4 590 |
| Arêtes inter-domaines (bridge keys) | 573 |
| Assets archivables (FROID + CHIFFRE + COMPRESSION) | ~14 900 (~7,1 Go) |
| Piliers protégés (`referenced_by_count` ≥ 20) | 1 135 (CONSERVATION_CRITIQUE) |
| Taux d'économie normalisé | 233 $/To archivé/an |

---

## Commandes de référence rapide

```bash
# Environnement
.venv\Scripts\activate

# Pipeline complet (Oracle + MongoDB)
python -m src.prefect.flows.flow_full_pipeline

# Pipeline Oracle seul (sans MongoDB — nouveau run_id)
python -m src.prefect.flows.flow_oracle_only

# Publier la couche serving (MVs + domaines)
python -m src.prefect.flows.flow_publish_serving

# Modèle de domaine uniquement
python -m src.transform.build_serving_domain_model

# Règles d'archivage uniquement
python -m src.transform.build_archiving_rules

# Analyse de coût + projection ROI
python -m src.transform.build_cost_analysis

# Export Excel complet (11 feuilles : domaine + archivage + coût/ROI)
python -m src.export.export_domain_model

# Dashboard interactif (démo web, lecture seule sur la couche serving)
pip install -r requirements-ml.txt   # installe streamlit (une fois)
streamlit run app/streamlit_dashboard.py
```

> **Dashboard / Interface Streamlit** (`app/streamlit_dashboard.py`) — 7 sections, sans terminal :
> - **Consultation** (lecture `serving.*`) : Vue d'ensemble (KPIs) · Domaines · Dépendances · Archivage (filtres domaine/stratégie) · Coûts & ROI (camembert, Pareto, projection).
> - **🚀 Pipelines** : boutons pour lancer chaque traitement (publication serving, exports, régénérations) + **pipeline complet** (extraction Oracle/Mongo, VPN requis) avec **logs en direct** et historique des runs (`admin.pipeline_run`).
> - **⚙️ Paramètres** : formulaires d'édition des coûts/ROI (`dim_cost_params`) avec recalcul « what-if » + bouton **réinitialiser aux valeurs par défaut**.
