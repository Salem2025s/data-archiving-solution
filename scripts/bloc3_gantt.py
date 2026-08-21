"""Génère le diagramme de Gantt du planning projet (Bloc 3), phases réelles.

Les phases sont reconstruites à partir des dates de commits Git réelles.
Une seule teinte (les phases sont une même catégorie) : l'identité passe par
la position et les libellés, pas par la couleur — robuste au daltonisme.

Usage : python scripts/bloc3_gantt.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "certification" / "bloc3_gantt.png"

ACCENT = "#2563EB"   # bleu projet (accent unique)
INK = "#0F172A"      # texte sombre (contraste élevé)
MUTED = "#64748B"    # texte secondaire
GRID = "#E6EAF2"     # grille récessive

# (libellé, début, fin)  — début 09/03 (runs admin.pipeline_run), puis commits Git
PHASES = [
    ("P0 · Cadrage & collecte",          date(2026, 3, 9),  date(2026, 3, 31)),
    ("P1 · Modélisation & analyse",      date(2026, 4, 1),  date(2026, 5, 31)),
    ("P2 · Sûreté & fiabilité",          date(2026, 6, 1),  date(2026, 6, 9)),
    ("P3 · Deep Learning (XLM-R)",       date(2026, 6, 9),  date(2026, 6, 19)),
    ("P4 · Sécurité & externalisation",  date(2026, 7, 7),  date(2026, 7, 17)),
    ("P5 · Certification (Blocs 1-5)",   date(2026, 7, 14), date(2026, 8, 29)),
]


def build() -> None:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    labels = [p[0] for p in PHASES]
    y = range(len(PHASES))

    for i, (_, start, end) in enumerate(PHASES):
        width = (end - start).days or 1
        ax.barh(
            i, width, left=start, height=0.5,
            color=ACCENT, edgecolor="white", linewidth=1.2, zorder=3,
        )
        # étiquette de dates au bout de la barre
        ax.text(
            end, i, f"  {start.strftime('%d/%m')}→{end.strftime('%d/%m')}",
            va="center", ha="left", fontsize=7.5, color=MUTED, zorder=4,
        )

    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=9.5, color=INK)
    ax.invert_yaxis()  # P0 en haut (ordre chronologique)

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(axis="x", labelsize=8, colors=MUTED)

    # grille verticale récessive uniquement
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    ax.set_title(
        "Planning du projet — phases réelles (runs admin.pipeline_run + historique Git)",
        fontsize=11, color=INK, fontweight="bold", pad=12, loc="left",
    )
    ax.margins(x=0.02)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"OK -> {OUT}  ({OUT.stat().st_size:,} octets)")


if __name__ == "__main__":
    build()
