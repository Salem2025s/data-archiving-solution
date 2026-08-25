"""Dashboard interactif de gouvernance des données (couche serving PostgreSQL).

Lance une démo web lisant directement les vues `serving.*` :
    streamlit run app/streamlit_dashboard.py

Sections : Vue d'ensemble · Domaines · Clés partagées · Archivage · Coûts & ROI.
Aucune écriture en base — lecture seule.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Rendre `src` importable quel que soit le répertoire de lancement
# (streamlit run place app/ sur le path, pas la racine du projet).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from src.config.settings import get_settings

st.set_page_config(
    page_title="Gouvernance des données — PFE",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Helpers partagés (extraits dans dashboard_common.py pour la maintenabilité)
from dashboard_common import (  # noqa: E402
    _inject_css, page_header, get_engine, run_query, safe_query,
    run_query_params, safe_query_params, _PAL, _PROJECT_ROOT,
    load_saved_queries, write_saved_queries, _load_classifier, run_command,
)

_inject_css()

# ---------------------------------------------------------------------------
# Barre latérale
# ---------------------------------------------------------------------------
st.sidebar.markdown(
    """
    <div class="sidebar-brand">
      <h2>📊 Gouvernance des données</h2>
      <p>Oracle PeopleSoft EP92U038 · couche serving</p>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    run_df = run_query("SELECT MAX(run_id) AS run_id FROM processed.dim_asset")
    run_id = int(run_df["run_id"].iloc[0]) if not run_df.empty and run_df["run_id"].iloc[0] is not None else 0
except Exception:
    run_id = 0

_online = bool(run_id)
st.sidebar.markdown(
    f"""
    <div class="sidebar-badge">
      <span class="dot {'dot-on' if _online else 'dot-off'}"></span>
      {'Run actif #' + str(run_id) if _online else 'Base hors-ligne'}
    </div>
    """,
    unsafe_allow_html=True,
)

# Navigation (icône + libellé pour un rendu homogène)
_NAV = {
    "🏠  Vue d'ensemble":  "Vue d'ensemble",
    "🔎  Recherche":        "Recherche",
    "🗂️  Domaines":         "Domaines",
    "🔗  Clés partagées":   "Clés partagées",
    "📦  Archivage":        "Archivage",
    "💰  Coûts & ROI":      "Coûts & ROI",
    "🚀  Pipelines":        "🚀 Pipelines",
    "⚙️  Paramètres":       "⚙️ Paramètres",
    "💾  Console SQL":      "💾 Console SQL",
    "🤖  Test du modèle":   "🤖 Test du modèle",
}
st.sidebar.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
_nav_label = st.sidebar.radio("Navigation", list(_NAV), label_visibility="collapsed")
section = _NAV[_nav_label]

st.sidebar.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
st.sidebar.button("🔄  Rafraîchir les données", on_click=st.cache_data.clear,
                  width='stretch')


# ===========================================================================
# 1. VUE D'ENSEMBLE
# ===========================================================================
from sections import (
    archivage, cles_partagees, console_sql, couts_roi, domaines, parametres, pipelines, recherche, test_modele, vue_ensemble,
)

if section == "Vue d'ensemble":
    vue_ensemble.render()

elif section == "Recherche":
    recherche.render()

elif section == "Domaines":
    domaines.render()

elif section == "Clés partagées":
    cles_partagees.render()

elif section == "Archivage":
    archivage.render()

elif section == "Coûts & ROI":
    couts_roi.render()

elif section == "🚀 Pipelines":
    pipelines.render()

elif section == "⚙️ Paramètres":
    parametres.render()

elif section == "💾 Console SQL":
    console_sql.render()

elif section == "🤖 Test du modèle":
    test_modele.render()
