# D — Règles d'archivage data-driven : Fiche Technique

> **Statut :** ✅ Complet  
> **Périmètre :** recentré sur les **~16 800 tables PHYSIQUES** (qui occupent réellement du stockage) — les ~150 k records logiques PeopleSoft sont écartés en amont.
> **Décision pilotée par le domaine :** rétention légale par domaine (Finance/RH réglementés ≠ IT) → stratégie `CONSERVATION_REGLEMENTAIRE`.

---

## 1. Principe : moteur de règles multi-dimensionnel

La spécification demande d'analyser **volumes, fréquences d'accès, ancienneté et sensibilité**. La décision d'archivage est calculée à partir de **dimensions physiques concrètes**, et non à partir du `archival_candidate_score`.

> **Recentrage économique (correction) :** la MV ne porte plus que sur les **actifs physiques** (`size_mb > 0 OR row_count > 0`), soit ~16 800 tables. Les ~150 k records logiques PeopleSoft (sans stockage) — auparavant classés `NON_APPLICABLE` — sont **filtrés en amont** : métriques d'archivage/coût alignées sur l'objectif économique.

> **Le DOMAINE est désormais une dimension de décision (correction) :** une 5ᵉ dimension, la **rétention légale/métier par domaine** (`serving.dim_domain_retention`), rend la classification *actrice* de la décision (et non plus seulement un axe de reporting). Un domaine **réglementé** (Finance, RH, Achats, Ventes) dont la donnée est encore dans sa fenêtre de rétention n'est **pas archivable à froid** → `CONSERVATION_REGLEMENTAIRE`. Le **seuil d'archivabilité dépend donc du domaine** (IT : 1 an ; Finance : 10 ans).

### Pourquoi pas le score ?

Analyse de la distribution sur run_id=5 :

| Bucket de score | Nb assets |
|---|---|
| 40–50 | **166 996 (99,8 %)** |
| autres | 267 |

Le score est faussé par `term_count = 0` (composante +25 constante) et `lineage_out = 0` (composante +20 pour les feuilles) → il ne différencie pas les assets. **Décision : s'appuyer sur les dimensions physiques.**

---

## 2. Les 4 dimensions analysées

| Dimension | Source PostgreSQL | Disponibilité run_id=5 |
|---|---|---|
| **Volume** | `features_asset.size_mb`, `row_count` | 16 941 assets avec données (>0) |
| **Ancienneté** | `GREATEST(fact_asset_profile.last_analyzed, table_catalog.last_modified)` | 109 107 assets datés |
| **Sensibilité** | `dataset_asset_ml.column_value_semantics_text` | 10 134 PII + 23 662 financiers |
| **Dépendances (hiérarchie)** | `features_asset.lineage_out_count` | 4 590 arêtes ps_parent_record |
| **Références (objets stockés)** | `table_catalog.referenced_by_count` → `is_orphan` | ✅ actif (run 6) |
| **Accès (lectures réelles)** | `raw_oracle.segment_access.logical_reads` (V$SEGMENT_STATISTICS) → `access_band` | 🔒 prêt mais inactif (grant DBA requis — voir ci-dessous) |

> **Fréquence d'accès — verdict sondé (2026-06).** Oracle n'expose pas de compteur de **lecture** accessible à SYSADM. Probe direct sur EP92U038 : **toutes** les vues de stats par segment renvoient `ORA-00942` pour SYSADM — `V$SEGMENT_STATISTICS`, `V$SEGSTAT`, `SYS.V_$SEGMENT_STATISTICS`, `DBA_HIST_SEG_STAT` (AWR). Ce n'est donc **pas un manque d'implémentation** mais un **blocage de permissions**. Un **extracteur défensif** (`extract_segment_access.py`) et une **6ᵉ dimension** (`access_band`) sont déjà branchés ; ils restent **inertes** (signal `inconnu`) tant que le grant n'est pas accordé, et s'activent automatiquement ensuite — **sans toucher au code**. Pour activer un vrai signal de lecture (sans licence Diagnostics Pack), un DBA doit exécuter :
> ```sql
> GRANT SELECT ON SYS.V_$SEGMENT_STATISTICS TO SYSADM;
> ```
> À défaut, on retombe sur l'**activité d'écriture/analyse** (`last_analyzed`/`last_modified`) comme proxy.

