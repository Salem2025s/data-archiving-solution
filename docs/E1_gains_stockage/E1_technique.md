# E1 — Gains de stockage et coût avant/après : Fiche Technique

> **Statut :** ✅ Complet  
> **Devise :** USD · **Run de référence :** run_id = 5

---

## 1. Modèle de coût (paramètres réels)

Stockés dans `serving.dim_cost_params`, alimentés depuis l'**API publique Azure
Retail Prices** (`src/extract/external/fetch_cloud_storage_prices.py --apply`) —
tarifs réels et rejouables, non plus des constantes codées en dur :

| param_name | Valeur | Unité | Base |
|---|---|---|---|
| `storage_cost_per_gb_per_year` | 0.211968 | USD/Go/an | Azure Hot LRS (0,0177 $/Go/mois) |
| `cold_storage_cost_per_gb_year` | 0.0216 | USD/Go/an | Azure Archive LRS (0,0018 $/Go/mois) |
| `compression_ratio` | 0.5 | ratio | Taille résiduelle après compression (−50 %) |
| `data_growth_rate_pct_per_year` | 15.0 | %/an | Croissance annuelle (moyenne, hypothèse E3) |
| `data_growth_std_pct_per_year` | 5.0 | %/an | Écart-type de la croissance (incertitude Monte-Carlo E3) |
| `implementation_cost_one_shot` | 0.0 | USD | Tiering cloud = pas de capex |

**Mise à jour depuis la source :** `python -m src.extract.external.fetch_cloud_storage_prices --apply`
puis re-run `build_cost_analysis`. (Modification manuelle toujours possible via
`UPDATE serving.dim_cost_params SET param_value = ... WHERE param_name = ...`.)

---

## 2. Modèle de coût par asset

Le coût après archivage est calculé selon la **stratégie réelle de la section D** (pas un seuil de score) :

```
cost_current = size_gb × cost_active

cost_after = CASE
    WHEN strategy IN ('ARCHIVAGE_FROID','ARCHIVAGE_CHIFFRE') THEN size_gb × cost_cold
    WHEN strategy = 'COMPRESSION'                            THEN size_gb × 0.5 × cost_active
    ELSE                                                          size_gb × cost_active
END

savings = cost_current − cost_after
```

---

## 3. Objets créés

| Objet | Type | Rôle |
|---|---|---|
| `serving.dim_cost_params` | Table | Paramètres de coût (6 lignes) |
| `serving.mv_cost_analysis` | Vue matérialisée | Coût par domaine (avant/après/économie) |
| `serving.v_storage_impact_summary` | Vue | Synthèse globale + taux normalisé au To |

### `mv_cost_analysis` — colonnes

| Colonne | Description |
|---|---|
| `domain_label` | Domaine |
| `total_size_gb` | Volume total (Go) |
| `archivable_size_gb` | Volume archivable (FROID+CHIFFRE+COMPRESSION) |
| `current_cost_usd_year` | Coût actuel ($/an) |
| `cost_after_archiving_usd_year` | Coût après archivage ($/an) |
| `annual_savings_usd` | Économie annuelle ($/an) |
| `savings_pct` | % de réduction |

---

## 4. Résultats run_id=5

### Synthèse globale (`v_storage_impact_summary`)

| Indicateur | Valeur |
|---|---|
| Patrimoine total | 7,835 Go |
| Volume archivable | 7,668 Go (97,9 %) |
| Coût actuel | **2,16 $/an** |
| Coût après archivage | 0,43 $/an |
| Économie annuelle | **1,73 $/an (−80,1 %)** |
| **Taux d'économie normalisé** | **233,47 $ / To archivé / an** |

> **Lecture pour le PFE :** les montants absolus sont faibles car l'instance EP92U038 est une base de démonstration (~8 Go physiques, 90 % des objets vides). La métrique transposable est le **taux : 233 $/To archivé/an**. Sur une instance production de 10 To archivables, l'économie serait ≈ 2 335 $/an.

---

## 5. Script de build

`src/transform/build_cost_analysis.py` :
1. Upsert `dim_cost_params`
2. `REFRESH MATERIALIZED VIEW serving.mv_cost_analysis`
3. Calcule la projection ROI (voir E3)

```bash
python -m src.transform.build_cost_analysis
```

---

## 6. Requêtes utiles

```sql
SELECT * FROM serving.v_storage_impact_summary;

SELECT domain_label, current_cost_usd_year, annual_savings_usd, savings_pct
FROM serving.mv_cost_analysis
ORDER BY annual_savings_usd DESC;
```

---

## 7. Export Excel

Feuilles produites par `export_domain_model.py` : **Cost Parameters** + **Cost by Domain** (voir E4).
