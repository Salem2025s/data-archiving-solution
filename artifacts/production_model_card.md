# Fiche modèle — Classification par domaine métier (PRODUCTION)

> **Source de vérité unique** sur le modèle réellement déployé.
> Générée à partir des métadonnées de `LLM/artifacts_business_domain/production_pipeline_latest.joblib`
> et du scoring run_id=6. Dernière mise à jour : 2026-05-31.

## Modèle déployé

| Élément | Valeur |
|---|---|
| Algorithme | **LinearSVC + calibration Platt** (`CalibratedClassifierCV(estimator=LinearSVC)`) |
| Version | **v3.0** — `timestamp=20260421_110952` — `data_hash=14df313f3030` |
| `model_version` écrit en base | `v3.0_20260421_110952` (ML) · `keyword_rule/v3.0_20260421_110952` (passe keyword) |
| Classes | **7** : Achats & Fournisseurs, Finance & Contrôle, IT & Sécurité, Other, RH, Supply Chain / Logistique / Production, Ventes & Clients |
| Jeu d'entraînement | **gold = 18 473 lignes** (consensus LLM ≥ 0.7), `sample_weight = consensus`, `class_weight = balanced` |

## Performance réelle du modèle déployé (holdout interne)

| Métrique | Valeur |
|---|---|
| **Macro-F1 (holdout)** | **0,892** |
| **Weighted-F1 (holdout)** | **0,923** |

> Ces chiffres proviennent de l'artefact déployé (`holdout_macro_f1`, `holdout_weighted_f1`).

## Inférence (2 passes) — couverture run_id=6 (167 260 assets)

| Passe | Méthode | Assets | % |
|---|---|---|---|
| 1 | Règles keyword (`domain_term_base.py`) | 44 568 | 26,6 % |
| 2 | Modèle ML (LinearSVC + Platt) | 122 692 | 73,4 % |

Répartition prédite : Finance 74 398 · IT 39 933 · Other 18 522 · Achats 13 198 · Supply Chain 12 453 · Ventes 5 171 · RH 3 585.

---

## Modèle deep learning — XLM-RoBERTa v3 (ONNX, inférence standalone)

> Entraîné sur 4× RTX 3090 (bf16, HuggingFace Accelerate). Disponible dans `artifacts/xlmr_v3/`.

| Élément | Valeur |
|---|---|
| Architecture | XLM-RoBERTa-large (355 M params) + tête hybride (feature gating, Focal Loss γ=2,0) |
| Calibration | Per-class temperature scaling — ECE 0,052 (v1) → **0,011** |
| Decision offsets | Per-classe SLA : Finance +2,26, RH +4,42, Achats +1,36, Ventes +5,42 |
| Export | ONNX opset 17 (températures baked-in dans `probs`) |
| Inférence | `DomainClassifier(apply_offsets=False|True).predict(row_dict)` |

**Métriques (mode équilibré) :** Macro-F1 ~0,82, ECE 0,011, Finance rappel 0,84 (sous SLA), RH/Achats/Ventes ≥ 0,90.

**Interface de test :** section « 🤖 Test du modèle » du dashboard Streamlit.

---

## ⚠️ Mises en garde importantes

1. **`artifacts/benchmark_champion_report.json` ne décrit PAS ce modèle.** Ce rapport titre **LightGBM** (meilleur candidat par macro-F1 holdout du benchmark, ~0,885). LightGBM et LinearSVC+Platt sont à **égalité statistique** (Δ macro-F1 = 0,002 ; p = 0,785) ; LinearSVC+Platt a été retenu pour la **vitesse d'inférence, la calibration des probabilités et l'interprétabilité**. **Ne pas citer le `champion_report` comme métrique de production.**
2. **`artifacts/business_domain_metrics.json` est obsolète** : il documente un modèle *baseline* (3-4 classes, macro-F1 ~0,55), sans rapport avec la production.
3. **Labels = consensus LLM** (`qwen2.5-32b-instruct`, 2 variantes de prompt), **pas de gold validé humain**. L'annotateur étant guidé par des heuristiques (préfixes PS, mots-clés) qui recoupent les features du classifieur, les métriques peuvent être **optimistes** (risque de circularité). Une évaluation sur échantillon annoté humainement reste à faire.
