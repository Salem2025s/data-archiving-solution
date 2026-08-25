"""Section « Clés partagées » du dashboard."""
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
        "Clés métier partagées entre domaines",
        "Champs-clés communs (ex. SETID) — couplage potentiel, pas des FK",
        "🔗",
    )
    st.caption("PeopleSoft ne déclare pas de clés étrangères : ces liens signalent un "
               "vocabulaire commun / couplage potentiel, pas des dépendances prouvées.")

    dep = safe_query("SELECT * FROM serving.mv_domain_dependency ORDER BY shared_asset_count DESC")
    if dep.empty:
        st.stop()

    domains = sorted(set(dep["source_domain"]) | set(dep["target_domain"]))
    pick = st.selectbox("Filtrer par domaine", ["(tous)"] + domains)
    view = dep if pick == "(tous)" else dep[(dep["source_domain"] == pick) | (dep["target_domain"] == pick)]

    st.metric("Liens (clés partagées)", len(view))

    # Agréger par paire (source ↔ target) — une ligne peut exister par bridge_field
    top = (
        view.groupby(["source_domain", "target_domain"], as_index=False)
        .agg(
            shared_asset_count=("shared_asset_count", "sum"),
            nb_champs=("bridge_field", "nunique"),
            champs_pont=("bridge_field", lambda x: ", ".join(sorted(x.unique()))),
        )
        .sort_values("shared_asset_count", ascending=False)
        .head(20)
        .copy()
    )
    top["paire"] = top["source_domain"] + " ↔ " + top["target_domain"]

    bars = (
        alt.Chart(top)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X(
                "shared_asset_count:Q",
                title="Assets partagés (total)",
                axis=alt.Axis(grid=True, format=","),
            ),
            y=alt.Y("paire:N", sort="-x", title=None, axis=alt.Axis(labelLimit=340)),
            color=alt.Color(
                "source_domain:N",
                scale=alt.Scale(domain=list(_PAL), range=list(_PAL.values())),
                legend=alt.Legend(title="Domaine source", orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("source_domain:N",      title="Domaine source"),
                alt.Tooltip("target_domain:N",      title="Domaine cible"),
                alt.Tooltip("champs_pont:N",        title="Champs partagés"),
                alt.Tooltip("nb_champs:Q",          title="Nb champs"),
                alt.Tooltip("shared_asset_count:Q", title="Assets total", format=","),
            ],
        )
    )

    labels = (
        alt.Chart(top)
        .mark_text(align="left", dx=5, fontSize=11, color="#444")
        .encode(
            x=alt.X("shared_asset_count:Q"),
            y=alt.Y("paire:N", sort="-x"),
            text=alt.Text("shared_asset_count:Q", format=","),
        )
    )

    st.subheader("Top 20 liens (nb records partagés)")
    st.altair_chart((bars + labels).properties(height=500), width='stretch')
    st.dataframe(view, width="stretch", hide_index=True)
