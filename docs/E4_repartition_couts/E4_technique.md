# E4 — Répartition des coûts par objet métier : Fiche Technique

> **Statut :** ✅ Complet · **Devise :** USD

---

## 1. Objet créé

`serving.v_cost_by_domain` — vue SQL sur `mv_cost_analysis` avec parts relatives, Pareto et potentiel d'optimisation.

| Colonne | Description |
|---|---|
| `domain_label` | Domaine |
| `total_size_gb` | Volume (Go) |
| `current_cost_usd_year` | Coût annuel ($) |
| `annual_savings_usd` | Économie potentielle ($/an) |
| `savings_pct` | % d'économie du domaine |
| `volume_share_pct` | Part du volume total |
| `cost_share_pct` | Part du coût total |
| `savings_share_pct` | Part des économies totales |
| `cost_rank` | Rang par coût (1 = le plus cher) |
| `cumulative_cost_pct` | Coût cumulé (analyse de Pareto) |
| `optimization_potential` | Très élevé / Élevé / Modéré / Faible |

---

## 2. Résultats run_id=5

| Rang | Domaine | Coût $/an | % coût | % cumulé | Potentiel |
|---|---|---|---|---|---|
| 1 | IT & Sécurité | 1,68 | 77,8 % | 77,8 % | Très élevé |
| 2 | Other | 0,32 | 14,8 % | 92,6 % | Très élevé |
| 3 | Finance & Contrôle | 0,14 | 6,5 % | 99,1 % | Très élevé |
| 4 | Supply Chain | 0,01 | 0,5 % | 99,5 % | Très élevé |
| 5 | Achats & Fournisseurs | 0,01 | 0,5 % | 100 % | Très élevé |
| 6 | Ventes & Clients | 0,00 | 0 % | 100 % | Très élevé |
| 7 | RH | 0,00 | 0 % | 100 % | Très élevé |

### Lecture Pareto

**IT & Sécurité concentre 77,8 % du coût** à lui seul. **IT + Other = 92,6 %** → 2 domaines sur 7 représentent l'essentiel du coût. L'effort d'archivage doit se concentrer en priorité sur ces deux domaines.

> `optimization_potential = Très élevé` pour tous les domaines : c'est attendu car ~98 % du volume est archivable (données très anciennes). Le discriminant utile ici est le **rang de coût** (Pareto), pas le potentiel.

---

## 3. Requêtes

```sql
-- Répartition + Pareto
SELECT domain_label, current_cost_usd_year, cost_share_pct, cumulative_cost_pct, cost_rank
FROM serving.v_cost_by_domain ORDER BY cost_rank;

-- Domaines couvrant 80% du coût
SELECT domain_label, cumulative_cost_pct
FROM serving.v_cost_by_domain
WHERE cumulative_cost_pct <= 80;
```

Export Excel : feuille **Cost by Domain** (colonne `cumulative_cost_pct` pour la courbe de Pareto).

---

## 4. Tableau de bord visuel (Dashboard)

L'export `domain_model_run5.xlsx` contient une feuille **Dashboard** (en première position) avec 5 graphiques natifs Excel :

| Graphique | Type | Source |
|---|---|---|
| Répartition du coût par domaine | Camembert | `v_cost_by_domain.current_cost_usd_year` |
| Volume par stratégie d'archivage | Histogramme | `mv_archiving_recommendation` (agrégé) |
| Projection coût 5 ans (sans/avec archivage) | Courbes | `v_roi_projection_summary` |
| Nombre d'assets par domaine | Histogramme horizontal | `mv_domain_profile.asset_count` |
| Pareto des coûts par domaine | Barres + courbe % cumulé (axe secondaire) | `v_cost_by_domain` |

Les graphiques référencent dynamiquement les cellules des feuilles de données → ils se mettent à jour si on régénère l'export sur un nouveau run.
