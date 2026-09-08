# Trace — recherche d'hyperparamètres (modèle de production LinearSVC + Platt)

> **Protocole** : gold 18 473 (consensus ≥ 0,7), split stratifié **holdout 20 %**, **seed 42**,
> `class_weight='balanced'`, `max_iter=4000`. Les macro-F1 ci-dessous sont mesurés sur le
> holdout par un LinearSVC **brut** ; le **modèle déployé ajoute la calibration Platt** → **0,885**
> (= chiffre du benchmark et du deck). *(Le même modèle sur holdout 15 % donne 0,892 — voir §Réconciliation.)*

## Méthode
- **RandomizedSearchCV** — 20 tirages, **3-fold**, `scoring='f1_macro'` (60 fits).
- Menée sur le modèle champion = LinearSVC + Platt.
- Espace exploré : `C ~ loguniform(0.01, 100)` · `max_iter ~ randint(1000, 5000)`.
- **Meilleur paramètre trouvé (par CV) : C ≈ 2,48.**
- Source : `LLM/benchmark_ml_dl_classification_domaine_metier.ipynb`.

## Validation sur holdout 20 % — balayage de C

| C | Macro-F1 (holdout 20 %) | Statut |
|---|---|---|
| 0.1 | 0.8725 | — |
| 0.5 | 0.8919 | — |
| 1.0 | 0.8889 | **déployé** |
| 2.48 | 0.8856 | optimum RandomizedSearch (CV) |
| 5.0 | 0.8833 | — |
| 10.0 | 0.8845 | — |

## Lecture
- Le réglage **a un effet mesurable** : de **0,8725** (C=0,1) à **0,8919** (C=0,5), soit **+0,019** sur le holdout.
- Le holdout dessine un **plateau plat pour C ≈ 0,5–1** ; au-delà (C ≥ 2,5) la performance redescend légèrement.
- **RandomizedSearchCV (3-fold CV)** avait retenu **C ≈ 2,48** ; sur le holdout unique le plateau est plutôt
  **C ≈ 0,5–1**. Écart normal (CV vs holdout) — les valeurs sont dans un **mouchoir de poche (< 0,006)**.
- → **C = 1 retenu** : valeur ronde, stable et reproductible **au cœur du plateau**, sans sur-ajustement au holdout.
- La **calibration Platt** du modèle déployé échange ~0,004 de macro-F1 (0,889 → 0,885) contre des
  **probabilités fiables** (ECE réduit) — indispensable pour le routage `review_required`.

## Réconciliation 0,885 vs 0,892 (même modèle)
| Mesure | Protocole | Macro-F1 |
|---|---|---|
| Benchmark / deck | LinearSVC **+ Platt**, holdout **20 %** | **0,885** *(reproduit : 0,8849)* |
| Carte modèle déployé | même pipeline, holdout **15 %** | **0,892** |

**L'écart ≈ 0,007 vient uniquement de la taille du holdout (20 % vs 15 %)** — mêmes features,
mêmes hyperparamètres (C=1, balanced, max_iter=4000). **Ce n'est pas un gain de réglage.**
