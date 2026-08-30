# B — Classification ML par objet métier : Fiche Technique

> **Statut :** ✅ Complet  
> **Modèle actif :** `LLM/artifacts_business_domain/production_pipeline_latest.joblib` (**v3.4-human** — gold LLM + corrections d'apprentissage actif)
> **Fiche de référence du modèle :** [`artifacts/production_model_card.md`](../../artifacts/production_model_card.md)

---

## 1. Définition des domaines métier

*(Modèle déployé v3.4-human, run_id=6.)*

| Domaine (label ML) | Clé interne | Couverture run_id=6 |
|---|---|---|
| Finance & Contrôle | `finance` | 75 495 assets (45,1 %) |
| IT & Sécurité | `it` | 35 245 assets (21,1 %) |
| Supply Chain / Logistique / Production | `supply_chain` | 21 865 assets (13,1 %) |
| Achats & Fournisseurs | `procurement` | 14 455 assets (8,6 %) |
| Ventes & Clients | `sales` | 11 014 assets (6,6 %) |
| Other | `other` | 4 667 assets (2,8 %) |
| RH | `hr` | 4 519 assets (2,7 %) |
| **Total** | | **167 260 assets** |

---

## 2. Classification en 2 passes

### Passe 1 — Règles keyword (`src/ml/domain_term_base.py`)

**Principe :** matching regex `\b<terme>\b` (word boundary, case-insensitive) sur 4 champs :
- `technical_name` (nom technique de l'asset)
- `source_ref` (nom de la table Oracle physique)
- `column_names_text` (noms de colonnes séparés par `|`)
- `column_value_semantics_text` (patterns sémantiques des colonnes)

**Dictionnaire :** 8 clés de domaine, listes de termes :
- `finance` : ~100 termes (voucher, ledger, budget, gl, fiscal, accrual, payable, receivable...)
- `hr` : ~120 termes (emplid, employee, payroll, leave, benefit, position, jobcode...)
- `procurement` : ~80 termes (vendor, purchase, po, receipt, contract, supplier...)
- `supply_chain` : ~70 termes (inventory, demand, item, warehouse, ship, stock...)
- `it` : ~60 termes (oprid, role, permission, process, definition, class, security...)
- `sales` : ~50 termes (customer, order, invoice, billing, price, quote...)
- `risk` : redirigeé → `Finance`

**Seuil de classification :**
- Minimum **2 hits** dans un domaine
- Ratio de dominance **≥ 3.0×** (le domaine gagnant a 3× plus de hits que le 2ème)
- → `confidence` **graduée 0,70–0,90** (base 0,70 + bonus d'occurrences + bonus de
  dominance, bornée à 0,90), `model_version = "keyword_<domain>"`

**Couverture :** 44 568 assets classifiés en passe 1 (26,6 %)

### Passe 2 — Modèle ML (`src/transform/score_business_domain.py`)

Les 122 695 assets non classifiés par les règles keyword sont envoyés au modèle ML.

**Pipeline sklearn :**
```
ProductionPreprocessor → LinearSVC (Platt calibration)
```

---

## 3. `ProductionPreprocessor` — Ingénierie des features

### 3.1 Features textuelles (TF-IDF)

| Vectoriseur | Champ source | Paramètres |
|---|---|---|
| TF-IDF char_wb (n-grammes de caractères) | `technical_name` + `source_ref` | n=(3,5), max_features=50 000 |
| TF-IDF word (n-grammes de mots) | `column_names_text` | n=(1,2), max_features=80 000 |

### 3.2 Features numériques (12 colonnes, StandardScaler)

| Feature | Description |
|---|---|
| `field_count` | Nombre total de colonnes |
| `nullable_field_count` | Colonnes nullable |
| `non_nullable_field_count` | Colonnes NOT NULL |
| `numeric_field_count` | Colonnes numériques |
| `date_field_count` | Colonnes date/timestamp |
| `text_field_count` | Colonnes texte court |
| `large_text_field_count` | Colonnes CLOB/TEXT |
| `avg_data_length` | Longueur moyenne des colonnes |
| `max_data_length` | Longueur maximale |
| `row_count` | Nombre de lignes Oracle |
| `size_bytes` | Taille en octets |
| `size_mb` | Taille en Mo |

### 3.3 Features catégorielles (OHE)

| Feature | Modalités |
|---|---|
| `source_system` | `oracle`, `peoplesoft` |
| `asset_type` | `oracle_table`, `ps_record` |
| `has_profile_data` | `True`, `False` |

### 3.4 Assemblage

```python
scipy.sparse.hstack([tfidf_char, tfidf_word, numeric_scaled, ohe_encoded])
```

---

## 4. Modèle : LinearSVC + calibration Platt

- **Estimateur :** `LinearSVC(C=1.0, max_iter=2000)`
- **Calibration :** `CalibratedClassifierCV(method='sigmoid')` → probabilités via Platt scaling
- **Classes :** 7 (Finance & Contrôle, IT & Sécurité, Other, Achats & Fournisseurs, Supply Chain / Logistique / Production, RH, Ventes & Clients)
- **Stratégie multi-classe :** OVR (One-vs-Rest)

### Résultats stored dans `serving.asset_business_domain_prediction`

| Colonne | Description |
|---|---|
| `business_domain_predicted` | Domaine prédit (label) |
| `business_domain_alt` | 2ème domaine le plus probable |
| `confidence` | Probabilité calibrée [0, 1] (passe 2) ou confiance graduée `0,70–0,90` (passe 1 keyword) |
| `confidence_band` | `high` (≥ 0.85), `medium` (≥ 0.60), `low` (< 0.60) — 3 bandes (`_confidence_band`) |
| `review_required` | `true` si bande `low`, **ou** prédiction `Other`, **ou** top-1/top-2 trop proches (marge ≤ 0.05) |
| `model_version` | Passe 2 : version de l'artefact (`<pipeline_version>_<timestamp>`, ex. `v3.0_20260421_110952`). Passe 1 : `keyword_rule/<version>` |

---

## 4 bis. Benchmark multi-modèles & choix du modèle

> Notebook : `LLM/benchmark_ml_dl_classification_domaine_metier.ipynb`  
> Méthodo : StratifiedKFold 5-fold, **pipeline de features identique à la production**, métrique principale **Macro-F1** (classes déséquilibrées).

### Résultats (CV 5-fold)

| Rang | Modèle | Macro-F1 | Accuracy | Temps CV | Famille |
|---|---|---|---|---|---|
| 1 | **LinearSVC + Platt** | **0,8691** ± 0,009 | 0,9070 | 327 s | Linéaire |
| 2 | LightGBM | 0,8671 ± 0,011 | 0,9085 | 1 020 s | Gradient Boosting |
| 3 | MLP (Deep Learning) | 0,8533 ± 0,012 | 0,8931 | 1 250 s | Réseau de neurones |
| 4 | XGBoost | 0,8452 ± 0,012 | 0,8862 | 3 471 s | Gradient Boosting |
| 5 | LogisticRegression | 0,8301 ± 0,007 | 0,8710 | 413 s | Linéaire |
| 6 | Random Forest | 0,8049 ± 0,009 | 0,8407 | 111 s | Ensemble |

### Test de significativité (LinearSVC + Platt vs autres)

| Modèle comparé | Δ Macro-F1 | p-value | Significatif (α=0.05) |
|---|---|---|---|
| LightGBM | +0,0020 | 0,785 | **Non** (équivalent) |
| MLP | +0,0158 | 0,077 | Non |
| XGBoost | +0,0239 | 0,015 | Oui |
| LogisticRegression | +0,0390 | 0,0002 | Oui |
| Random Forest | +0,0642 | <0,001 | Oui |

### Décision : LinearSVC + Platt (modèle de production)

**Tier 1 (à égalité statistique) :** LinearSVC + Platt et LightGBM dominent ; leur écart de Macro-F1 (0,002) n'est **pas significatif** (p = 0,785).

Le choix de **LinearSVC + Platt** comme modèle de production se justifie sur des critères opérationnels, à performance équivalente :

| Critère | LinearSVC + Platt | LightGBM |
|---|---|---|
| Macro-F1 | **0,8691** (meilleur) | 0,8671 |
| Vitesse d'inférence | **Millisecondes** | Plus lente (~3×) |
| Probabilités calibrées | ✅ (Platt scaling) | Moins fiables sans calibration |
| Interprétabilité | ✅ (coefficients linéaires) | Boîte noire |
| Coût d'entraînement | 327 s | 1 020 s |

→ Idéal pour scorer 167 263 assets avec des `confidence` exploitables.

**Plan B :** **LightGBM** — alternative équivalente, à privilégier si l'accuracy brute ou la performance sur classes rares devient prioritaire.

**Deep Learning (MLP)** : écart vs champion non significatif (p = 0,077) mais sans avantage sur features sparse TF-IDF → non retenu. Piste BERT/embeddings reportée à une v2.

---

## 5. Entraînement du modèle

### 5.1 Création du jeu d'entraînement par annotation LLM (distillation)

Plutôt qu'une annotation manuelle de milliers de tables, le projet utilise un **LLM open-source comme annotateur automatique** (*LLM-as-labeler* → distillation de connaissances vers un modèle léger).

**Pipeline — `LLM/annotate_assets_llm.py` :**

| Élément | Détail |
|---|---|
| Échantillon | **20 000 lignes** tirées de `processed.dataset_asset_ml` (run_id=5) |
| Modèle annotateur | **`qwen2.5-32b-instruct`** (open-source) |
| Serveur | **Ollama** en local, API compatible OpenAI (`http://localhost:11434/v1`) |
| Appel | `chat/completions`, **température = 0** (déterministe), `response_format = json_object` |
| Entrée (par ligne) | `technical_name`, `source_ref`, noms/types/sémantiques/échantillons de colonnes |
| Sortie (JSON structuré) | `{ business_domain, confidence (0–1), reason }` |
| Garde-fou hybride | si le LLM répond `Other`, un repli par règles (`infer_domain_from_metadata` : patterns regex de domaine + préfixes de modules PeopleSoft GL/AP/HR/PO…) tente de récupérer un domaine |
| Robustesse | retries (`max_retries`), normalisation + clamp de la `confidence` |

**Mécanisme de consensus (qualité de l'annotation) :**

Chaque ligne reçoit un **`llm_consensus_score`** = degré d'accord entre **plusieurs votes du LLM** (colonnes `llm_votes_json`, `_n_votes`, `llm_models_used`). Deux seuils pilotent la stratification :
- `CONSENSUS_SOFT_FLOOR = 0.7` → en dessous : queue de revue humaine
- `CONSENSUS_HARD_FLOOR = 0.5` → coin-flip (consensus 0.5 avec exactement 2 votes) : rejeté

**Stratification réelle des 20 000 lignes (run_id=5) :**

| Tier | Critère | Lignes | % | Destination |
|---|---|---|---|---|
| 🟢 Gold | consensus ≥ 0.7 | **18 473** | 92,4 % | **Entraînement** |
| 🟡 Review | 0.5 < consensus < 0.7 | 2 | 0,0 % | Revue humaine (`review_queue_*.csv`) |
| 🔴 Reject | coin-flip (0.5, 2 votes) | 1 525 | 7,6 % | Écarté |

> Consensus moyen global = 0,96 ; 92,4 % des lignes ont un consensus ≥ 0,9. La revue humaine n'a concerné que 2 lignes sur ce run → la base est **quasi intégralement annotée par LLM à fort consensus**.

**Gold dataset = 18 473 lignes**, fichier `exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_business_domain_v4.csv`. Distribution (déséquilibre 24,9×) :

| Domaine | Lignes |
|---|---|
| Finance & Contrôle | 7 033 |
| IT & Sécurité | 4 913 |
| Other | 2 238 |
| Achats & Fournisseurs | 2 018 |
| Supply Chain / Logistique / Production | 1 235 |
| RH | 754 |
| Ventes & Clients | 282 |

Les 8 classes candidates du LLM (HR, Finance, Sales, Procurement, Supply Chain, IT, Risk, Marketing) sont remappées vers le référentiel de production (ex. Risk → Finance) via `LLM/annotate_base_d'entrainement/remap_to_6classes.py`.

**Intérêt de l'approche :**
1. Évite des semaines d'annotation manuelle sur des noms techniques cryptiques.
2. Le LLM 32B apporte une **compréhension sémantique** que des règles seules n'ont pas.
3. Le modèle final (LinearSVC, quelques Mo) est ~1000× plus léger que le LLM annotateur (32 Md de paramètres) → on **distille** la connaissance du gros modèle dans un classifieur déployable et rapide.

> Schéma : `qwen2.5-32b-instruct` (annotateur multi-votes, hors ligne) → filtrage consensus ≥ 0.7 → gold 18 473 lignes → entraînement `LinearSVC + Platt` (modèle servi en production).

### 5.2 Entraînement du modèle de production

> Notebook : `LLM/business_domain_production.ipynb`

1. **Source** : gold dataset (18 473 lignes, consensus ≥ 0.7).
2. **Poids d'échantillon** : le `llm_consensus_score` sert de `sample_weight` (les lignes les plus sûres pèsent plus).
3. **Split de validation** : 85 / 15 stratifié → **15 702** train / **2 771** holdout (pour CV + hold-out).
4. **Modèle final** : ré-entraîné sur **100 % du gold** (18 473 lignes) après validation → `production_pipeline_latest.joblib`.
5. **Déséquilibre** (24,9×) géré par `class_weight='balanced'`.

> ⚠️ Le notebook reste la référence historique, mais l'entraînement de production est désormais **reproductible en CLI** (§5.2 bis) — c'est ce script qui a produit le modèle déployé **v3.4-human**.

### 5.2 bis — Trainer reproductible (`src/ml/train_production_classifier.py`)

Porte le notebook en script déterministe et **réutilise les mêmes feature-builders que le scoring** (`_build_numeric_values`, `_compose_text` de `score_business_domain.py`) → **parité train/inférence garantie par construction**. Sauvegarde un artefact compatible octet-pour-octet avec le loader de scoring.

```bash
# entraînement gold seul (équivalent notebook)
python -m src.ml.train_production_classifier --pipeline-version v3.x

# entraînement augmenté par corrections ciblées (apprentissage actif) + comparaison avant/après
python -m src.ml.train_production_classifier --pipeline-version v3.4-human \
    --human-csv artifacts/human_eval_sample.csv \
    --human-csv artifacts/human_eval_sample_2.csv \
    --human-csv artifacts/human_eval_sample_3_train.csv \
    --human-test-csv artifacts/human_eval_sample_3_test.csv \
    --human-weight 10
```

Options clés : `--human-csv` (corrections ciblées ajoutées au gold, répétable), `--human-weight` (poids ×N des lignes corrigées), `--human-test-csv` (test fixe exclu de l'entraînement → équitable pour tous les modèles comparés), `--promote-latest`. Par défaut l'artefact est **horodaté et NON promu** (`latest` intouché → déploiement explicite).

### 5.2 ter — Correctif train/inférence (features sur texte normalisé)

Décalage latent corrigé : les features dérivées du texte (forme, préfixes `ps_is_*`, comptes de mots-clés) doivent être calculées sur le **texte normalisé** (comme à l'entraînement), pas brut. En brut, l'underscore de `PS_GL_ACCOUNT` casse la détection `\bgl\b` → les features mots-clés (les plus discriminantes) étaient inertes à l'inférence. Corrigé dans `_build_numeric_values` ; vérifié par comparaison feature-à-feature notebook vs inférence (**0 écart sur 129 features**). Le `model_version` écrit en base est désormais traçable (`v3.4-human_<timestamp>`).

### 5.2 quater — Validation d'échantillon + apprentissage actif (→ modèle déployé)

Les labels sont produits par le **LLM local** (`qwen2.5-32b`, consensus ≥ 0,7). Un **expert métier a validé un échantillon** de ces labels et **confirmé leur bonne qualité**. Pour progresser sur les cas difficiles, une boucle d'**apprentissage actif** cible la **zone de désaccord** entre versions du modèle et réinjecte les corrections en entraînement.

- `src/ml/build_human_eval_sample.py` — échantillon stratifié (sur-échantillonne classes rares + faible confiance ; option `--disagreement-vs <modèle>` pour cibler la **zone de désaccord**).
- `src/ml/evaluate_human_gold.py` — comparaison des labels (accord, par bande de confiance).

Chaque vague de corrections ciblée (~500 lignes) sur la zone de désaccord **améliore mesurablement** le modèle sur les cas les plus difficiles ; le modèle déployé (**v3.4-human**) intègre ces corrections avec un `sample_weight` élevé (10).

### 5.3 Modèle baseline (piste secondaire, scripts `src/ml/`)

Une version initiale, plus petite, **distincte de la production** :

```bash
python -m src.ml.prepare_labeled_dataset            # sample_1200_labeled.csv -> labeled_dataset_clean.csv
python -m src.ml.train_business_domain_classifier   # -> artifacts/business_domain_model.joblib
```

**Fichiers produits :**
- `artifacts/labeled_dataset_clean.csv` — ~1 200 lignes labélisées (baseline)
- `artifacts/business_domain_model.joblib` — modèle baseline
- `LLM/artifacts_business_domain/production_pipeline_latest.joblib` — **modèle de PRODUCTION** (gold 18 473, notebook)

### Métriques

```bash
# Analyser les erreurs par classe
python -m src.ml.analyze_business_domain_errors

# Construire la file de re-labélisation prioritaire
python -m src.ml.build_relabeling_priority_set
```

Métriques baseline stockées dans `artifacts/business_domain_metrics.json`.

> ⚠️ `analyze_business_domain_errors` et `build_relabeling_priority_set` ainsi que `business_domain_metrics.json` portent sur le **baseline** (taxonomie `Technique/Finance/RH/Achats`, macro-F1 ~0,55) — **pas** sur le modèle de production. Les métriques du modèle déployé sont dans [`artifacts/production_model_card.md`](../../artifacts/production_model_card.md). De même, `artifacts/benchmark_champion_report.json` titre LightGBM (candidat de benchmark, **non déployé**).

---

## 6. Reclassification et audit

```bash
# Reclassification par règles keyword uniquement (audit)
python -m src.ml.reclassify_by_terms --run-id 5

# Sorties :
# exports/reclassified/run5_all.csv           (167 263 lignes)
# exports/reclassified/run5_focus_domains.csv (domaines ciblés)
# exports/reclassified/run5_unclassified.csv  (non classifiés)
```

---

## 7. Scoring opérationnel

```bash
# Scorer le run_id=5 avec le modèle PROD
python -m src.transform.score_business_domain \
    --run-id 5 \
    --model-path LLM/artifacts_business_domain/production_pipeline_latest.joblib
```

**Durée estimée :** ~5 min pour 167 263 assets sur CPU standard.

---

## 8. Drift monitoring

Le fichier `LLM/artifacts_business_domain/drift_report.json` trace l'évolution de la distribution des prédictions entre runs, permettant de détecter si le comportement du modèle change avec les nouvelles données.

---

## 9. XLM-RoBERTa v3 — Classifieur deep learning (bundle ONNX)

> Entraîné sur un serveur 4× RTX 3090 (bf16, HuggingFace Accelerate). Disponible en inférence sans PyTorch via ONNX Runtime.

### 9.1 Architecture

```
XLM-RoBERTa-large (355 M params)
   [CLS] → 1024-d

Feature gating (129 features numériques → 1024-d gate via sigmoid)
   cls_gated = [CLS] × (1 + sigmoid(num_gate(num)))

Tête hybride
   Linear(1152, 512) → GELU → Dropout(0.2) → Linear(512, 7)
   ─── 1152 = 1024 (text_gated) + 128 (num_proj(num))
```

### 9.2 Innovations vs LinearSVC

| Technique | Détail |
|---|---|
| **Feature gating** | Les features numériques modulent le CLS embedding — le contexte volumétrique ajuste la représentation sémantique |
| **Focal Loss (γ=2,0)** | Pénalise les prédictions confiantes erronées — améliore les classes rares (RH, Ventes) |
| **Per-class temperature scaling** | 7 températures indépendantes optimisées sur NLL — ECE passe de 0,052 (v1) à **0,011** |
| **Decision offsets SLA** | `label = argmax(logits + offsets)` — post-processing sans réentraînement pour enforcer rappel ≥ 0,90 |

### 9.3 Format d'entrée (`build_input_text` v3)

```
[TABLE] {technical_name} [MODULE] {source_ref} [COLS] {column_names[:400]}
[SEM] {column_semantics[:200]} [TYPES] {column_type_signature_text[:200]}
```

### 9.4 Paramètres d'entraînement

| Paramètre | Valeur |
|---|---|
| Modèle de base | `xlm-roberta-large` (355 M paramètres) |
| Précision | `bf16` (4× RTX 3090) |
| Epochs | 50 (early stopping orienté rappel réglementé) |
| Batch size | 32 par GPU (128 total) |
| Optimiseur | AdamW (lr 2e-5, weight decay 0,01) |
| Scheduler | Cosine warmup (10 % steps) |
| Max sequence length | 256 tokens |
| Export ONNX | opset 17 (températures baked-in dans `probs`) |

### 9.5 Métriques (holdout LLM)

| Mode | Macro-F1 | ECE | Finance rappel | RH rappel | Achats rappel | Ventes rappel |
|---|---|---|---|---|---|---|
| Équilibré (`apply_offsets=False`) | ~0,82 | 0,011 | 0,84 | ≥ 0,90 | ≥ 0,90 | ≥ 0,90 |
| SLA-strict (`apply_offsets=True`) | ~0,79 | 0,011 | 0,89 | ≥ 0,90 | ≥ 0,90 | ≥ 0,90 |

> Finance reste la classe la plus difficile (rappel 0,84 en mode équilibré). Seules des annotations humaines supplémentaires permettront de franchir le seuil SLA 0,90.

### 9.6 Règle de décision

```python
logits, probs = session.run(["logits", "probs"], inputs)
# probs = softmax(logits / T_k)  ← températures per-classe baked-in ONNX
label = argmax(logits + offsets)   # offsets = 0 en mode équilibré
confidence = probs[label]          # probabilité calibrée per-classe
review_required = label in REGULATED and confidence < 0.60
```

### 9.7 Utilisation

```bash
# Inférence standalone (hors base de données, hors pipeline)
cd artifacts/xlmr_v3
pip install -r requirements-inference.txt
python predict.py

# Via le dashboard Streamlit (section "🤖 Test du modèle")
streamlit run app/streamlit_dashboard.py
```

### 9.8 Artefacts

| Fichier | Rôle |
|---|---|
| `artifacts/xlmr_v3/artifacts/model.onnx` | Graphe ONNX (poids exclus — `model.onnx.data` gitignored) |
| `artifacts/xlmr_v3/artifacts/temperatures.json` | 7 températures per-classe |
| `artifacts/xlmr_v3/artifacts/decision_offsets.json` | Offsets logit pour SLA (Finance +2,26 ; RH +4,42 ; Ventes +5,42) |
| `artifacts/xlmr_v3/artifacts/scaler_params.npz` | StandardScaler (129 features) |
| `artifacts/calibration_report.json` | ECE avant/après calibration (LinearSVC v3.4 vs XLM-R v1 vs XLM-R v3) |
| `src/ml/model_reliability.py` | `ModelReliabilityMonitor` — calibration, SLA rappel, drift (Phase 1) |
