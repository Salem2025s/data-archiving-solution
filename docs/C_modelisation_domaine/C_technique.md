# C — Modélisation logique par objet métier : Fiche Technique

> **Statut :** ✅ Complet  
> **Résultats run_id=5 :** 7 profils de domaine, 531 liens de **clés métier partagées** (vocabulaire, non des dépendances FK), 142 candidats d'archivage listés

---

## 1. Objets PostgreSQL créés

| Objet | Type | Schéma |
|---|---|---|
| `dim_domain` | Table persistante | `serving` |
| `mv_domain_profile` | Vue matérialisée | `serving` |
| `mv_domain_dependency` | Vue matérialisée | `serving` |
| `v_archivability_by_domain` | Vue SQL (live) | `serving` |

---

## 2. `serving.dim_domain` — Table de référence des domaines

### DDL

```sql
CREATE TABLE IF NOT EXISTS serving.dim_domain (
    domain_id           SERIAL PRIMARY KEY,
    domain_label        TEXT NOT NULL UNIQUE,  -- correspond au label ML exact
    domain_key          TEXT NOT NULL UNIQUE,  -- clé courte (finance, hr, ...)
    description         TEXT,
    typical_objects     TEXT,
    typical_bridge_keys TEXT
);
```

### Contenu (7 lignes)

| domain_label | domain_key | typical_objects (extrait) | typical_bridge_keys |
|---|---|---|---|
| Finance & Contrôle | finance | VOUCHER, LEDGER, PROJECT | VOUCHER_ID, PROJECT_ID, BUSINESS_UNIT |
| IT & Sécurité | it | PSOPRDEFN, ROLEDEFN | OPRID, ROLENAME |
| Achats & Fournisseurs | procurement | PO_HDR, VENDOR, CNTRCT_HDR | PO_ID, VENDOR_ID, CONTRACT_NUM |
| Supply Chain / Logistique / Production | supply_chain | INV_ITEMS, IN_DEMAND | INV_ITEM_ID, SHIP_ID |
| RH | hr | PERSONAL_DATA, JOB, EMPLOYMENT | EMPLID, JOBCODE |
| Ventes & Clients | sales | CUSTOMER, ORDER_HDR, BI_HDR | CUST_ID, ORDER_NO |
| Other | other | — | — |

**Mise à jour :** upsert via `ON CONFLICT (domain_label) DO UPDATE` → safe à rejouer.

---

## 3. `serving.mv_domain_profile` — KPIs agrégés par domaine

### Colonnes

| Colonne | Type | Description |
|---|---|---|
| `domain_label` | TEXT | Nom du domaine |
| `asset_count` | BIGINT | Nombre d'assets classifiés dans ce domaine |
| `total_size_mb` | NUMERIC | Volume total des assets Oracle (Mo) |
| `archival_candidates` | BIGINT | Assets avec `archival_candidate_score > 60` |
| `estimated_gain_mb` | NUMERIC | Volume récupérable si archivage des candidats |
| `avg_archival_score` | NUMERIC(p=2) | Score moyen d'archivabilité |
| `avg_roi_score` | NUMERIC(p=2) | Score moyen de ROI |
| `avg_lineage_out` | NUMERIC(p=2) | Dépendances sortantes moyennes |
| `avg_nullable_ratio` | NUMERIC(p=4) | Ratio de colonnes nullable (qualité) |
| `assets_without_description` | BIGINT | Assets sans `description` renseignée |
| `risk_level` | TEXT | `HIGH` (avg_lineage_out ≥ 10) / `MEDIUM` (≥3) / `LOW` (<3) |

### Requête de construction (résumé)

```sql
WITH latest AS (SELECT MAX(run_id) AS run_id FROM processed.dim_asset),
domain_assets AS (
    SELECT p.business_domain_predicted, da.description,
           f.size_mb, f.archival_candidate_score, f.roi_score,
           f.lineage_out_count, ml.field_count, ml.nullable_field_count
    FROM latest
    JOIN processed.dim_asset da ON ...
    JOIN serving.asset_business_domain_prediction p ON ...
    LEFT JOIN processed.features_asset f ON ...
    LEFT JOIN processed.dataset_asset_ml ml ON ...
)
SELECT domain_label, COUNT(*), SUM(size_mb), ...
GROUP BY domain_label
```

**Refresh :**
```bash
python -m src.transform.build_serving_domain_model
```

### Résultats run_id=5

| Domaine | Assets | Volume (Mo) | Candidats archivage | Risk |
|---|---|---|---|---|
| Finance & Contrôle | 74 401 | 535 | 0 | LOW |
| IT & Sécurité | 39 933 | 6 215 | 2 | LOW |
| Other | 18 522 | 1 200 | 0 | LOW |
| Achats & Fournisseurs | 13 198 | 23 | 0 | LOW |
| Supply Chain | 12 453 | 37 | 0 | LOW |
| Ventes & Clients | 5 171 | 2 | 0 | LOW |
| RH | 3 585 | 9 | 0 | LOW |

