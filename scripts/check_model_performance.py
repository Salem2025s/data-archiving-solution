"""Garde-fou de performance (gate CI/CD) — C5.3.2 « évaluation des performances ».

Lit le registre de modèles (`artifacts/model_registry.json`), retrouve le modèle
en `stage=production` et vérifie que ses métriques respectent des seuils minimaux.
Sort en erreur (code 1) si le seuil n'est pas tenu, ce qui **bloque le déploiement**
dans le pipeline CI/CD. C'est l'étape d'évaluation automatisée des performances,
complémentaire des tests unitaires et du garde-fou de parité train/inférence.

Usage :
    python -m scripts.check_model_performance
    python -m scripts.check_model_performance --min-macro-f1 0.85
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "artifacts" / "model_registry.json"

# Seuils par défaut : sous ces valeurs, on refuse la promotion en production.
DEFAULT_MIN_MACRO_F1 = 0.80
DEFAULT_MIN_ACCURACY = 0.85


def _load_production_entry() -> dict:
    if not REGISTRY.exists():
        sys.exit(f"[ÉCHEC] Registre introuvable : {REGISTRY.relative_to(ROOT)}")
    entries = json.loads(REGISTRY.read_text(encoding="utf-8"))
    prod = [e for e in entries if e.get("stage") == "production"]
    if not prod:
        sys.exit("[ÉCHEC] Aucun modèle en 'production' dans le registre.")
    if len(prod) > 1:
        sys.exit(f"[ÉCHEC] {len(prod)} modèles en 'production' — une seule version attendue.")
    return prod[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate de performance du modèle de production")
    ap.add_argument("--min-macro-f1", type=float, default=DEFAULT_MIN_MACRO_F1)
    ap.add_argument("--min-accuracy", type=float, default=DEFAULT_MIN_ACCURACY)
    args = ap.parse_args()

    entry = _load_production_entry()
    metrics = entry.get("metrics", {})
    macro_f1 = metrics.get("macro_f1")
    accuracy = metrics.get("accuracy")

    print(f"Modèle production : {entry['version']} ({entry['algo']}) — commit {entry.get('git_commit')}")
    print(f"  macro-F1 = {macro_f1}  (seuil {args.min_macro_f1})")
    print(f"  accuracy = {accuracy}  (seuil {args.min_accuracy})")

    failures = []
    if macro_f1 is None or macro_f1 < args.min_macro_f1:
        failures.append(f"macro-F1 {macro_f1} < {args.min_macro_f1}")
    if accuracy is None or accuracy < args.min_accuracy:
        failures.append(f"accuracy {accuracy} < {args.min_accuracy}")

    if failures:
        print("[ÉCHEC] Seuils de performance non tenus : " + " ; ".join(failures))
        sys.exit(1)
    print("[OK] Le modèle de production respecte les seuils de performance.")


if __name__ == "__main__":
    main()