### ⚠️ Sonde Oracle (2026-05-29) — ce qui existe réellement

Deux signaux Oracle ont été ajoutés à l'extraction ([extract_table_catalog.py](../../src/extract/oracle/extract_table_catalog.py)) puis **validés en lecture seule sur l'instance EP92U038** :

| Signal | Source Oracle | Verdict sonde |
|---|---|---|
| `last_modified` | `ALL_TAB_MODIFICATIONS` | ❌ **Quasi inexistant** : 47 tables / 79 633 (0,06 %), absent des plus grosses. Oracle vide l'entrée après collecte de stats → **pas un signal d'âge fiable**. On garde `last_analyzed`. |
| `referenced_by_count` | `ALL_DEPENDENCIES` | ✅ **Riche** : 80 294 dépendances, 7 210 tables référencées (1 à 3 206 réf.). Signal exploitable. |
| `logical_reads` (accès) | `V$SEGMENT_STATISTICS` | 🔒 **Inaccessible** (`ORA-00942`) : SYSADM n'a aucun droit sur les vues `V$`/`DBA_*` de stats segment (sondé 2026-06). Extracteur prêt, activable par grant DBA (signal `inconnu` sinon). |

**Statut : ACTIVÉ sur run_id=6** (ré-extraction Oracle complète via `flow_oracle_only`). `referenced_by_count` peuplé pour 109 775 assets, `is_orphan` = 95 867, **piliers ≥ 20 réf. = 1 256**. (`last_modified` : 29 seulement → confirmé inexploitable, l'âge retombe sur `last_analyzed`.)

**Impact de la règle de protection ≥ 20 (run 5 → run 6) :**

| Stratégie | run 5 (dormant) | run 6 (actif) |
|---|---|---|
| CONSERVATION_CRITIQUE | 73 (20 Mo) | **1 135 (822 Mo)** |
| ARCHIVAGE_FROID | 13 450 (7 636 Mo) | 13 251 (6 919 Mo) |

→ ~1 060 piliers structurels (≈800 Mo) **retirés de l'archivage** et protégés. Exemples : SET_CNTRL_REC (3 206 réf.), VENDOR (1 460), BUS_UNIT_TBL_FS (1 103).

> **Note d'usage de `referenced_by_count` :** ~91 % des tables SYSADM ne sont référencées par aucun objet stocké (l'appli les requête en SQL direct). Donc *orphelin → archiver* est un signal **faible/support** (combiné à l'âge), tandis que l'inverse — un `referenced_by_count` **élevé** — est un signal de **protection fort** (pilier structurel à conserver). Piste d'amélioration retenue.

### Bandes d'ancienneté (`age_band`)

| Bande | Critère | Interprétation |
|---|---|---|
| `tres_ancien` | > 3 ans (1095 j) | Non touché depuis longtemps → archivable |
| `ancien` | > 1 an | Peu actif |
| `moyen` | > 3 mois | Activité modérée |
| `recent` | ≤ 3 mois | Actif |
| `inconnu` | `last_analyzed` NULL | Statistiques absentes |

### Niveaux de sensibilité (`sensitivity_level`)

| Niveau | Sémantiques détectées (regex sur `column_value_semantics_text`) |
|---|---|
| `HAUTE` | person_identifier, email_address, phone_number, person_first/last/full_name |
| `MOYENNE` | financial_amount, user_identifier |
| `FAIBLE` | autres sémantiques présentes |
| `AUCUNE` | pas de sémantique |

---

## 3. Objets PostgreSQL créés

| Objet | Type | Rôle |
|---|---|---|
| `serving.dim_archiving_policy` | Table | 9 stratégies de référence |
| `serving.dim_domain_retention` | Table | Plancher de rétention légale/métier + flag `regulated` par domaine |
| `serving.mv_archiving_recommendation` | Vue matérialisée | 1 recommandation par **table physique** (~16 828 lignes) |
| `serving.v_archiving_policy_summary` | Vue SQL | Agrégat par domaine × stratégie + `effective_retention_years` |

---

## 4. `serving.dim_archiving_policy` — Les 9 stratégies

| priorité | strategy_code | Rétention | Traitement |
|---|---|---|---|
| 0 | `NON_APPLICABLE` | — | Aucune action (objet logique sans stockage) — *désormais inatteignable : périmètre physique* |
| 1 | `CONSERVATION_CRITIQUE` | — | Conserver — ne jamais archiver (≥10 dépendants ou ≥20 réf.) |
| 2 | `ARCHIVAGE_CHIFFRE` | 7 ans | Stockage froid chiffré (PII anciennes, RGPD) |
| 3 | `CONSERVATION_SECURISEE` | — | Conserver + contrôle d'accès renforcé (PII active) |
| 3 | `CONSERVATION_REGLEMENTAIRE` | *plancher domaine* | **Domaine réglementé encore dans sa fenêtre de rétention légale → conserver, ne pas archiver** |
| 4 | `ARCHIVAGE_FROID` | 10 ans | Stockage froid S3/bande (données inactives au-delà de la rétention) |
| 5 | `COMPRESSION` | 5 ans | Compression Oracle ou externalisation |
| 6 | `A_EVALUER` | — | Analyse manuelle (volume important, âge inconnu) |
| 7 | `CONSERVATION` | — | Conserver en actif (récent / faible potentiel) |

**`serving.dim_domain_retention`** (plancher de rétention par domaine, peuplé par `build_archiving_rules.py`) :

| Domaine | `min_retention_years` | `regulated` | Base |
|---|---|---|---|
| Finance & Contrôle | 10 | ✅ | Pièces comptables — Code de commerce art. L123-22 |
| Ventes & Clients | 10 | ✅ | Factures clients (10 ans) |
| Achats & Fournisseurs | 10 | ✅ | Factures / contrats fournisseurs (10 ans) |
| RH | 5 | ✅ | Bulletins de paie / contrats (Code du travail) |
| Supply Chain / Logistique / Production | 3 | ❌ | Documents logistiques (usage) |
| Other | 3 | ❌ | Défaut prudent |
| IT & Sécurité | 1 | ❌ | Logs techniques (rétention courte) |

---

## 5. Arbre de décision (CASE dans la MV)

L'ordre de priorité est strict : la première règle satisfaite l'emporte.

> Le périmètre est filtré en amont aux **actifs physiques** (`WHERE size_mb>0 OR row_count>0`), donc la branche `NON_APPLICABLE` n'est jamais atteinte (conservée par compatibilité).

```sql
CASE
    WHEN size_mb = 0 AND row_count = 0                          THEN 'NON_APPLICABLE'  -- inatteignable (filtre physique)
    WHEN lineage_out_count >= 10                                THEN 'CONSERVATION_CRITIQUE'  -- pilier (hiérarchie PS)
    WHEN referenced_by_count >= 20                              THEN 'CONSERVATION_CRITIQUE'  -- pilier (objets stockés)
    WHEN sensitivity = 'HAUTE' AND age IN ('ancien','tres_ancien') THEN 'ARCHIVAGE_CHIFFRE'
    WHEN sensitivity = 'HAUTE'                                  THEN 'CONSERVATION_SECURISEE'
    -- DOMAINE = INPUT : réglementé + encore dans la fenêtre légale (âge inconnu = prudence)
    WHEN regulated AND (age_days IS NULL OR age_days < min_retention_years*365) THEN 'CONSERVATION_REGLEMENTAIRE'
    -- ACCÈS = 6e dimension (NULL-safe) : table encore LUE -> conserver. access_band
    -- = 'inconnu' tant que le grant DBA est absent -> cette règle reste inerte.
    WHEN access_band = 'actif'                                  THEN 'CONSERVATION'  -- lue (V$SEGMENT_STATISTICS)
    WHEN age = 'tres_ancien'                                    THEN 'ARCHIVAGE_FROID'
    WHEN is_orphan AND age IN ('ancien','moyen') AND size_mb>0  THEN 'ARCHIVAGE_FROID'  -- orphelin + inactif
    WHEN age = 'inconnu' AND size_mb >= 50                      THEN 'A_EVALUER'
    WHEN age = 'ancien' OR (age = 'moyen' AND size_mb >= 10)    THEN 'COMPRESSION'
    ELSE                                                             'CONSERVATION'
END
```

> Conséquence concrète : une table **Finance** inactive depuis 4 ans (`tres_ancien`) reste **conservée** (fenêtre légale 10 ans non écoulée), alors qu'une table **IT** identique part en `ARCHIVAGE_FROID` (rétention 1 an). Le **même âge** mène à des **décisions différentes selon le domaine** — c'est l'effet recherché par le plan.

> **`referenced_by_count` à double tranchant** : un compte **élevé** (≥ 20 objets stockés dépendants) = **pilier → conservation** (protège des faux positifs d'archivage) ; un compte **nul** (`is_orphan`) = signal **faible** de support à l'archivage (combiné à l'âge), car ~91 % des tables ne sont référencées par aucun objet stocké. Seuil `20` ajustable.

- **`age`** est dérivé de `GREATEST(last_analyzed, last_modified)` — la trace d'activité la plus récente. `GREATEST` ignore les NULL en PostgreSQL, donc repli automatique sur `last_analyzed` quand `last_modified` est absent.
- **`is_orphan`** = `(referenced_by_count = 0)`, NULL-safe : si `referenced_by_count` n'est pas extrait (NULL), `is_orphan` vaut NULL et la règle orpheline ne se déclenche pas.

Chaque recommandation est accompagnée d'une colonne `rationale` (ex. : `volume_eleve(2215Mo); inactif_>3ans; orpheline(0_objet_dependant)`).

---

## 6. Résultats run_id=6 (périmètre physique + domaine décisionnel)

### Distribution globale (16 828 tables physiques)

| Stratégie | Nb assets |
|---|---|
| **CONSERVATION_REGLEMENTAIRE** | **6 895** *(domaines réglementés dans leur fenêtre légale)* |
| **ARCHIVAGE_FROID** | **6 854** |
| ARCHIVAGE_CHIFFRE | 1 620 |
| CONSERVATION_CRITIQUE | 1 135 |
| CONSERVATION | 196 |
| CONSERVATION_SECURISEE | 122 |
| COMPRESSION | 6 |

**Total archivable (FROID + CHIFFRE + COMPRESSION) : ~8 480 tables, ~6,6 Go** (vs ~6,9 Go avant la prise en compte de la rétention légale → ~0,3 Go conservés pour conformité).

### Effet du domaine (même logique, décisions opposées)

| Domaine | Réglementé | Stratégie dominante | Nb |
|---|---|---|---|
| Finance & Contrôle | ✅ 10 ans | **CONSERVATION_REGLEMENTAIRE** | 5 369 |
| Achats & Fournisseurs | ✅ 10 ans | CONSERVATION_REGLEMENTAIRE | 1 045 |
| Ventes & Clients | ✅ 10 ans | CONSERVATION_REGLEMENTAIRE | 351 |
| RH | ✅ 5 ans | ARCHIVAGE_CHIFFRE (PII) + REGLEMENTAIRE | 387 + 130 |
| **IT & Sécurité** | ❌ 1 an | **ARCHIVAGE_FROID** | 4 590 |
| Other / Supply Chain | ❌ 3 ans | ARCHIVAGE_FROID | 1 370 / 749 |

---

## 7. Script de build — `src/transform/build_archiving_rules.py`

```bash
python -m src.transform.build_archiving_rules
```

Séquence (3 étapes) :
1. Upsert des **9 stratégies** dans `dim_archiving_policy` (idempotent `ON CONFLICT`)
2. Upsert de `dim_domain_retention` (**7 domaines** — plancher de rétention légale/métier)
3. `REFRESH MATERIALIZED VIEW serving.mv_archiving_recommendation`

Durée : ~7 s.

---

## 8. Intégration pipeline

`flow_publish_serving` appelle `build_archiving_rules()` après `build_serving_domain_model()` :

```python
for view_name in MATERIALIZED_VIEWS:   # 3 MVs de base
    refresh_materialized_view(...)
build_serving_domain_model()           # section C
build_archiving_rules()                # section D
```

---

## 9. Export Excel

`src/export/export_domain_model.py` produit **13 feuilles** au total (Dashboard + domaine + archivage + coût/ROI + Metadata), dont 4 pour l'archivage :

| Feuille | Source | Lignes run6 |
|---|---|---|
| Archiving Policies | `dim_archiving_policy` | 9 |
| Archiving by Domain | `v_archiving_policy_summary` | 32 |
| Archiving Actions | `mv_archiving_recommendation` (FROID/CHIFFRE/COMPRESSION) | top 1000 |
| Archiving by Strategy | `mv_archiving_recommendation` (agrégat par stratégie) | 7 |

```bash
python -m src.export.export_domain_model
# → exports/domain_model_run6.xlsx
```

---

## 10. Requêtes utiles

```sql
-- Distribution des stratégies
SELECT recommended_strategy, COUNT(*), ROUND(SUM(size_mb)::numeric,1) AS mb
FROM serving.mv_archiving_recommendation
GROUP BY recommended_strategy ORDER BY 3 DESC;

-- Top tables à archiver à froid
SELECT technical_name, domain_label, size_mb, age_band, rationale
FROM serving.mv_archiving_recommendation
WHERE recommended_strategy = 'ARCHIVAGE_FROID'
ORDER BY size_mb DESC LIMIT 20;

-- Données personnelles à archiver (RGPD)
SELECT domain_label, COUNT(*), ROUND(SUM(size_mb)::numeric,1) AS mb
FROM serving.mv_archiving_recommendation
WHERE recommended_strategy = 'ARCHIVAGE_CHIFFRE'
GROUP BY domain_label ORDER BY 2 DESC;
```

---

## 11. Limites & évolutions

| Limite | Statut / évolution |
|---|---|
| ~~Classification non décisionnelle~~ | ✅ **Corrigé** : le domaine pilote la rétention (`CONSERVATION_REGLEMENTAIRE`) |
| ~~Périmètre pollué par 150 k objets logiques~~ | ✅ **Corrigé** : MV recentrée sur les tables physiques |
| Signal d'accès (lecture) indisponible pour SYSADM (`ORA-00942`, sondé) | ✅ **Prêt à activer** : extracteur `segment_access` + 6ᵉ dimension `access_band` branchés (inertes) ; un `GRANT SELECT ON SYS.V_$SEGMENT_STATISTICS TO SYSADM` les active sans modif de code |
| `purge_event_count = 0` (MongoDB hors scope) | Connecter `raw_mongo.archlog_purge` → signal d'usage |
| Planchers de rétention codés par défaut (FR) | Externaliser dans une table éditable (par juridiction) |
| Âge = inactivité de la table, pas âge de la donnée | `age_days` proxy : une table active peut contenir de la donnée hors rétention (et inversement) |
| Double comptage ps_record + oracle_table | Le même fichier physique peut apparaître 2× (record PS + table Oracle) |
