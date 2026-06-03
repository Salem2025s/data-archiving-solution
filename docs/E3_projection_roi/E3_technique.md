# E3 — Projection ROI multi-années : Fiche Technique

> **Statut :** ✅ Complet (modèle statistique Monte-Carlo) · **Devise :** USD · **Horizon :** 5 ans

---

## 1. D'une projection ponctuelle à un modèle d'incertitude

La croissance future des données n'est pas connue : la projeter par un **chiffre unique** donne une fausse précision. E3 modélise donc l'incertitude par **simulation de Monte-Carlo** (`build_cost_analysis.py`, `numpy`).

- **`N_SIMULATIONS = 2000`** scénarios, **graine fixe `SEED = 42`** → résultat **déterministe et reproductible**.
- Chaque simulation tire **un taux de croissance annuel** `g ~ Normal(μ, σ)`, borné à `g ≥ −0,9` (une base ne peut pas perdre plus de 90 %/an).
- On en déduit, **par année et par percentile**, l'économie nette cumulée et la **probabilité de rentabilité**.

### Modèle de coût (par simulation, année k)

```
# Sans archivage
Volume(k)        = total_gb × (1 + g)^k
Coût_cumulé_no   = Σ Volume(i) × cost_active

# Avec archivage  (les archives froides croissent 2× moins vite)
Volume_actif(k)  = non_archivable_gb × (1 + g)^k
Volume_froid(k)  = archivable_gb     × (1 + g/2)^k
Coût_cumulé_with = impl_cost + Σ [Volume_actif(i)·cost_active + Volume_froid(i)·cost_cold]

# ROI
Économie_nette(k) = Coût_cumulé_no(k) − Coût_cumulé_with(k)
```

Sur les 2000 valeurs d'`Économie_nette(k)` on calcule **P10 / P50 / P90** et `breakeven_probability = P(Économie_nette > 0)`.

---

## 2. Estimateur de croissance : observé vs hypothèse (`_estimate_growth`)

La moyenne `μ` n'est **pas codée en dur** : elle est estimée depuis l'historique réel (E2).

```
Si la série TOTAL des snapshots couvre ≥ 2 runs ET que le CAGR observé > 0 :
    μ = CAGR observé
    σ = écart-type des variations annuelles (≥ 3 runs) sinon σ paramétré
    source = "observed"
Sinon :
    μ = data_growth_rate_pct_per_year   (15 %)
    σ = data_growth_std_pct_per_year    (5 %)
    source = "assumption"
```

> **État actuel (run 6) :** l'historique TOTAL est **décroissant** (run 5 → run 6, cf. E2), donc CAGR ≤ 0 ⇒ `source = "assumption"`, `μ = 15 %`, `σ = 5 %`. Le modèle **refuse d'extrapoler une tendance non fiable** ; il bascule sur l'hypothèse et le déclare explicitement (`growth_source`). Dès que l'historique deviendra positif et stable, il passera automatiquement en `"observed"`.

---

## 3. Objets créés

| Objet | Type | Rôle |
|---|---|---|
| `serving.roi_projection` | Table | 1 ligne / année : volumes, coûts cumulés, P10/P50/P90, breakeven_probability, μ, σ, source, n_simulations |
| `serving.v_roi_projection_summary` | Vue | Dernière projection (filtre `MAX(computed_at)`) |

Colonnes clés exposées : `cumul_cost_no_action_usd`, `cumul_cost_with_archiving_usd`, `net_savings_p10_usd`, `net_savings_p50_usd`, `net_savings_p90_usd`, `breakeven_probability`, `growth_mean_pct`, `growth_std_pct`, `growth_source`, `n_simulations`.

> **Note :** tous les enregistrements d'un calcul partagent un `computed_at` unique (fixé en Python) pour que la vue isole proprement le dernier batch.

---

## 4. Résultats réels — run 6 (croissance = hypothèse 15 % ± 5 %, 2000 sim.)

| Année | Coût cumulé sans action ($) | Coût cumulé avec archivage ($) | Économie nette P50 ($) | Intervalle P10–P90 | P(rentable) |
|---|---|---|---|---|---|
| N+0 | 2,16 | 0,66 | 1,51 | 1,51 – 1,51 | 1,00 |
| N+1 | 4,65 | 1,39 | 3,26 | 3,15 – 3,36 | 1,00 |
| N+2 | 7,50 | 2,20 | 5,30 | 4,94 – 5,65 | 1,00 |
| N+3 | 10,78 | 3,11 | 7,67 | 6,88 – 8,46 | 1,00 |
| N+4 | 14,55 | 4,13 | 10,42 | 9,00 – 11,91 | 1,00 |
| N+5 | 18,88 | 5,26 | **13,62** | **11,31 – 16,14** | **1,00** |

L'intervalle **P10–P90 s'élargit avec l'horizon** (l'incertitude sur la croissance se compose) — exactement ce qu'un chiffre unique cachait. La rentabilité reste **certaine** (`P = 1,00`) car le coût de mise en place est nul (tiering cloud).

---

## 5. Transposition production

À l'échelle production (`impl_cost > 0`), le breakeven n'est plus immédiat et `breakeven_probability` devient discriminant : on lit directement **la probabilité que le projet soit rentable à l'année k**, plutôt qu'un point unique. Exemple indicatif : 10 To archivables ⇒ ordre de grandeur 2 300 $/an d'économie ⇒ un projet à 5 000 $ devient rentable avec forte probabilité dès ~2 ans.

---

## 6. Commandes

```bash
python -m src.transform.build_cost_analysis --years 5

SELECT year_offset, cumul_cost_no_action_usd, cumul_cost_with_archiving_usd,
       net_savings_p10_usd, net_savings_p50_usd, net_savings_p90_usd,
       breakeven_probability, growth_source
FROM serving.v_roi_projection_summary ORDER BY year_offset;
```

Tests : `tests/test_cost_projection.py` (ordre des percentiles, reproductibilité, observé-vs-hypothèse).
Export Excel : feuille **ROI Projection**.
