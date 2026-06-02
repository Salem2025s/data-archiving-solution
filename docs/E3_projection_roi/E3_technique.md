# E3 — Projection ROI multi-années : Fiche Technique

> **Statut :** ✅ Complet · **Devise :** USD · **Horizon :** 5 ans

---

## 1. Modèle

Deux scénarios projetés sur N années (défaut 5), calculés en Python dans `build_cost_analysis.py` :

### Scénario sans archivage
```
Volume(k)      = total_gb × (1 + g)^k
Coût(k)        = Volume(k) × cost_active
Coût_cumulé(k) = Σ Coût(i)
```

### Scénario avec archivage
```
Volume_actif(k)  = non_archivable_gb × (1 + g)^k
Volume_froid(k)  = archivable_gb × (1 + g/2)^k   (archives : croissance 2× plus lente)
Coût(k)          = Volume_actif(k) × cost_active + Volume_froid(k) × cost_cold
Coût_cumulé(k)   = impl_cost + Σ Coût(i)
```

### ROI
```
Économie_nette(k) = Coût_cumulé_sans(k) − Coût_cumulé_avec(k)
breakeven         = (Économie_nette > 0)
roi_pct           = Économie_nette / impl_cost × 100   (NULL si impl_cost = 0)
```

`g = 15 %`, `impl_cost = 0` (tiering cloud).

---

## 2. Objets créés

| Objet | Type | Rôle |
|---|---|---|
| `serving.roi_projection` | Table | 1 ligne par année (peuplée par Python) |
| `serving.v_roi_projection_summary` | Vue | Dernière projection calculée |

> **Note technique :** tous les enregistrements d'un même calcul partagent un `computed_at` unique (fixé en Python), pour que la vue summary filtre correctement le dernier batch via `MAX(computed_at)`.

---

## 3. Résultats run_id=5

| Année | Coût sans action ($/an) | Coût avec archivage ($/an) | Économie cumulée ($) | Rentable |
|---|---|---|---|---|
| N+0 | 2,16 | 0,41 | 1,75 | ✅ |
| N+1 | 2,49 | 0,45 | 3,79 | ✅ |
| N+2 | 2,86 | 0,49 | 6,16 | ✅ |
| N+3 | 3,29 | 0,53 | 8,92 | ✅ |
| N+4 | 3,78 | 0,57 | 12,13 | ✅ |
| N+5 | 4,35 | 0,62 | **15,86** | ✅ |

**Breakeven immédiat** (impl_cost = 0 → le tiering cloud est rentable dès l'année 0).

> Le coût "sans action" passe de 2,16 à 4,35 $/an en 5 ans (×2,01 — l'effet de la croissance 15 %/an composée). Avec archivage, il reste sous 0,62 $/an.

---

## 4. Transposition production

Le modèle est volume-indépendant. À l'échelle production (impl_cost > 0), le breakeven devient :
```
breakeven_year ≈ impl_cost / (économie_annuelle)
```
Exemple : 10 To archivables → 2 335 $/an d'économie → un projet à 5 000 $ s'amortit en ~2,1 ans.

---

## 5. Commandes

```bash
python -m src.transform.build_cost_analysis --years 5

SELECT year_offset, cost_no_action_usd, cost_with_archiving_usd, net_savings_usd, breakeven
FROM serving.v_roi_projection_summary;
```

Export Excel : feuille **ROI Projection**.
