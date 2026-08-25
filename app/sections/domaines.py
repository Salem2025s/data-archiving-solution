"""Section « Domaines » du dashboard."""
from __future__ import annotations

import altair as alt  # noqa: F401
import pandas as pd  # noqa: F401
import streamlit as st
from sqlalchemy import text  # noqa: F401

from dashboard_common import (  # noqa: F401
    _PAL, _load_classifier, get_engine, load_saved_queries, page_header,
    run_command, run_query, safe_query, safe_query_params, write_saved_queries,
)


def render() -> None:
    page_header(
        "Profil par domaine métier",
        "Score d'archivage, risque, qualité des données par domaine",
        "🗂️",
    )

    profile = safe_query("SELECT * FROM serving.mv_domain_profile ORDER BY asset_count DESC")
    if profile.empty:
        st.stop()

    st.dataframe(profile, width="stretch", hide_index=True)
    st.download_button(
        "⬇️ Télécharger le profil par domaine (CSV)",
        profile.to_csv(index=False).encode("utf-8"),
        file_name="profil_par_domaine.csv", mime="text/csv",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Score d'archivage moyen")
        _sc = alt.Chart(profile).mark_bar(cornerRadiusEnd=3).encode(
            x=alt.X(
                "avg_archival_score:Q",
                title="Score moyen",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format=".2f"),
            ),
            y=alt.Y(
                "domain_label:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=260),
            ),
            color=alt.Color(
                "domain_label:N",
                scale=alt.Scale(domain=list(_PAL), range=list(_PAL.values())),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("domain_label:N", title="Domaine"),
                alt.Tooltip("avg_archival_score:Q", title="Score", format=".3f"),
            ],
        )
        _scl = alt.Chart(profile).mark_text(align="left", dx=4, fontSize=11, color="#444").encode(
            x=alt.X("avg_archival_score:Q", scale=alt.Scale(zero=False)),
            y=alt.Y("domain_label:N", sort="-x"),
            text=alt.Text("avg_archival_score:Q", format=".2f"),
        )
        st.altair_chart((_sc + _scl).properties(height=270), width='stretch')
    with col_b:
        st.subheader("Niveau de risque (hiérarchie de records PeopleSoft)")
        risk = profile[["domain_label", "avg_lineage_out", "risk_level"]].copy()
        st.dataframe(risk, width="stretch", hide_index=True)

    st.subheader("Qualité des données")
    qual = profile[["domain_label", "avg_nullable_ratio", "assets_without_description"]]
    st.dataframe(qual, width="stretch", hide_index=True)
