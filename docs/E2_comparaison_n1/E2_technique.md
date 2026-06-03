# E2 — Comparaison N-1 : Fiche Technique

> **Statut :** ✅ Complet (réel, snapshots historiques) · **Devise :** USD

---

## 1. Approche : un historique factuel, plus de simulation

Le pipeline conserve **tous les `run_id`**. À chaque exécution de l'analyse coût, on fige un **snapshot** du coût et du volume par domaine (+ ligne `TOTAL`) dans une table dédiée. La comparaison N vs N-1 lit alors les **deux runs les plus récents réellement observés** — il n'y a plus aucune reconstruction mathématique du passé.

```
N   = run le plus récent ayant un snapshot   (rn = 1)
N-1 = run précédent                          (rn = 2)
```

Au premier lancement, `backfill_cost_snapshots()` rattrape les runs historiques déjà chargés (ceux qui ont des `features_asset`) pour amorcer l'historique immédiatement.

---

## 2. Objets créés

### `serving.fact_cost_snapshot` (table)

| Colonne | Description |
|---|---|
| `run_id` | Run figé |
| `domain_label` | Domaine (ou `TOTAL`) |
| `total_size_gb` | Volume du domaine à ce run |
| `current_cost_usd_year` | Coût annuel = volume × tarif actif |
| `captured_at` | Horodatage de la capture |

Écriture **idempotente** : `DELETE` + `INSERT` par `run_id` (re-jouable sans doublon).

### `serving.v_n1_comparison` (vue)

```sql
WITH ranked AS (
    SELECT s.*, ROW_NUMBER() OVER (PARTITION BY domain_label ORDER BY run_id DESC) AS rn
    FROM serving.fact_cost_snapshot s
),
cur  AS (SELECT * FROM ranked WHERE rn = 1),
prev AS (SELECT * FROM ranked WHERE rn = 2)
SELECT cur.domain_label, cur.run_id AS run_n, prev.run_id AS run_n1,
       cur.total_size_gb AS size_gb_n, prev.total_size_gb AS size_gb_n1,
       (cur.total_size_gb - prev.total_size_gb)              AS growth_gb,
       cur.current_cost_usd_year AS cost_n_usd, prev.current_cost_usd_year AS cost_n1_usd,
       (cur.current_cost_usd_year - prev.current_cost_usd_year) AS cost_increase_usd,
       100.0 * (cur.total_size_gb - prev.total_size_gb)
             / NULLIF(prev.total_size_gb, 0)                 AS growth_rate_pct
FROM cur LEFT JOIN prev USING (domain_label);
```

`LEFT JOIN` : un domaine apparu seulement à N (sans N-1) reste visible avec des champs N-1 à `NULL`.

---

## 3. Résultats réels — run 6 (N) vs run 5 (N-1)

| Domaine | Volume N-1 | Volume N | Croissance | Taux |
|---|---|---|---|---|
| **TOTAL** | **11,76 Go** | **7,84 Go** | **−3,93 Go** | **−33,4 %** |
| IT & Sécurité | 6,07 | 6,69 | +0,62 | +10,1 % |
| Finance & Contrôle | 0,52 | 0,55 | +0,03 | +5,5 % |
| Other | 1,17 | 0,48 | −0,69 | −59,1 % |
| Supply Chain | 0,036 | 0,045 | +0,009 | +25,0 % |
| Achats | 0,023 | 0,035 | +0,012 | +51,5 % |
| RH | 0,009 | 0,022 | +0,013 | +142,2 % |
| Ventes & Clients | 0,002 | 0,019 | +0,017 | +743,4 % |

**Lecture honnête :** le patrimoine **TOTAL a diminué** entre les deux extractions (−33,4 %). Ce n'est pas une décroissance « naturelle » des données : les deux runs n'ont pas capté exactement le même périmètre (le run 5 incluait davantage d'objets volumineux non répétés au run 6). C'est précisément le genre de signal qu'un historique réel révèle — et qu'une simulation à 15 % aurait masqué.

> **Conséquence directe pour E3 :** un historique de 2 runs, non monotone et globalement négatif, **n'est pas un trend prédictif fiable**. L'estimateur de croissance de E3 le détecte (CAGR ≤ 0) et bascule sur l'hypothèse paramétrée plutôt que d'extrapoler une fausse tendance. La rigueur de E2 protège E3.

---

## 4. Requête utile

```sql
SELECT run_n, run_n1, size_gb_n, size_gb_n1, growth_gb, growth_rate_pct
FROM serving.v_n1_comparison
WHERE domain_label = 'TOTAL';
```

Export Excel : feuille **N-1 Comparison** (8 lignes : 7 domaines + TOTAL).
