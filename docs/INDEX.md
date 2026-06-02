# Guide de travail — PFE Data IA
## Pipeline de gouvernance des données Oracle PeopleSoft EP92U038

> Ce guide documente l'ensemble du projet PFE. Chaque section contient deux fichiers :
> - **`_technique.md`** — implémentation, code, paramètres, commandes
> - **`_metier.md`** — explication accessible, valeur pour le projet, décisions

---

## Statut global

| Section | Description | Statut (lecture honnête) |
|---|---|---|
| [A](A_connexion_preparation/) | Connexion & préparation des données | ✅ Complet (extraction résiliente ; signal d'accès **prêt mais en attente de grant DBA**) |
| [B](B_classification_ml/) | Classification ML par objet métier | ✅ Complet — **justesse réelle ~75 % validée humainement** (≠ 89 % d'accord avec le LLM) |
| [C](C_modelisation_domaine/) | Modélisation logique par objet métier | ✅ Complet — graphe = **clés métier partagées** (vocabulaire), pas des dépendances FK |
| [D](D_regles_archivage/) | Règles d'archivage data-driven | ✅ Complet — recentré tables physiques + **domaine décisionnel** (rétention légale) |
| [E1](E1_gains_stockage/) | Gains de stockage et coût avant/après | ✅ Complet (échelle démo ~8 Go → montants illustratifs) |
| [E2](E2_comparaison_n1/) | Comparaison N-1 | ⚠️ **Simulé** (taux de croissance inversé — pas d'historique réel) |
| [E3](E3_projection_roi/) | Projection ROI multi-années | ⚠️ **Déterministe** (capitalisation à taux fixe — pas un modèle prédictif) |
| [E4](E4_repartition_couts/) | Répartition des coûts par objet métier | ✅ Complet |

> 📌 **Lire avant la soutenance : [« Lecture critique »](#lecture-critique--valeur-réelle-proxys-et-portée) ci-dessous** — ce qui est solide, ce qui est un proxy, et où se situe la vraie valeur du projet.

---

## Lecture critique : valeur réelle, proxys et portée

> Cette section assume honnêtement ce que le projet **est** (un prototype data-driven solide) et ce qu'il **n'est pas** (un outil de décision opérationnel clé en main). C'est plus robuste en soutenance que de tout présenter comme « 100 % terminé ».

### Où est la vraie valeur
- **Le cœur de la classification = règles mots-clés + supervision humaine ciblée.** Le LLM (`qwen2.5-32b`) a servi d'**amorce** pour étiqueter à grande échelle (distillation), et le modèle ML (LinearSVC) **généralise** ; mais c'est l'**annotation humaine active** (1 290 corrections) qui a fait passer la justesse réelle de **~51 % à ~75 %**. À présenter ainsi, pas comme « 89 % » (ce chiffre ne mesure que l'**accord avec le LLM** — circularité).
- **Pipeline de bout en bout reproductible** (extraction → ML → archivage → KPI), orchestré, idempotent, avec parité train/inférence garantie et un modèle versionné/traçable.
- **Archivage réellement piloté par le métier** : recentré sur les tables physiques + **rétention légale par domaine** (Finance/RH conservés, IT archivé).

### Proxys assumés (à nommer, pas à survendre)
| Élément | Ce qu'on mesure vraiment |
|---|---|
| « Fréquence d'accès » | **Récence d'écriture/analyse** (`last_analyzed`/`last_modified`). Le vrai signal de lecture est **prêt mais inactif** (grant DBA manquant — sondé). |
| « Graphe de dépendances » | **Clés métier partagées** (mêmes noms de champs) — vocabulaire/couplage, **pas** des dépendances FK (PeopleSoft n'en déclare pas). |
| « Lignage » (`fact_lineage_edge`) | **Hiérarchie de records** PeopleSoft (`parentrecname`), pas un lignage de flux de données. |
| Rétention légale par domaine | Valeurs **FR par défaut**, à valider par juridiction. |
| Âge d'archivage | **Inactivité de la table**, pas l'âge réel de la donnée. |

### Portée prototype
- **Échelle économique = démo** (~8 Go, ~14 $ d'économie sur 5 ans) : la **méthodologie** coût/ROI est valide, les **montants** sont illustratifs (à rejouer sur un volume de production).
- **E2 (comparaison N-1) = simulée** (pas d'historique réel) ; **E3 (ROI) = déterministe** (pas un modèle prédictif).
- **Gold test humain mono-annotateur** (pas d'accord inter-annotateurs).
- **Sources MongoDB hors périmètre** du run courant → pas de lignage/purges réels.

### Ce qui reste à durcir
Tests automatisés · vrai signal d'accès (grant DBA) · E2/E3 en vrais modèles (snapshots historiques + projection statistique).

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
