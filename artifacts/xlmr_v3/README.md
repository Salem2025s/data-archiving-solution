# XLM-RoBERTa v3 (50 époques) — Bundle d'inférence

Classifie un actif Oracle/PeopleSoft dans l'une des **7 classes** (ordre fixe) :
`Finance & Contrôle, RH, Achats & Fournisseurs, Ventes & Clients, Supply Chain / Logistique / Production, IT & Sécurité, Other` (indices 0→6).

Modèle = XLM-R-large + tête hybride, **v3** : feature gating, Focal Loss, **calibration par classe** (7 T), **feature type-signature**, entraîné **50 époques** (meilleur checkpoint = **époque 22**, sélection orientée rappel réglementé).

## ⚠️ Deux points cruciaux (sinon prédictions fausses)

1. **Feature type-signature** : fournir `column_type_signature_text` (signature des types de colonnes). Le modèle a été entraîné avec — `features.py` l'ajoute comme section `[TYPES]`. S'il manque, la section est omise (prédiction dégradée mais pas cassée).
2. **Règle de décision** : la calibration par classe change l'argmax →
   ```
   label      = argmax(logits + offsets)    # PAS argmax(probs)
   confidence = probs[label]                # proba calibrée
   ```
   `predict.py` applique ça automatiquement.

## Deux modes (paramètre `apply_offsets`)

| Mode | `apply_offsets` | Accuracy | Rappels réglementés | Usage |
|---|---|---|---|---|
| **Équilibré** (défaut) | `False` | **0.838** | Fin 0.84 · RH 0.90 · Ach 0.92 · Ven 0.90 | usage général |
| **SLA-strict** | `True` | 0.79 | Fin 0.89 · RH 0.94 · Ach 0.91 · Ven 0.95 | maximiser le rappel réglementé (au prix de la précision/accuracy) |

```python
from predict import DomainClassifier
clf = DomainClassifier()                       # équilibré (défaut)
clf = DomainClassifier(apply_offsets=True)     # mode SLA-strict
```

## Installation & usage

```bash
pip install -r requirements-inference.txt
python predict.py
```
```python
out = clf.predict({
    "technical_name": "PS_GL_ACCOUNT", "source_ref": "GL",
    "column_names": "account ledger amount currency_cd",
    "column_semantics": "ACCOUNT:reference_identifier|AMOUNT:financial_amount",
    "column_type_signature_text": "NBR:8|CHAR:6|DATE:2",     # v3 : à fournir
    "field_count": 18, "numeric_field_count": 8, "row_count": 250000, "size_mb": 40.0,
})
# -> {'label': 'Finance & Contrôle', 'confidence': 0.9x, 'probs': {...}, 'review_required': False}
```
Sans PyTorch — onnxruntime uniquement.

## Performance (test set, époque 22)
Accuracy **0.838** · Macro-F1 **0.802** · ECE après calibration **0.011** · Cohen-κ ~0.79.
Meilleur compromis accuracy/calibration/équilibre des rappels parmi toutes les versions.

## Contenu
```
predict.py · features.py · requirements-inference.txt · README.md
artifacts/
  model.onnx + model.onnx.data   ⚠️ indissociables (poids externes ~2.2 Go)
  tokenizer/ · scaler_params.npz · class_labels.json
  temperatures.json (7 T) · decision_offsets.json (7 offsets)
```
⚠️ `model.onnx` et `model.onnx.data` restent ensemble (même dossier). Fournir les métriques de schéma + le type-signature en production. Ordre des 7 classes = contractuel.
