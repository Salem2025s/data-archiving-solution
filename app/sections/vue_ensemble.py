"""Section « Vue d'ensemble » du dashboard."""
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
        "Vue d'ensemble du patrimoine de données",
        "Cartographie, volumétrie et potentiel d'archivage — lecture seule",
        "🏠",
    )

    impact   = safe_query("SELECT * FROM serving.v_storage_impact_summary")
    profile  = safe_query("SELECT * FROM serving.mv_domain_profile ORDER BY asset_count DESC")
    archiving = safe_query("SELECT * FROM serving.v_archiving_policy_summary")

    total_assets = int(profile["asset_count"].sum()) if not profile.empty else 0
    n_domains    = profile["domain_label"].nunique() if not profile.empty else 0

    # ── KPIs ────────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Assets classifiés", f"{total_assets:,}".replace(",", " "))
    c2.metric("Domaines métier", n_domains)
    if not impact.empty:
        row = impact.iloc[0]
        c3.metric("Patrimoine total", f"{row['total_patrimoine_gb']:.1f} Go")
        c4.metric("Coût annuel actuel", f"${row['current_cost_usd_year']:,.0f}")
        c5.metric(
            "Économie possible",
            f"${row['annual_savings_usd']:,.0f} / an",
            delta=f"réduction de {row['reduction_pct']:.0f}%",
        )

    # ── Bannière ROI ─────────────────────────────────────────────────────────
    if not impact.empty:
        st.success(
            f"**💡 Taux d'économie normalisé : ${row['savings_usd_per_tb_archived_year']:,.0f} / To archivé / an** "
            f"— stockage actif {row['cost_active_usd_per_gb_year']} $/Go/an → froid "
            f"{row['cost_cold_usd_per_gb_year']} $/Go/an · métrique transposable à l'échelle production."
        )

    st.divider()

    # ── Répartition par domaine (donut) + Volume (barres) ────────────────────
    if not profile.empty:
        profile["pct"] = (profile["asset_count"] / profile["asset_count"].sum() * 100).round(1)
        _color_sc = alt.Scale(domain=list(_PAL), range=list(_PAL.values()))

        col_a, col_b = st.columns([1, 2])
        with col_a:
            st.subheader("Répartition par domaine")
            donut = (
                alt.Chart(profile)
                .mark_arc(innerRadius=65, outerRadius=115, stroke="white", strokeWidth=1.5)
                .encode(
                    theta=alt.Theta("asset_count:Q"),
                    color=alt.Color(
                        "domain_label:N",
                        scale=_color_sc,
                        legend=alt.Legend(
                            title=None, orient="bottom", columns=2,
                            labelFontSize=11, symbolSize=120,
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("domain_label:N", title="Domaine"),
                        alt.Tooltip("asset_count:Q",  title="Assets", format=","),
                        alt.Tooltip("pct:Q",          title="%",      format=".1f"),
                    ],
                )
                .properties(height=340)
            )
            st.altair_chart(donut, width='stretch')

        with col_b:
            st.subheader("Volume stocké par domaine (Mo)")
            _bv = alt.Chart(profile).mark_bar(cornerRadiusEnd=3).encode(
                x=alt.X("total_size_mb:Q", title="Volume (Mo)", axis=alt.Axis(format=",")),
                y=alt.Y("domain_label:N", sort="-x", title=None,
                         axis=alt.Axis(labelLimit=260)),
                color=alt.Color("domain_label:N", scale=_color_sc, legend=None),
                tooltip=[
                    alt.Tooltip("domain_label:N",   title="Domaine"),
                    alt.Tooltip("total_size_mb:Q",  title="Volume (Mo)", format=",.0f"),
                    alt.Tooltip("asset_count:Q",    title="Assets",      format=","),
                    alt.Tooltip("pct:Q",            title="% du parc",   format=".1f"),
                ],
            )
            _lv = alt.Chart(profile).mark_text(align="left", dx=4, fontSize=11, color="#444").encode(
                x="total_size_mb:Q",
                y=alt.Y("domain_label:N", sort="-x"),
                text=alt.Text("total_size_mb:Q", format=",.0f"),
            )
            st.altair_chart((_bv + _lv).properties(height=340), width='stretch')

    # ── Synthèse des recommandations d'archivage ─────────────────────────────
    if not archiving.empty:
        st.divider()
        st.subheader("Recommandations d'archivage — synthèse")

        by_strat = (
            archiving.groupby("recommended_strategy", as_index=False)
            .agg(nb_assets=("asset_count", "sum"), volume_mb=("total_size_mb", "sum"))
            .sort_values("nb_assets", ascending=False)
        )
        total_rec = by_strat["nb_assets"].sum()

        metric_cols = st.columns(min(len(by_strat), 4))
        for i, (_, r) in enumerate(by_strat.head(4).iterrows()):
            label = r["recommended_strategy"].replace("_", " ").title()
            vol = (f"{r['volume_mb'] / 1024:.1f} Go"
                   if r["volume_mb"] >= 1024 else f"{r['volume_mb']:.0f} Mo")
            pct_s = f"{r['nb_assets'] / total_rec * 100:.0f}% des assets"
            metric_cols[i].metric(label, f"{int(r['nb_assets']):,}".replace(",", " "),
                                  delta=vol, delta_color="off")

        strat_bars = alt.Chart(by_strat).mark_bar(cornerRadiusEnd=3, color="#4c8cbf").encode(
            x=alt.X("nb_assets:Q", title="Nb d'assets", axis=alt.Axis(format=",")),
            y=alt.Y("recommended_strategy:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=360, labelFontSize=11)),
            tooltip=[
                alt.Tooltip("recommended_strategy:N", title="Stratégie"),
                alt.Tooltip("nb_assets:Q",  title="Assets",      format=","),
                alt.Tooltip("volume_mb:Q",  title="Volume (Mo)", format=",.0f"),
            ],
        )
        strat_lbl = alt.Chart(by_strat).mark_text(
            align="left", dx=4, fontSize=11, color="#444"
        ).encode(
            x="nb_assets:Q",
            y=alt.Y("recommended_strategy:N", sort="-x"),
            text=alt.Text("nb_assets:Q", format=","),
        )
        st.altair_chart(
            (strat_bars + strat_lbl).properties(height=max(200, len(by_strat) * 46)),
            width='stretch',
        )
