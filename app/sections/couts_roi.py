"""Section « Coûts & ROI » du dashboard."""
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
        "Analyse des coûts & projection ROI",
        "Coût par domaine, Pareto, projection Monte-Carlo avec intervalles",
        "💰",
    )

    cost = safe_query("SELECT * FROM serving.v_cost_by_domain ORDER BY cost_rank")
    roi = safe_query("SELECT * FROM serving.v_roi_projection_summary ORDER BY year_offset")
    n1 = safe_query("SELECT * FROM serving.v_n1_comparison ORDER BY cost_n_usd DESC")

    if not cost.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Répartition du coût par domaine")
            pie = (
                alt.Chart(cost)
                .mark_arc(innerRadius=50)
                .encode(
                    theta=alt.Theta("current_cost_usd_year:Q", title="Coût $/an"),
                    color=alt.Color("domain_label:N", title="Domaine"),
                    tooltip=["domain_label", "current_cost_usd_year", "cost_share_pct"],
                )
            )
            st.altair_chart(pie, width='stretch')
        with c2:
            st.subheader("Pareto des coûts")
            base = alt.Chart(cost).encode(
                x=alt.X("domain_label:N", sort="-y", title=None,
                         axis=alt.Axis(labelAngle=-30, labelLimit=160, labelFontSize=10))
            )
            bars = base.mark_bar().encode(y=alt.Y("current_cost_usd_year:Q", title="Coût $/an"))
            line = base.mark_line(point=True, color="red").encode(
                y=alt.Y("cumulative_cost_pct:Q", title="% cumulé")
            )
            st.altair_chart(
                alt.layer(bars, line).resolve_scale(y="independent"),
                width='stretch',
            )

        st.dataframe(cost, width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Télécharger les coûts par domaine (CSV)",
            cost.to_csv(index=False).encode("utf-8"),
            file_name="couts_par_domaine.csv", mime="text/csv",
        )

    if not roi.empty:
        src = "observée" if (roi["growth_source"].iloc[0] == "observed") else "hypothèse"
        st.subheader(
            f"Projection ROI sur {int(roi['year_offset'].max())} ans "
            f"— croissance {roi['growth_mean_pct'].iloc[0]}%/an ({src})"
        )

        cc1, cc2 = st.columns(2)
        with cc1:
            st.caption("Coût **cumulé** : sans action vs avec archivage")
            roi_long = roi.melt(
                id_vars="year_offset",
                value_vars=["cumul_cost_no_action_usd", "cumul_cost_with_archiving_usd"],
                var_name="scénario",
                value_name="coût_cumulé_usd",
            )
            roi_long["scénario"] = roi_long["scénario"].map({
                "cumul_cost_no_action_usd": "Sans archivage",
                "cumul_cost_with_archiving_usd": "Avec archivage",
            })
            line = (
                alt.Chart(roi_long)
                .mark_line(point=True)
                .encode(
                    x=alt.X("year_offset:O", title="Année (N+k)"),
                    y=alt.Y("coût_cumulé_usd:Q", title="Coût cumulé $"),
                    color=alt.Color("scénario:N", title=None),
                    tooltip=["year_offset", "scénario", "coût_cumulé_usd"],
                )
            )
            st.altair_chart(line, width='stretch')
        with cc2:
            st.caption("Économie nette cumulée — médiane + intervalle P10–P90 (Monte Carlo)")
            band = (
                alt.Chart(roi)
                .mark_area(opacity=0.25, color="#2e8b57")
                .encode(
                    x=alt.X("year_offset:O", title="Année (N+k)"),
                    y=alt.Y("net_savings_p10_usd:Q", title="Économie nette cumulée $"),
                    y2="net_savings_p90_usd:Q",
                )
            )
            median = (
                alt.Chart(roi)
                .mark_line(point=True, color="#2e8b57")
                .encode(
                    x="year_offset:O",
                    y="net_savings_p50_usd:Q",
                    tooltip=[
                        "year_offset", "net_savings_p10_usd",
                        "net_savings_p50_usd", "net_savings_p90_usd",
                        "breakeven_probability",
                    ],
                )
            )
            st.altair_chart(band + median, width='stretch')

        st.dataframe(roi, width="stretch", hide_index=True)

    if not n1.empty:
        with st.expander("📉 Comparaison N-1 (réelle, snapshots historiques)"):
            st.dataframe(n1, width="stretch", hide_index=True)
