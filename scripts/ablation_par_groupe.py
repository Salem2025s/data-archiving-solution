"""Ablation par groupe de features — méthode wrapper (compétence C5.2.2).

Principe
--------
On retire une **famille entière** de features, on **réentraîne** le LinearSVC de
production, on mesure le **macro-F1 sur le holdout**, et on compare à la
référence (toutes features). La chute de score mesure la contribution du groupe.

Parité avec la production
-------------------------
Le script **réutilise les helpers de features** de
``src/ml/train_production_classifier.py`` (`_fit_char_word`, `_numeric_matrix`,
`_make_ohe`, `_cat_frame`, `_compose_text`, `_numeric_feature_order`). Les
features sont donc **strictement identiques** à celles du modèle déployé — pas de
logique dupliquée. Le split est **fixe** (``random_state`` de production) : les
écarts se lisent *entre configurations*, sur le même holdout, et ne remplacent
pas le chiffre publié du modèle (voir la carte modèle).

Sortie
------
Écrit ``artifacts/ablation_par_groupe.csv`` (Configuration, Macro-F1, Δ vs
référence) — la source du tableau d'ablation de la soutenance.

Usage
-----
    python -m scripts.ablation_par_groupe
    python -m scripts.ablation_par_groupe --test-size 0.20 --output artifacts/ablation_par_groupe.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import LinearSVC

from src.ml import train_production_classifier as T

# liblinear peut ne pas converger à max_iter borné (choix de production) : le
# score reste valable, on masque seulement l'avertissement pour une sortie propre.
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "artifacts" / "ablation_par_groupe.csv"

# Familles de features (les 4 blocs empilés en production) et configurations testées.
_BLOCKS = ("char", "word", "num", "ohe")
_CONFIGS: list[tuple[str, tuple[str, ...]]] = [
    ("Toutes les features (référence)", ("char", "word", "num", "ohe")),
    ("sans TEXTE (char + word)",        ("num", "ohe")),
    ("sans NUMÉRIQUE (129 features)",   ("char", "word", "ohe")),
    ("sans OHE (catégoriel)",           ("char", "word", "num")),
    ("TEXTE seul",                      ("char", "word")),
    ("NUMÉRIQUE seul",                  ("num",)),
]


def _load_gold(input_path: str) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Charge le gold (consensus >= seuil), encode la cible, renvoie les poids."""
    df = pd.read_csv(input_path, low_memory=False)
    cons = pd.to_numeric(df[T.CONSENSUS_COL], errors="coerce").fillna(0.0)
    gold = df[cons >= T.CONSENSUS_SOFT_FLOOR].reset_index(drop=True)
    weights = (
        pd.to_numeric(gold[T.CONSENSUS_COL], errors="coerce")
        .fillna(1.0)
        .astype(np.float32)
        .values
    )
    y = LabelEncoder().fit_transform(gold[T.TARGET].astype(str).str.strip())
    return gold.to_dict("records"), y, weights


def _make_block_builder(rows_tr: list[dict]):
    """Ajuste les 4 blocs de features sur le TRAIN uniquement (aucune fuite)."""
    names = T._numeric_feature_order()
    char_v, word_v, _, _ = T._fit_char_word(rows_tr)
    scaler = StandardScaler(with_mean=False).fit(T._numeric_matrix(rows_tr, names))
    ohe = T._make_ohe().fit(T._cat_frame(rows_tr))

    def block(rows_: list[dict], key: str) -> csr_matrix:
        if key == "char":
            return csr_matrix(char_v.transform(T._compose_text(rows_, list(T.DEFAULT_TEXT_COLS_CHAR))))
        if key == "word":
            return csr_matrix(word_v.transform(T._compose_text(rows_, list(T.DEFAULT_TEXT_COLS_WORD))))
        if key == "num":
            return csr_matrix(scaler.transform(T._numeric_matrix(rows_, names)))
        if key == "ohe":
            return csr_matrix(ohe.transform(T._cat_frame(rows_)))
        raise ValueError(f"bloc inconnu : {key}")

    return block


def run_ablation(input_path: str, test_size: float, output_path: Path) -> list[tuple[str, float, float]]:
    """Exécute l'ablation par groupe et écrit le CSV. Renvoie (label, macro_f1, delta)."""
    rows, y, w = _load_gold(input_path)
    itr, iho = train_test_split(
        np.arange(len(rows)), test_size=test_size, random_state=T.RANDOM_STATE, stratify=y
    )
    rows_tr = [rows[i] for i in itr]
    rows_ho = [rows[i] for i in iho]
    y_tr, y_ho, w_tr = y[itr], y[iho], w[itr]

    block = _make_block_builder(rows_tr)
    cache = {k: (block(rows_tr, k), block(rows_ho, k)) for k in _BLOCKS}

    def macro_f1(keys: tuple[str, ...]) -> float:
        x_tr = hstack([cache[k][0] for k in keys]).tocsr()
        x_ho = hstack([cache[k][1] for k in keys]).tocsr()
        clf = LinearSVC(C=1.0, class_weight="balanced", max_iter=4000, random_state=T.RANDOM_STATE)
        clf.fit(x_tr, y_tr, sample_weight=w_tr)
        return float(f1_score(y_ho, clf.predict(x_ho), average="macro"))

    scores = [(label, macro_f1(keys)) for label, keys in _CONFIGS]
    ref = scores[0][1]
    results = [(label, m, m - ref) for label, m in scores]

    pct = int(round(test_size * 100))
    col_f1 = f"Macro-F1 (holdout {pct}%)"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as fh:
        wtr = csv.writer(fh)
        wtr.writerow(["Configuration", col_f1, "Delta vs reference"])
        for label, m, d in results:
            wtr.writerow([label, f"{m:.4f}", f"{d:+.4f}"])

    # Sortie lisible en console
    print(f"Gold : {len(rows)} lignes · holdout {pct}% · {len(rows_ho)} tables · seed {T.RANDOM_STATE}\n")
    print(f"{'Configuration':34s} {col_f1:>22s} {'Δ vs réf.':>12s}")
    print("-" * 70)
    for label, m, d in results:
        print(f"{label:34s} {m:>22.4f} {d:>+12.4f}")
    print(f"\nOK -> {output_path}")
    return results


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Ablation par groupe de features (C5.2.2).")
    parser.add_argument("--input", default=T.DEFAULT_INPUT, help="CSV du dataset gold (défaut : dataset de production).")
    parser.add_argument("--test-size", type=float, default=0.20, help="Taille du holdout (défaut : 0.20, protocole du benchmark).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Chemin du CSV de sortie.")
    args = parser.parse_args()
    run_ablation(args.input, args.test_size, args.output)


if __name__ == "__main__":
    main()
