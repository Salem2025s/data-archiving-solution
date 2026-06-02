# E2 — Comparaison N-1 : Fiche Technique

> **Statut :** ✅ Complet (par simulation) · **Devise :** USD

---

## 1. Contrainte et approche

Un seul snapshot Oracle existe (run_id=5). La comparaison N-1 est construite par **simulation** : on applique le taux de croissance (15 %) à l'envers pour reconstruire le patrimoine d'il y a 1 an.

```
size_gb_n1 = size_gb_n / (1 + growth/100)
cost_n1    = cost_n   / (1 + growth/100)
```

---

## 2. Objet créé

`serving.v_n1_comparison` — vue SQL sur `mv_cost_analysis` + paramètre de croissance.

| Colonne | Description |
|---|---|
| `domain_label` | Domaine |
| `size_gb_n1` | Volume simulé il y a 1 an |
| `size_gb_n` | Volume actuel |
| `growth_gb` | Croissance (Go) |
| `cost_n1_usd` | Coût N-1 ($/an) |
| `cost_n_usd` | Coût actuel ($/an) |
| `cost_increase_usd` | Surcoût annuel dû à la croissance |
| `growth_rate_pct` | Taux appliqué |

---

## 3. Résultats run_id=5 (global)

| Indicateur | Valeur |
|---|---|
| Patrimoine N-1 (simulé) | 6,813 Go |
| Patrimoine N (actuel) | 7,835 Go |
| Croissance sur 1 an | +1,022 Go (+15 %) |
| Surcoût annuel | +0,28 $/an |

---

## 4. Évolution vers une comparaison réelle

Le pipeline conserve tous les `run_id`. Dès qu'un second run existera, la comparaison réelle remplacera la simulation :

```sql
SELECT f.run_id, ROUND(SUM(f.size_mb)/1024.0, 3) AS total_gb
FROM processed.features_asset f
WHERE f.run_id IN (5, 6)
GROUP BY f.run_id;
```

---

## 5. Requête utile

```sql
SELECT SUM(size_gb_n1) AS n1_gb, SUM(size_gb_n) AS n_gb,
       SUM(cost_increase_usd) AS surcout_annuel
FROM serving.v_n1_comparison;
```

Export Excel : feuille **N-1 Comparison**.
