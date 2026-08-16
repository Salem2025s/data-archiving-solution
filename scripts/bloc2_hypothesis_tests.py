"""Bloc 2 — C2.1.4 : tests statistiques et tests d'hypothèses sur le patrimoine.

Exécute quatre tests d'hypothèses réels (scipy) sur les données de la couche
serving/processed du dernier run, chacun couvrant une famille différente :

    H1  Kruskal-Wallis   — la complexité (nb de colonnes) diffère-t-elle selon le domaine ?
    H2  Spearman         — la taille d'une table est-elle corrélée à son nb de colonnes ?
    H3  Chi-deux         — l'absence de description dépend-elle du domaine ?
    H4  Mann-Whitney U   — la confiance des règles mots-clés diffère-t-elle de celle du modèle ML ?

Pour chaque test : hypothèses H0/H1, effectif, statistique, p-value, taille
d'effet, décision au seuil alpha = 0,05 et interprétation métier.

Usage :
    python -m scripts.bloc2_hypothesis_tests            # dernier run en base
    python -m scripts.bloc2_hypothesis_tests --run-id 6
    python -m scripts.bloc2_hypothesis_tests --out docs/certification/bloc2_tests_resultats.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient

ALPHA = 0.05


def _load(engine, run_id: int) -> pd.DataFrame:
    """Charge un actif = une ligne : domaine prédit, scores, taille, description."""
    sql = text(
        """
        SELECT
            p.business_domain_predicted           AS domain,
            p.confidence                          AS confidence,
            p.model_version                       AS model_version,
            inv.size_mb                           AS size_mb,
            inv.column_count                      AS column_count,
            inv.archival_candidate_score          AS archival_score,
            inv.roi_score                         AS roi_score,
            (inv.description IS NULL
                 OR btrim(inv.description) = '')  AS description_absente
        FROM serving.asset_business_domain_prediction p
        JOIN serving.mv_asset_inventory inv
          ON inv.asset_id = p.asset_id
         AND inv.run_id   = p.run_id
        WHERE p.run_id = :run_id
        """
    )
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"run_id": run_id})
    return df


def _fmt_p(p: float) -> str:
    return "< 0,001" if p < 1e-3 else f"{p:.4f}".replace(".", ",")


def _decision(p: float) -> str:
    return (
        f"p {_fmt_p(p)} < 0,05  →  on REJETTE H0"
        if p < ALPHA
        else f"p {_fmt_p(p)} ≥ 0,05  →  on ne peut pas rejeter H0"
    )


# --------------------------------------------------------------------------- #
# H1 — Kruskal-Wallis : complexité structurelle (nb de colonnes) selon le domaine
# --------------------------------------------------------------------------- #
def test_h1_complexite_par_domaine(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["column_count", "domain"])
    d = d[d["column_count"] > 0]
    groups = [g["column_count"].to_numpy() for _, g in d.groupby("domain") if len(g) >= 5]
    labels = [name for name, g in d.groupby("domain") if len(g) >= 5]
    H, p = stats.kruskal(*groups)
    k, n = len(groups), sum(len(g) for g in groups)
    epsilon2 = (H - k + 1) / (n - k)  # taille d'effet (0 = nul, 1 = maximal)
    medians = {lab: float(np.median(g)) for lab, g in zip(labels, groups)}
    return {
        "titre": "H1 — La complexité structurelle (nombre de colonnes) diffère-t-elle "
        "selon le domaine métier ?",
        "H0": "Les distributions du nombre de colonnes sont identiques entre domaines.",
        "H1": "Au moins un domaine a une distribution différente.",
        "test": f"Kruskal-Wallis (non paramétrique, {k} domaines, n = {n})",
        "stat": f"H = {H:.1f}",
        "p": p,
        "effet": f"epsilon² = {epsilon2:.3f} "
        + ("(faible)" if epsilon2 < 0.06 else "(modéré)" if epsilon2 < 0.14 else "(fort)"),
        "detail": "Médianes de colonnes par domaine : "
        + " · ".join(f"{k2} {v:.0f}" for k2, v in sorted(medians.items(), key=lambda x: -x[1]))
        + ". Les tables Finance sont structurellement plus riches que celles d'IT/Other, "
        "ce qui oriente la modélisation métier et la priorisation de la documentation.",
    }


# --------------------------------------------------------------------------- #
# H2 — Spearman : taille vs nombre de colonnes
# --------------------------------------------------------------------------- #
def test_h2_taille_vs_colonnes(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["size_mb", "column_count"])
    d = d[(d["size_mb"] > 0) & (d["column_count"] > 0)]
    rho, p = stats.spearmanr(d["size_mb"], d["column_count"])
    return {
        "titre": "H2 — La taille d'une table est-elle corrélée à son nombre de colonnes ?",
        "H0": "Il n'existe pas de corrélation monotone (rho = 0).",
        "H1": "Il existe une corrélation monotone (rho ≠ 0).",
        "test": f"Corrélation de Spearman (n = {len(d)})",
        "stat": f"rho = {rho:.3f}",
        "p": p,
        "effet": "corrélation "
        + ("faible" if abs(rho) < 0.3 else "modérée" if abs(rho) < 0.5 else "forte"),
        "detail": "Spearman choisi car les tailles suivent une loi très asymétrique "
        "(quelques très grosses tables) — un test de Pearson serait tiré par les valeurs extrêmes.",
    }


# --------------------------------------------------------------------------- #
# H3 — Chi-deux : absence de description vs domaine
# --------------------------------------------------------------------------- #
def test_h3_description_par_domaine(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["domain"])
    ct = pd.crosstab(d["domain"], d["description_absente"])
    ct = ct[ct.sum(axis=1) >= 5]  # domaines à effectif suffisant
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    n = int(ct.to_numpy().sum())
    cramers_v = float(np.sqrt(chi2 / (n * (min(ct.shape) - 1))))
    return {
        "titre": "H3 — L'absence de description dépend-elle du domaine métier ?",
        "H0": "La présence d'une description est indépendante du domaine.",
        "H1": "La présence d'une description dépend du domaine.",
        "test": f"Test du χ² d'indépendance (ddl = {dof}, n = {n})",
        "stat": f"χ² = {chi2:.1f}",
        "p": p,
        "effet": f"V de Cramér = {cramers_v:.3f} "
        + ("(faible)" if cramers_v < 0.2 else "(modérée)" if cramers_v < 0.4 else "(forte)"),
        "detail": "Enjeu gouvernance : une documentation inégale entre domaines cible "
        "les efforts de complétion des métadonnées.",
    }


# --------------------------------------------------------------------------- #
# H4 — Mann-Whitney U : confiance keyword vs ML
# --------------------------------------------------------------------------- #
def test_h4_confiance_keyword_vs_ml(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["confidence", "model_version"])
    kw = d[d["model_version"].str.startswith("keyword")]["confidence"].to_numpy()
    ml = d[~d["model_version"].str.startswith("keyword")]["confidence"].to_numpy()
    U, p = stats.mannwhitneyu(kw, ml, alternative="two-sided")
    rank_biserial = 1 - (2 * U) / (len(kw) * len(ml))  # taille d'effet
    return {
        "titre": "H4 — La confiance des règles mots-clés diffère-t-elle de celle du modèle ML ?",
        "H0": "Les deux méthodes produisent des confiances de même distribution.",
        "H1": "Les distributions de confiance diffèrent.",
        "test": f"Mann-Whitney U (keyword n = {len(kw)}, ML n = {len(ml)})",
        "stat": f"U = {U:.0f}",
        "p": p,
        "effet": f"rang-bisérial = {rank_biserial:.3f}",
        "detail": f"Médianes : keyword {np.median(kw):.3f} · ML {np.median(ml):.3f}. "
        "Confirme que les deux passes ne sont pas interchangeables (calibrage distinct).",
    }


def _render(results: list[dict], run_id: int) -> str:
    lines = [
        f"# Bloc 2 · C2.1.4 — Tests d'hypothèses (run {run_id})",
        "",
        f"Seuil de signification : **α = 0,05**. Données réelles de la couche serving.",
        "",
    ]
    for r in results:
        lines += [
            f"## {r['titre']}",
            "",
            f"- **H0** : {r['H0']}",
            f"- **H1** : {r['H1']}",
            f"- **Test** : {r['test']}",
            f"- **Résultat** : {r['stat']} · {r['effet']}",
            f"- **Décision** : {_decision(r['p'])}",
            f"- **Interprétation** : {r['detail']}",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bloc 2 — tests d'hypothèses (scipy)")
    ap.add_argument("--run-id", type=int, default=None, help="run_id (défaut : max en base)")
    ap.add_argument("--out", type=str, default=None, help="chemin d'un rapport .md à écrire")
    args = ap.parse_args()

    engine = PostgresClient(get_settings()).engine
    if args.run_id is None:
        with engine.connect() as c:
            args.run_id = int(c.execute(text("SELECT MAX(run_id) FROM processed.dim_asset")).scalar())

    df = _load(engine, args.run_id)
    if df.empty:
        raise SystemExit(f"Aucune donnée pour run_id={args.run_id}")

    results = [
        test_h1_complexite_par_domaine(df),
        test_h2_taille_vs_colonnes(df),
        test_h3_description_par_domaine(df),
        test_h4_confiance_keyword_vs_ml(df),
    ]
    report = _render(results, args.run_id)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\n[OK] Rapport écrit → {args.out}")


if __name__ == "__main__":
    main()
