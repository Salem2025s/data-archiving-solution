"""Cycle de vie automatisé — ré-entraînement candidat + promotion sous non-régression (C5.3.4).

À chaque exécution :
  1. COLLECTE       : jeu "existant" + un "nouveau lot" de données étiquetées.
  2. RÉ-ENTRAÎNEMENT: un modèle CANDIDAT sur (existant + nouveau lot).
  3. ÉVALUATION     : candidat vs production, sur un holdout fixe (macro-F1).
  4. RÈGLE DE REMPLACEMENT : le candidat n'est promu QUE s'il ne régresse pas de
     plus de --tolerance (0,01) — jamais à l'aveugle.
  5. DÉCISION journalisée ; si promu, la nouvelle version est enregistrée.

Données :
  --synthetic  : génère un jeu SYNTHÉTIQUE (schéma métier), pour la CI / la
                 démonstration du MÉCANISME (les données ne sont pas réelles).
  --input PATH : jeu réel (dataset enrichi). En production, branché sur les
                 nouvelles tables + corrections de revue collectées.

Métrique : macro-F1 · Validation : holdout stratifié (seed 42).
NB : le mécanisme (candidat / non-régression / promotion) est identique en réel ;
en production, le ré-entraînement final passe par src.ml.train_production_classifier.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import LinearSVC

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
SEED = 42
DEFAULT_TOLERANCE = 0.01

# Lexiques par domaine — avec des mots SIGNATURE et des mots PARTAGÉS entre
# domaines proches (Finance/Ventes, Achats/Supply, IT/Other) pour créer une
# confusion réaliste : le jeu n'est PAS parfaitement séparable (macro-F1 ~0,8).
DOMAINS: dict[str, list[str]] = {
    "Finance & Contrôle": ["account", "ledger", "gl", "journal", "tax", "invoice", "payment"],
    "RH": ["employee", "salary", "leave", "payroll", "person", "absence"],
    "Achats & Fournisseurs": ["vendor", "purchase", "po", "supplier", "voucher", "item"],
    "Ventes & Clients": ["customer", "sales", "quote", "opportunity", "invoice", "payment"],
    "Supply Chain / Logistique / Production": ["shipment", "warehouse", "inventory", "delivery", "item", "order"],
    "IT & Sécurité": ["server", "log", "security", "auth", "system", "role"],
    "Other": ["misc", "temp", "staging", "aux", "system", "role"],
}
# Jetons communs SANS signal (diluent le nom, rapprochent les classes)
COMMON = ["ps", "tbl", "rec", "data", "id", "cd", "dt", "flg", "seq", "hdr", "num", "ts"]


def synth_dataset(n_per_class: int, seed: int, noise: float) -> pd.DataFrame:
    """Jeu synthétique au schéma métier : signal apprenable MAIS bruité et non
    parfaitement séparable (mots partagés + jetons communs + fuite inter-domaines)."""
    rng = np.random.default_rng(seed)
    doms = list(DOMAINS)
    rows = []
    for dom in doms:
        sig = DOMAINS[dom]
        for _ in range(n_per_class):
            toks = list(rng.choice(sig, size=int(rng.integers(1, 3)), replace=True))   # 1-2 signature
            toks += list(rng.choice(COMMON, size=int(rng.integers(3, 6)), replace=True))  # 3-5 bruit neutre
            if rng.random() < noise:  # fuite : un mot signature d'un AUTRE domaine
                other = rng.choice([d for d in doms if d != dom])
                toks += list(rng.choice(DOMAINS[other], size=1))
            rng.shuffle(toks)
            rows.append({"text": "ps_" + "_".join(toks), "business_domain": dom,
                         "consensus": float(rng.uniform(0.7, 1.0))})
    return pd.DataFrame(rows).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def load_real(input_path: str) -> pd.DataFrame:
    df = pd.read_csv(input_path, low_memory=False)
    text = (df.get("technical_name", pd.Series([""] * len(df))).astype(str) + " "
            + df.get("column_names_text", pd.Series([""] * len(df))).astype(str))
    out = pd.DataFrame({"text": text, "business_domain": df["business_domain"].astype(str)})
    out["consensus"] = (pd.to_numeric(df.get("llm_consensus_score"), errors="coerce").fillna(1.0)
                        if "llm_consensus_score" in df else 1.0)
    return out


def make_pipe() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
        ("clf", LinearSVC(C=1.0, class_weight="balanced", random_state=SEED, max_iter=4000)),
    ])


def macro_f1_on(train_df: pd.DataFrame, holdout_df: pd.DataFrame, labels) -> tuple[float, Pipeline]:
    pipe = make_pipe()
    pipe.fit(train_df["text"], train_df["y"], clf__sample_weight=train_df["consensus"].values)
    pred = pipe.predict(holdout_df["text"])
    return float(f1_score(holdout_df["y"], pred, average="macro", labels=labels)), pipe


def run(args: argparse.Namespace) -> int:
    mode = "SYNTHÉTIQUE (démonstration du mécanisme)" if args.synthetic else f"RÉEL ({args.input})"
    print("=" * 60)
    print("CYCLE DE VIE AUTOMATISÉ — ré-entraînement sous non-régression (C5.3.4)")
    print(f"Mode données : {mode}")
    print("=" * 60)

    if args.synthetic or not args.input:
        df = synth_dataset(args.n_per_class, SEED, args.noise)
    else:
        df = load_real(args.input)

    le = LabelEncoder().fit(df["business_domain"])
    df["y"] = le.transform(df["business_domain"])
    labels = list(range(len(le.classes_)))

    # holdout fixe + séparation existant / nouveau lot (collecte)
    pool, holdout = train_test_split(df, test_size=0.20, random_state=SEED, stratify=df["y"])
    existing, new_batch = train_test_split(pool, test_size=0.30, random_state=SEED, stratify=pool["y"])
    print(f"Données d'origine   : {len(existing)} lignes")
    print(f"Nouveau lot collecté: {len(new_batch)} lignes")
    print(f"Holdout d'évaluation: {len(holdout)} lignes\n")

    # PRODUCTION (actuel) = modèle sur l'existant ; CANDIDAT = sur existant + nouveau lot
    f1_prod, _ = macro_f1_on(existing, holdout, labels)
    candidate_train = pd.concat([existing, new_batch], ignore_index=True)
    f1_cand, cand_pipe = macro_f1_on(candidate_train, holdout, labels)

    delta = f1_cand - f1_prod
    promote = f1_cand >= (f1_prod - args.tolerance)

    print("=" * 60)
    print("DÉCISION AUTOMATIQUE DE MISE À JOUR")
    print("=" * 60)
    print(f"Macro-F1 production (actuel) : {f1_prod:.4f}")
    print(f"Macro-F1 candidat            : {f1_cand:.4f}   (Δ = {delta:+.4f})")
    print(f"Tolérance de régression      : {args.tolerance:.2f}")
    decision = "DÉPLOYER LE CANDIDAT" if promote else "GARDER LA PRODUCTION"
    print(f"Décision                     : {decision}")
    print("=" * 60)

    out_dir = ROOT / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "synthetic" if (args.synthetic or not args.input) else "real",
        "n_existing": len(existing), "n_new_batch": len(new_batch), "n_holdout": len(holdout),
        "macro_f1_production": round(f1_prod, 4),
        "macro_f1_candidate": round(f1_cand, 4),
        "delta": round(delta, 4),
        "tolerance": args.tolerance,
        "decision": "promote" if promote else "keep",
        "metric": "macro_f1", "seed": SEED,
    }
    (out_dir / "retrain_decision.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport -> {out_dir / 'retrain_decision.json'}")

    if promote:
        import joblib
        model_path = out_dir / "candidate_model.joblib"
        joblib.dump({"pipeline": cand_pipe, "classes": list(le.classes_), **report}, model_path, compress=3)
        print(f"Candidat promu et sauvegardé -> {model_path}")
        # trace d'enregistrement (registre de ré-entraînement)
        reg = out_dir / "retrain_registry.jsonl"
        with reg.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report, ensure_ascii=False) + "\n")
        print(f"Enregistré au registre de ré-entraînement -> {reg}")
    else:
        print("Aucune promotion : la production reste en place (non-régression non satisfaite).")

    return 0  # le job réussit ; la décision est le livrable, pas un échec


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Ré-entraînement automatique sous non-régression (C5.3.4).")
    p.add_argument("--synthetic", action="store_true", help="Jeu synthétique (CI / démonstration du mécanisme).")
    p.add_argument("--input", default=None, help="CSV réel (dataset enrichi) — sinon --synthetic.")
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE, help="Régression max tolérée en macro-F1 (défaut 0,01).")
    p.add_argument("--n-per-class", type=int, default=180, help="Lignes/classe pour le jeu synthétique.")
    p.add_argument("--noise", type=float, default=0.40, help="Bruit inter-domaines du jeu synthétique (0,4 → macro-F1 ~0,80).")
    args = p.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
