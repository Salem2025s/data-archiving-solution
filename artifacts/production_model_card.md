# Fiche modèle — Classification par domaine métier (PRODUCTION)

> **Source de vérité unique** sur le modèle réellement déployé.
> Métadonnées de `LLM/artifacts_business_domain/production_pipeline_latest.joblib`,
> scoring run_id=6. Dernière mise à jour : 2026-06-01.

## Modèle déployé

| Élément | Valeur |
|---|---|
| Algorithme | **LinearSVC + calibration Platt** (`CalibratedClassifierCV(estimator=LinearSVC)`) |
| Version | **v3.4-human** — `timestamp=20260601_104226` |
| `model_version` écrit en base | `v3.4-human_20260601_104226` (ML) · `keyword_rule/v3.4-human_20260601_104226` (passe keyword) |
| Classes | **7** : Achats & Fournisseurs, Finance & Contrôle, IT & Sécurité, Other, RH, Supply Chain / Logistique / Production, Ventes & Clients |
| Jeu d'entraînement | **gold LLM 18 473** (consensus ≥ 0.7) **+ 1 130 lignes annotées humainement** (`sample_weight=10`), `class_weight=balanced` |
| Entraîné par | `src.ml.train_production_classifier` (reproductible, parité train/inférence garantie) |
| Repli | `production_pipeline_v3.3-human_*` (783 humains) et `production_pipeline_v3.0_*` (LLM seul), conservés |

## Performance — justesse validée HUMAINEMENT (la métrique qui compte)

Apprentissage actif : 3 vagues d'annotation ciblée (1 290 lignes au total), chaque vague sur la zone de désaccord du modèle précédent. Mesuré sur test tenu à l'écart (jamais entraîné).

| Modèle | Données humaines | Accuracy (test humain) |
|---|---|---|
| v3.0 | 0 (LLM seul) | ~0,51 |
| v3.3-human | 783 | ~0,61 / 0,74† |
| **v3.4-human (déployé)** | **1 130** | **0,747** (test contesté lot 3) |

† v3.3 = 0,74 sur son propre test (lots 1+2) mais 0,61 sur la zone de désaccord plus dure (lot 3).
Sur le test équitable lot 3 (150 lignes, jamais vues par v3.0/v3.3/v3.4) : **v3.4 = 0,747 vs v3.3 = 0,613 (+13,4 pts)**, macro-F1 0,655, κ 0,70.

> Le **holdout LLM** reste ~0,89 mais ne mesure que l'accord avec l'annotateur LLM — **ne pas l'utiliser** comme métrique de qualité. Voir `src/ml/evaluate_human_gold.py`, `artifacts/human_eval_report*.json`.

## Inférence (2 passes)
- **Passe 1 — règles keyword** (`domain_term_base.py`) : ~26,6 % des assets, confidence fixe 0,95.
- **Passe 2 — modèle ML** (LinearSVC+Platt) : ~73,4 %, probabilités calibrées.
- Garde-fous calibrés : `confidence_band` (high ≥ 0,85 / medium ≥ 0,60 / low) et `review_required` corrèlent avec la justesse → triage auto (high) vs revue humaine (low/review).

## Mises en garde
1. `artifacts/benchmark_champion_report.json` ne décrit PAS ce modèle (titre LightGBM, candidat de benchmark non déployé ; égalité statistique p=0,785).
2. `artifacts/business_domain_metrics.json` est obsolète (baseline 3-4 classes, macro-F1 ~0,55).
3. Le test humain est volontairement stratifié sur les cas durs (désaccord, classes rares) → l'accuracy population réelle est probablement **supérieure** à ces chiffres.
