# XLM-RoBERTa v1 — Bundle d'inférence (classification de domaine métier)

Classe un actif Oracle/PeopleSoft dans l'une des **7 classes** (ordre fixe) :

| idx | classe |
|-----|--------|
| 0 | Finance & Contrôle |
| 1 | RH |
| 2 | Achats & Fournisseurs |
| 3 | Ventes & Clients |
| 4 | Supply Chain / Logistique / Production |
| 5 | IT & Sécurité |
| 6 | Other |

Modèle : XLM-RoBERTa-large fine-tuné + tête hybride (texte + 129 features numériques),
exporté en **ONNX (opset 17)** avec **temperature scaling intégré** (la sortie `probs`
est déjà calibrée).

---

## 1. Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-inference.txt
```

Aucune dépendance à PyTorch. `transformers` n'est utilisé que pour le tokenizer.
Pour l'inférence GPU : remplacer `onnxruntime` par `onnxruntime-gpu` et passer
`providers=["CUDAExecutionProvider"]` à `DomainClassifier(...)`.

## 2. Utilisation

```python
from predict import DomainClassifier

clf = DomainClassifier()              # charge ./artifacts

asset = {
    "technical_name": "PS_VENDOR_ADDR",
    "source_ref": "AP",
    "column_names": "vendor_id address1 city",                    # ou column_names_text
    "column_semantics": "VENDOR_ID:reference_identifier|ADDRESS1:postal_location",
    # --- métriques de schéma (voir §4) ---
    "field_count": 12, "nullable_field_count": 4, "non_nullable_field_count": 8,
    "numeric_field_count": 3, "date_field_count": 1, "text_field_count": 8,
    "large_text_field_count": 0, "avg_data_length": 22.0, "max_data_length": 120.0,
    "row_count": 5000, "size_bytes": 1258291, "size_mb": 1.2,
}

out = clf.predict(asset)
# {'label': 'Achats & Fournisseurs', 'label_index': 2, 'confidence': 0.99,
#  'probs': {...}, 'review_required': False}

# batch :
outs = clf.predict([asset1, asset2, ...])
```

Test rapide : `python predict.py`

## 3. Contenu du bundle

```
xlmr_v1_bundle/
├── predict.py                  # API d'inférence (DomainClassifier)
├── features.py                 # construction texte + 129 features (vendoré, parité exacte)
├── requirements-inference.txt
├── README.md
└── artifacts/
    ├── model.onnx              # graphe ONNX (petit)
    ├── model.onnx.data         # ⚠️ POIDS (~2.2 Go) — DOIT rester à côté de model.onnx
    ├── tokenizer/              # tokenizer XLM-R (tokenizer.json, tokenizer_config.json)
    ├── scaler_params.npz       # mean_/scale_ du StandardScaler (129 features)
    ├── class_labels.json       # ordre des 7 classes
    └── temperature.json        # T (déjà appliqué dans le graphe ; informatif)
```

> ⚠️ **`model.onnx` et `model.onnx.data` sont indissociables** : onnxruntime charge
> les poids depuis `model.onnx.data` (référence relative, même dossier). Ne pas
> renommer ni séparer ces deux fichiers.

## 4. Entrées attendues

`predict()` accepte un dict (ou une liste de dicts) par actif. Champs **texte** :

- `technical_name` — nom technique de la table (ex. `PS_GL_ACCOUNT`)
- `source_ref` — module PeopleSoft (ex. `AP`, `HR`, `GL`)
- `column_names` **ou** `column_names_text` — noms de colonnes séparés par des espaces
- `column_semantics` **ou** `column_value_semantics_text` — `col:label|col:label|...`

Champs **numériques de schéma** (12 bruts ; le reste des 129 est dérivé automatiquement) :
`field_count, nullable_field_count, non_nullable_field_count, numeric_field_count,
date_field_count, text_field_count, large_text_field_count, avg_data_length,
max_data_length, row_count, size_bytes, size_mb`.

> Si `field_count` est absent/None, l'actif est traité **sans** features numériques
> (vecteur de zéros) — la prédiction repose alors sur le seul texte et sera dégradée.
> **En production, fournissez toujours les métriques de schéma.**

## 5. Sorties

- `label` / `label_index` — classe prédite (argmax)
- `confidence` — probabilité **calibrée** de la classe prédite
- `probs` — dict des 7 probabilités calibrées (somme ≈ 1)
- `review_required` — heuristique : domaine réglementé prédit avec confiance < 0.60

## 6. Performance (test set du projet, pour information)

- Accuracy 0.842 · Macro-F1 0.800 · ECE après calibration 0.047
- Rappel réglementé : Finance 0.88 · RH 0.81 · Achats 0.92 · Ventes 0.84
- (vs baseline LinearSVC : acc 0.75)

## 7. Notes d'intégration

- **Déterminisme** : `max_length = 256`, troncature à droite, padding à `max_length`.
- **Parité** : `features.py` reproduit à l'identique le préprocessing d'entraînement
  (vérifié au build contre le code source du projet).
- Le graphe ONNX expose aussi `logits` (avant softmax/T) si besoin de scores bruts.
- L'ordre des 7 classes est **contractuel** : ne pas le réordonner côté intégration.
