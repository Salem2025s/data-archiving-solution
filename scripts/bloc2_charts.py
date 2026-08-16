"""Bloc 2 — génère les graphiques analytiques du dossier (PNG).

Actuellement : le boxplot du nombre de colonnes par domaine, qui illustre
visuellement le test H1 (Kruskal-Wallis). Une seule teinte : les domaines sont
identifiés par l'axe, la couleur ne porte donc aucune information (évite le
« couleur par rang »). Trié par médiane décroissante.

Usage : python -m scripts.bloc2_charts
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import text

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient

OUT = Path("docs/certification/Bloc 2/boxplot_colonnes_par_domaine.png")
BLUE_FILL = "#BFD3F6"
BLUE_EDGE = "#2563EB"
INK = "#0F172A"
GRID = "#E6EAF2"


def load(run_id: int = 9) -> pd.DataFrame:
    eng = PostgresClient(get_settings()).engine
    sql = text(
        """
        SELECT p.business_domain_predicted AS domain, inv.column_count AS n_cols
        FROM serving.asset_business_domain_prediction p
        JOIN serving.mv_asset_inventory inv
          ON inv.asset_id = p.asset_id AND inv.run_id = p.run_id
        WHERE p.run_id = :r AND inv.column_count > 0
        """
    )
    with eng.connect() as c:
        return pd.read_sql(sql, c, params={"r": run_id})


def build() -> None:
    df = load()
    order = (
        df.groupby("domain")["n_cols"].median().sort_values().index.tolist()
    )  # croissant -> Finance finira en haut (dernier)
    data = [df.loc[df["domain"] == d, "n_cols"].to_numpy() for d in order]
    medians = [float(pd.Series(x).median()) for x in data]

    fig, ax = plt.subplots(figsize=(8.2, 4.3), dpi=150)
    # Distribution très asymétrique (queue jusqu'à des centaines de colonnes) :
    # on montre l'écart interquartile Q1–médiane–Q3, sans tracer la longue queue.
    ax.boxplot(
        data,
        vert=False,
        whis=(25, 75),          # bornes = quartiles -> pas de moustache (queue non représentée)
        showfliers=False,
        showcaps=False,
        widths=0.62,
        patch_artist=True,
        medianprops=dict(color=INK, linewidth=2.2),
        whiskerprops=dict(linewidth=0),
        boxprops=dict(facecolor=BLUE_FILL, edgecolor=BLUE_EDGE, linewidth=1.3),
    )

    ax.set_yticklabels(order, fontsize=9, color=INK)
    ax.set_xlabel("Nombre de colonnes par table (écart interquartile)", fontsize=9.5, color=INK)
    ax.set_title(
        "Distribution du nombre de colonnes par domaine métier (run 9)",
        fontsize=11, color=INK, fontweight="bold", pad=10,
    )
    ax.set_xlim(0, 60)

    # médianes annotées
    for i, m in enumerate(medians):
        ax.annotate(f"méd. {m:.0f}", (m, i + 1), xytext=(5, 9),
                    textcoords="offset points", fontsize=8, color=BLUE_EDGE, fontweight="bold")

    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)

    fig.text(0.125, -0.02,
             "Boîtes = Q1 · médiane · Q3 (50 % central des tables).   La queue supérieure, très étalée "
             "(jusqu'à plusieurs centaines de colonnes), n'est pas représentée pour la lisibilité.",
             fontsize=7.5, color="#64748B")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"OK -> {OUT}  ({OUT.stat().st_size:,} octets)")


if __name__ == "__main__":
    build()
