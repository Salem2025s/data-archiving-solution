"""Section « Archivage » du dashboard."""
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
        "Recommandations d'archivage",
        "Stratégies proposées par table physique, filtrables et exportables",
        "📦",
    )

    summary = safe_query("SELECT * FROM serving.v_archiving_policy_summary")
    policies = safe_query("SELECT * FROM serving.dim_archiving_policy ORDER BY priority")

    if not summary.empty:
        by_strat = (
            summary.groupby("recommended_strategy", as_index=False)
            .agg(nb_assets=("asset_count", "sum"), volume_mb=("total_size_mb", "sum"))
            .sort_values("volume_mb", ascending=False)
        )
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Volume par stratégie (Mo)")
            _bv = alt.Chart(by_strat).mark_bar(cornerRadiusEnd=3, color="#4c8cbf").encode(
                x=alt.X("volume_mb:Q", title="Volume (Mo)", axis=alt.Axis(format=",")),
                y=alt.Y("recommended_strategy:N", sort="-x", title=None,
                        axis=alt.Axis(labelLimit=380, labelFontSize=11)),
                tooltip=[
                    alt.Tooltip("recommended_strategy:N", title="Stratégie"),
                    alt.Tooltip("volume_mb:Q", title="Volume (Mo)", format=",.0f"),
                    alt.Tooltip("nb_assets:Q", title="Nb assets", format=","),
                ],
            )
            _lbv = alt.Chart(by_strat).mark_text(align="left", dx=4, fontSize=10, color="#444").encode(
                x="volume_mb:Q",
                y=alt.Y("recommended_strategy:N", sort="-x"),
                text=alt.Text("volume_mb:Q", format=",.0f"),
            )
            st.altair_chart((_bv + _lbv).properties(height=280), width='stretch')
        with c2:
            st.subheader("Nb d'assets par stratégie")
            _bn = alt.Chart(by_strat).mark_bar(cornerRadiusEnd=3, color="#5ba85b").encode(
                x=alt.X("nb_assets:Q", title="Nb d'assets", axis=alt.Axis(format=",")),
                y=alt.Y("recommended_strategy:N", sort="-x", title=None,
                        axis=alt.Axis(labelLimit=380, labelFontSize=11)),
                tooltip=[
                    alt.Tooltip("recommended_strategy:N", title="Stratégie"),
                    alt.Tooltip("nb_assets:Q", title="Nb assets", format=","),
                    alt.Tooltip("volume_mb:Q", title="Volume (Mo)", format=",.0f"),
                ],
            )
            _lbn = alt.Chart(by_strat).mark_text(align="left", dx=4, fontSize=10, color="#444").encode(
                x="nb_assets:Q",
                y=alt.Y("recommended_strategy:N", sort="-x"),
                text=alt.Text("nb_assets:Q", format=","),
            )
            st.altair_chart((_bn + _lbn).properties(height=280), width='stretch')

    with st.expander("📋 Politiques d'archivage (référentiel)"):
        st.dataframe(policies, width="stretch", hide_index=True)

    st.subheader("Explorateur des recommandations")
    reco_filters = safe_query(
        "SELECT DISTINCT domain_label FROM serving.mv_archiving_recommendation ORDER BY 1"
    )
    strat_filters = safe_query(
        "SELECT DISTINCT recommended_strategy FROM serving.mv_archiving_recommendation ORDER BY 1"
    )
    col1, col2 = st.columns(2)
    dom = col1.selectbox("Domaine", ["(tous)"] + (reco_filters["domain_label"].tolist() if not reco_filters.empty else []))
    strat = col2.selectbox("Stratégie", ["(toutes)"] + (strat_filters["recommended_strategy"].tolist() if not strat_filters.empty else []))

    where = ["size_mb > 0"]
    params: dict = {}
    if dom != "(tous)":
        where.append("domain_label = :dom")
        params["dom"] = dom
    if strat != "(toutes)":
        where.append("recommended_strategy = :strat")
        params["strat"] = strat
    clause = " AND ".join(where)
    reco = safe_query_params(
        f"""SELECT technical_name, domain_label, recommended_strategy,
                   ROUND(size_mb::numeric,2) AS size_mb, age_band, sensitivity_level,
                   lineage_out_count, rationale
            FROM serving.mv_archiving_recommendation
            WHERE {clause}
            ORDER BY size_mb DESC LIMIT 300""",
        params,
    )
    st.caption(f"{len(reco)} assets (top 300 par taille)")
    st.dataframe(reco, width="stretch", hide_index=True)
    st.download_button(
        "⬇️ Télécharger les recommandations (CSV)",
        reco.to_csv(index=False).encode("utf-8"),
        file_name="recommandations_archivage.csv", mime="text/csv",
    )