> `archival_candidates = 0` sur tous les domaines car `purge_event_count = 0`
> (MongoDB hors scope : `fact_archiving_event` est vide — ce point sera corrigé en section D/E).

---

## 4. `serving.mv_domain_dependency` — Graphe des clés métier partagées (vocabulaire)

> ⚠️ **Sémantique honnête :** PeopleSoft ne déclare aucune clé étrangère. Ce graphe relie deux domaines qui **emploient le même nom de champ en clé primaire** (ex. `SETID`). C'est un signal de **vocabulaire commun / couplage potentiel**, **pas** une dépendance référentielle prouvée. Le nom d'objet `mv_domain_dependency` est conservé (compatibilité), mais il s'agit bien de **clés partagées**.

### Algorithme de construction

```
1. Extraire les champs de clé primaire de raw_oracle.index_catalog (indexid = '0')
2. Mapper chaque record à son domaine via asset_business_domain_prediction
3. Compter, pour chaque champ, le nombre de records par domaine
4. Garder les champs présents dans ≥ 2 domaines avec ≥ 10 records au total
5. Créer des paires (domaine_A, domaine_B, champ_bridge, nb_records)
```

### Colonnes

| Colonne | Description |
|---|---|
| `source_domain` | Premier domaine (ordre alphabétique) |
| `target_domain` | Second domaine |
| `bridge_field` | Nom du champ partagé en clé primaire |
| `shared_asset_count` | Nombre de records partagés (somme des deux domaines) |

### Top 5 arêtes par volume

| source_domain | target_domain | bridge_field | shared_asset_count |
|---|---|---|---|
| Finance & Contrôle | IT & Sécurité | SETID | 532 |
| Finance & Contrôle | Other | DESCR | 501 |
| Finance & Contrôle | IT & Sécurité | DESCR | 461 |
| Finance & Contrôle | Other | SETID | 445 |
| Achats & Fournisseurs | Finance & Contrôle | SETID | 432 |

**Interprétation :** SETID est un champ de configuration qui apparaît dans des records Finance ET IT → ce n'est pas une vraie dépendance métier, mais une clé de paramétrage transverse. Les champs métier réels (VOUCHER_ID, PO_ID...) apparaissent avec moins de records mais sont plus significatifs pour les décisions d'archivage.

---

## 5. `serving.v_archivability_by_domain` — Top candidats par domaine

```sql
CREATE OR REPLACE VIEW serving.v_archivability_by_domain AS
WITH latest AS (SELECT MAX(run_id) AS run_id FROM processed.dim_asset),
ranked AS (
    SELECT p.business_domain_predicted AS domain_label,
           da.technical_name, da.business_name,
           f.archival_candidate_score, f.roi_score, f.size_mb,
           f.lineage_out_count, f.row_count,
           RANK() OVER (
               PARTITION BY p.business_domain_predicted
               ORDER BY f.archival_candidate_score DESC NULLS LAST
           ) AS domain_rank
    FROM latest
    JOIN processed.dim_asset da ON ...
    JOIN serving.asset_business_domain_prediction p ON ...
    LEFT JOIN processed.features_asset f ON ...
)
SELECT * FROM ranked WHERE domain_rank <= 20;
```

Vue SQL standard (pas de REFRESH nécessaire) — toujours à jour sur MAX(run_id).

---

## 6. Script de build — `src/transform/build_serving_domain_model.py`

Séquence d'exécution :
1. Upsert des 7 lignes dans `serving.dim_domain`
2. `REFRESH MATERIALIZED VIEW serving.mv_domain_profile`
3. `REFRESH MATERIALIZED VIEW serving.mv_domain_dependency`

Durée : ~4 secondes sur run_id=5.

---

## 7. Export Excel — `src/export/export_domain_model.py`

**Fichier produit :** `exports/domain_model_run<N>.xlsx`

Le classeur compte **13 feuilles** au total (Dashboard + domaine + archivage + coût/ROI + Metadata). Les **3 feuilles produites par la section C** :

| Feuille | Contenu | Nb lignes run6 |
|---|---|---|
| Domain Profile | `mv_domain_profile` complet | 7 |
| Domain Shared Keys | `mv_domain_dependency` complet (clés partagées) | 573 |
| Top Archival Candidates | `v_archivability_by_domain` (top 20/domaine) | 144 |

> Les feuilles d'archivage (D) et de coût/ROI (E1–E4) ainsi que **Dashboard** (5 graphiques) et **Metadata** sont décrites dans leurs sections respectives.

**Commande :**
```bash
python -m src.export.export_domain_model
# Produit : exports/domain_model_run5.xlsx
```

---

## 8. Intégration dans le pipeline

`flow_publish_serving` (Prefect) appelle maintenant `build_serving_domain_model()` après le refresh des 3 MVs existants :

```python
# flow_publish_serving.py
for view_name in MATERIALIZED_VIEWS:    # mv_asset_inventory, mv_archivability_ranking, mv_roi_summary
    refresh_materialized_view(...)
build_serving_domain_model()             # ← ajouté section C
```

Total : 5 MVs refreshées + dim_domain upsert à chaque run.
