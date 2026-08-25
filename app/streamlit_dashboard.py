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
if section == "Vue d'ensemble":
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


# ===========================================================================
# 2. DOMAINES
# ===========================================================================
elif section == "Recherche":
    page_header(
        "Recherche de table",
        "Retrouvez une table par son nom et consultez sa fiche complète",
        "🔎",
    )

    query = st.text_input(
        "Nom de la table (ou fragment)",
        placeholder="ex. PS_JRNL, EMPLOYEES, VOUCHER…",
    ).strip()
    fc1, fc2 = st.columns(2)
    bands = fc1.multiselect(
        "Bande de confiance", ["high", "medium", "low"], default=[],
        help="Filtrer par fiabilité de la classification",
    )
    review_choice = fc2.selectbox("Statut de revue", ["(tous)", "À réviser", "Validé"])

    if not query and not bands and review_choice == "(tous)":
        st.info(
            "Saisissez un nom de table **ou** utilisez les filtres "
            "(ex. « à réviser » pour lister toutes les tables incertaines)."
        )
        st.stop()

    _where = ["s.run_id = (SELECT MAX(run_id) FROM processed.dim_asset)"]
    _params: dict = {}
    if query:
        _where.append("s.technical_name ILIKE :pattern")
        _params["pattern"] = f"%{query}%"
    _safe_bands = [b for b in bands if b in ("high", "medium", "low")]
    if _safe_bands:
        _where.append("s.confidence_band IN (" + ",".join(f"'{b}'" for b in _safe_bands) + ")")
    if review_choice == "À réviser":
        _where.append("s.review_required = true")
    elif review_choice == "Validé":
        _where.append("s.review_required = false")

    _SEARCH_SQL = f"""
        SELECT s.technical_name,
               s.business_domain_predicted AS domaine,
               s.business_domain_alt       AS domaine_alt,
               s.confidence, s.confidence_band,
               s.review_required, s.review_reason,
               inv.schema_name, inv.description,
               inv.size_mb, inv.column_count, inv.row_count,
               inv.archival_candidate_score, inv.roi_score
        FROM serving.v_asset_business_domain_scored s
        JOIN serving.mv_asset_inventory inv
          ON inv.asset_id = s.asset_id AND inv.run_id = s.run_id
        WHERE {" AND ".join(_where)}
        ORDER BY s.technical_name
        LIMIT 200
    """
    res = safe_query_params(_SEARCH_SQL, _params) if _params else safe_query(_SEARCH_SQL)
    if res.empty:
        st.warning("Aucune table ne correspond à ces critères.")
        st.stop()

    st.caption(
        f"{len(res)} table(s) trouvée(s)"
        + (" — affichage limité aux 200 premières" if len(res) == 200 else "")
    )

    picked = st.selectbox("Sélectionner une table pour voir sa fiche", res["technical_name"].tolist())
    row = res[res["technical_name"] == picked].iloc[0]
    band = str(row["confidence_band"])
    band_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(band, "⚪")

    st.subheader(f"📄 {picked}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Domaine prédit", str(row["domaine"]))
    c2.metric("Confiance", f"{float(row['confidence'] or 0):.0%}", help=f"Bande : {band}")
    c3.metric("Taille (Mo)", f"{float(row['size_mb'] or 0):.2f}")
    c4.metric("Colonnes", int(row["column_count"] or 0))

    if bool(row["review_required"]):
        st.error(f"⚠️ À réviser avant toute décision — {row['review_reason'] or 'confiance insuffisante'}")
    else:
        st.success(f"{band_icon} Classification fiable ({band}) — exploitable")

    with st.expander("Détails complets de la table"):
        st.write({
            "Domaine alternatif":       row["domaine_alt"],
            "Schéma":                   row["schema_name"],
            "Description":              row["description"] or "(aucune)",
            "Nombre de lignes":         int(row["row_count"] or 0),
            "Score d'archivabilité":    round(float(row["archival_candidate_score"] or 0), 1),
            "Score ROI":                round(float(row["roi_score"] or 0), 1),
        })

    st.subheader("Tous les résultats")
    st.dataframe(res, width="stretch", hide_index=True)
    st.download_button(
        "⬇️ Télécharger les résultats (CSV)",
        res.to_csv(index=False).encode("utf-8"),
        file_name=f"recherche_{query}.csv",
        mime="text/csv",
        width="stretch",
    )


elif section == "Domaines":
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


# ===========================================================================
# 3. CLÉS MÉTIER PARTAGÉES ENTRE DOMAINES (vocabulaire, pas des FK)
# ===========================================================================
elif section == "Clés partagées":
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


# ===========================================================================
# 4. ARCHIVAGE
# ===========================================================================
elif section == "Archivage":
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


# ===========================================================================
# 5. COÛTS & ROI
# ===========================================================================
elif section == "Coûts & ROI":
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


# ===========================================================================
# 6. PIPELINES — Centre de contrôle
# ===========================================================================
elif section == "🚀 Pipelines":
    page_header(
        "Centre de contrôle des pipelines",
        "Lance les traitements sans terminal — logs en direct",
        "🚀",
    )

    st.subheader("⚡ Régénération analytics (rapide & sûr)")
    st.write(
        "Recalcule la couche serving à partir des données **déjà chargées** "
        "(run courant). Ne nécessite ni Oracle ni VPN — quelques secondes."
    )
    c = st.columns(2)
    if c[0].button("📊 Publier la couche serving (MVs + domaine + archivage + coûts)", width="stretch"):
        run_command("Publication serving", "src.prefect.flows.flow_publish_serving")
    if c[1].button("📥 Exporter l'Excel (13 feuilles)", width="stretch"):
        run_command("Export Excel", "src.export.export_domain_model")
    c2 = st.columns(3)
    if c2[0].button("🏷️ Modèle de domaine", width="stretch"):
        run_command("Modèle de domaine", "src.transform.build_serving_domain_model")
    if c2[1].button("📦 Règles d'archivage", width="stretch"):
        run_command("Règles d'archivage", "src.transform.build_archiving_rules")
    if c2[2].button("💰 Analyse coût/ROI", width="stretch"):
        run_command("Analyse coût/ROI", "src.transform.build_cost_analysis")

    st.divider()
    st.subheader("🗄️ Pipeline complet (lourd — VPN Oracle requis)")
    st.warning(
        "L'extraction interroge Oracle (~87 000 records), "
        "reconstruit toute la couche processed + le scoring ML, publie la couche "
        "serving, et crée un **nouveau run_id**. Durée : plusieurs minutes. "
        "À n'utiliser que connecté au VPN."
    )
    if st.button("Initialiser la base (schémas + tables)"):
        run_command("Initialisation base", "src.prefect.flows.flow_init_db")

    confirm = st.checkbox("Je confirme vouloir lancer une extraction (VPN Oracle requis)")
    if st.button("🚀 Pipeline complet (Oracle)", disabled=not confirm, type="primary", width="stretch"):
        run_command("Pipeline complet Oracle", "src.prefect.flows.flow_oracle_only")

    st.divider()
    st.subheader("🕑 Historique des exécutions")
    runs = safe_query(
        "SELECT id AS run_id, flow_name, run_type, status, started_at, ended_at "
        "FROM admin.pipeline_run ORDER BY id DESC LIMIT 15"
    )
    st.dataframe(runs, width="stretch", hide_index=True)


# ===========================================================================
# 7. PARAMÈTRES — édition coûts & ROI (what-if)
# ===========================================================================
elif section == "⚙️ Paramètres":
    page_header(
        "Paramètres de coût & ROI",
        "Scénarios what-if sur serving.dim_cost_params, recalcul en un clic",
        "⚙️",
    )

    from src.transform.build_cost_analysis import COST_PARAMS as DEFAULT_COST_PARAMS
    from src.transform.build_cost_analysis import build_cost_analysis

    defaults = {p["name"]: float(p["value"]) for p in DEFAULT_COST_PARAMS}
    current = safe_query(
        "SELECT param_name, param_value, unit, description "
        "FROM serving.dim_cost_params ORDER BY param_id"
    )
    cur_map = (
        {r["param_name"]: float(r["param_value"]) for _, r in current.iterrows()}
        if not current.empty
        else {}
    )

    labels = {
        "storage_cost_per_gb_per_year": "Coût stockage actif ($/Go/an)",
        "cold_storage_cost_per_gb_year": "Coût stockage froid ($/Go/an)",
        "compression_ratio": "Ratio compression (0–1, taille résiduelle)",
        "data_growth_rate_pct_per_year": "Croissance annuelle (%)",
        "implementation_cost_one_shot": "Coût d'implémentation ($)",
    }

    def _save_params(values: dict[str, float], reset: bool) -> None:
        try:
            eng = get_engine()
            with eng.begin() as conn:
                for name, val in values.items():
                    conn.execute(
                        text(
                            "UPDATE serving.dim_cost_params "
                            "SET param_value = :v, updated_at = now() WHERE param_name = :n"
                        ),
                        {"v": float(val), "n": name},
                    )
            # reset=True -> recalc canonique (réécrit les défauts) ; sinon préserve le custom
            res = build_cost_analysis(upsert_defaults=reset)
            run_query.clear()
            st.success(
                f"{'Réinitialisé' if reset else 'Enregistré'} & recalculé — "
                f"patrimoine {res['total_gb']} Go, "
                f"économie nette {res['projection_years']} ans (médiane) = "
                f"{res['net_savings_p50_usd']} $ "
                f"[P10 {res['net_savings_p10_usd']} – P90 {res['net_savings_p90_usd']}], "
                f"P(rentable) = {res['breakeven_probability']}, "
                f"croissance {res['growth_mean_pct']}%/an ({res['growth_source']})."
            )
        except Exception as exc:
            st.error(f"Échec : {exc}")

    with st.form("cost_params_form"):
        new_vals: dict[str, float] = {}
        for name, label in labels.items():
            new_vals[name] = st.number_input(
                label,
                value=float(cur_map.get(name, defaults.get(name, 0.0))),
                step=0.01,
                format="%.4f",
                key=f"param_{name}",
            )
        submitted = st.form_submit_button("💾 Enregistrer & recalculer", type="primary")
    if submitted:
        _save_params(new_vals, reset=False)

    if st.button("↩️ Réinitialiser aux valeurs par défaut"):
        _save_params(defaults, reset=True)
        st.rerun()

    st.info(
        "Note : un **pipeline complet** ou une **publication serving** réapplique "
        "les valeurs par défaut (reconstruction canonique). Les scénarios « what-if » "
        "persistent jusqu'à la prochaine reconstruction."
    )

    st.divider()
    st.subheader("Valeurs par défaut (référence)")
    st.dataframe(
        pd.DataFrame(
            [{"param_name": k, "défaut": v, "libellé": labels.get(k, "")} for k, v in defaults.items()]
        ),
        width="stretch",
        hide_index=True,
    )


# ===========================================================================
# 8. CONSOLE SQL
# ===========================================================================
elif section == "💾 Console SQL":
    import time as _time

    page_header(
        "Console SQL",
        "Interroge Oracle EP92U038 (source) ou PostgreSQL (cible) — lecture seule",
        "💾",
    )

    target = st.radio(
        "Base de données",
        ["🏛️ Oracle EP92U038  (VPN requis)", "🐘 PostgreSQL pfe_data_ia"],
        horizontal=True,
    )
    is_oracle = target.startswith("🏛️")

    # ── Requêtes rapides ────────────────────────────────────────────────
    with st.expander("📋 Requêtes rapides — cliquez pour copier", expanded=False):
        if is_oracle:
            st.markdown("**🏗️ Architecture de la base**")

            st.code("""-- Schémas (owners) et nombre de tables
SELECT owner, COUNT(*) AS nb_tables, ROUND(SUM(NVL(num_rows,0))) AS total_lignes
FROM ALL_TABLES
GROUP BY owner
ORDER BY nb_tables DESC""", language="sql")

            st.code("""-- Types d'objets Oracle dans SYSADM (tables, vues, index, LOB…)
SELECT object_type, COUNT(*) AS nb
FROM ALL_OBJECTS
WHERE owner = 'SYSADM'
GROUP BY object_type ORDER BY nb DESC""", language="sql")

            st.code("""-- Toutes les tables d'un schéma (triées par volume)
SELECT table_name, num_rows,
       ROUND(blocks * 8192 / 1024 / 1024, 1) AS size_mb
FROM ALL_TABLES
WHERE owner = 'SYSADM'
ORDER BY num_rows DESC NULLS LAST""", language="sql")

            st.code("""-- Tablespaces visibles (espaces de stockage)
SELECT tablespace_name, status, contents, extent_management
FROM USER_TABLESPACES
ORDER BY tablespace_name""", language="sql")

            st.code("""-- Index d'une table (remplacer PS_JRNL_LN)
SELECT index_name, uniqueness, index_type
FROM ALL_INDEXES
WHERE owner = 'SYSADM' AND table_name = 'PS_JRNL_LN'
ORDER BY index_name""", language="sql")

            st.code("""-- Contraintes d'une table (PK/UK/Check ; FK quasi inexistantes en PeopleSoft)
SELECT constraint_name, constraint_type, status
FROM ALL_CONSTRAINTS
WHERE owner = 'SYSADM' AND table_name = 'PS_JRNL_LN'
ORDER BY constraint_type""", language="sql")

            st.code("""-- Version PeopleTools & état de l'instance
SELECT toolsrel, ownerid, lastrefreshdttm, unicode_enabled
FROM SYSADM.PSSTATUS""", language="sql")

            st.divider()
            st.markdown("**📊 Exploration métier**")

            st.code("""-- Top 10 tables les plus volumineuses (Oracle)
SELECT table_name, num_rows,
       ROUND(blocks * 8192 / 1024 / 1024, 1) AS size_mb,
       last_analyzed
FROM ALL_TABLES
WHERE owner = 'SYSADM' AND num_rows IS NOT NULL
ORDER BY num_rows DESC FETCH FIRST 10 ROWS ONLY""", language="sql")

            st.code("""-- Répartition des types de records + matérialisation Oracle
SELECT rectype,
       CASE rectype
           WHEN 0 THEN 'SQL Table'
           WHEN 1 THEN 'SQL View'
           WHEN 2 THEN 'Derived/Work Record'
           WHEN 3 THEN 'SubRecord'
           WHEN 5 THEN 'Dynamic View'
           WHEN 6 THEN 'Query View'
           WHEN 7 THEN 'Temporary Table'
           ELSE 'Autre'
       END AS signification,
       COUNT(*) AS nb,
       CASE rectype
           WHEN 0 THEN 'Oui'
           WHEN 7 THEN 'Oui (transitoire)'
           ELSE 'Non'
       END AS materialise_oracle
FROM SYSADM.PSRECDEFN
WHERE recname <> 'PSDUMMY'
GROUP BY rectype ORDER BY nb DESC""", language="sql")

            st.code("""-- Tables physiques rectype=0 réellement présentes dans ALL_TABLES
SELECT
    COUNT(*) AS total_rectype0,
    SUM(CASE WHEN t.table_name IS NOT NULL THEN 1 ELSE 0 END) AS avec_table_physique,
    SUM(CASE WHEN t.table_name IS NULL     THEN 1 ELSE 0 END) AS sans_table_physique
FROM SYSADM.PSRECDEFN r
LEFT JOIN ALL_TABLES t
       ON t.owner = 'SYSADM'
      AND t.table_name = CASE
            WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
            THEN TRIM(r.sqltablename)
            ELSE 'PS_' || r.recname
          END
WHERE r.recname <> 'PSDUMMY' AND r.rectype = 0""", language="sql")

            st.code("""-- Colonnes d'une table (remplacer PS_JRNL_LN)
SELECT column_name, data_type, data_length, nullable
FROM ALL_TAB_COLUMNS
WHERE owner = 'SYSADM' AND table_name = 'PS_JRNL_LN'
ORDER BY column_id""", language="sql")

            st.code("""-- Champs les plus partagés entre records
SELECT f.fieldname, COUNT(rf.recname) AS nb_records
FROM SYSADM.PSDBFIELD f
JOIN SYSADM.PSRECFIELDDB rf ON rf.fieldname = f.fieldname
GROUP BY f.fieldname
ORDER BY nb_records DESC FETCH FIRST 20 ROWS ONLY""", language="sql")

            st.code("""-- Aperçu données réelles d'une table métier
SELECT * FROM SYSADM.PS_JRNL_LN FETCH FIRST 10 ROWS ONLY""", language="sql")
        else:
            st.code("""-- Assets par domaine (couche serving)
SELECT domain_label, asset_count, total_size_mb
FROM serving.mv_domain_profile
ORDER BY asset_count DESC""", language="sql")

            st.code("""-- Top 20 recommandations d'archivage par taille
SELECT technical_name, domain_label, recommended_strategy,
       ROUND(size_mb, 1) AS size_mb, age_band, sensitivity_level
FROM serving.mv_archiving_recommendation
WHERE size_mb > 0
ORDER BY size_mb DESC LIMIT 20""", language="sql")

            st.code("""-- Schémas et tables disponibles
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema','pg_catalog')
ORDER BY table_schema, table_name""", language="sql")

            st.code("""-- Historique des runs pipeline
SELECT id, flow_name, run_type, status, started_at, ended_at
FROM admin.pipeline_run ORDER BY id DESC LIMIT 10""", language="sql")

            st.code("""-- Profil coût par domaine
SELECT domain_label, current_cost_usd_year, cost_share_pct, cost_rank
FROM serving.v_cost_by_domain ORDER BY cost_rank""", language="sql")

    # ── Requêtes sauvegardées (persistées) ──────────────────────────────
    _db_key = "oracle" if is_oracle else "postgres"
    sql_key = f"console_sql_{'ora' if is_oracle else 'pg'}"
    default_sql = (
        "SELECT 1 AS ping FROM DUAL"
        if is_oracle
        else "SELECT current_database(), current_timestamp"
    )
    if sql_key not in st.session_state:
        st.session_state[sql_key] = default_sql

    _saved = load_saved_queries()
    _bucket = _saved.get(_db_key, {})

    with st.expander(f"💾 Requêtes sauvegardées ({len(_bucket)})", expanded=bool(_bucket)):
        if _bucket:
            lc1, lc2, lc3 = st.columns([5, 1.3, 1.3])
            picked = lc1.selectbox(
                "Charger une requête", ["—"] + sorted(_bucket),
                key="console_saved_pick", label_visibility="collapsed",
            )
            # NB : on modifie session_state[sql_key] AVANT la création du text_area
            if lc2.button("📂 Charger", width='stretch') and picked != "—":
                st.session_state[sql_key] = _bucket[picked]
            if lc3.button("🗑️ Supprimer", width='stretch') and picked != "—":
                _saved.get(_db_key, {}).pop(picked, None)
                write_saved_queries(_saved)
                st.success(f"Requête « {picked} » supprimée.")
                st.rerun()
        else:
            st.caption("Aucune requête sauvegardée pour cette base. "
                       "Écris une requête ci-dessous puis sauvegarde-la.")

    # ── Éditeur ─────────────────────────────────────────────────────────
    sql_input = st.text_area(
        "Requête SQL",
        height=220,
        key=sql_key,
        placeholder="SELECT ...",
    )

    # ── Sauvegarde de la requête courante ───────────────────────────────
    sv1, sv2 = st.columns([5, 2])
    save_name = sv1.text_input(
        "Nom pour sauvegarder la requête courante",
        key="console_save_name", placeholder="ex. Top tables volumineuses",
        label_visibility="collapsed",
    )
    if sv2.button("💾 Sauvegarder", width='stretch'):
        _name = save_name.strip()
        if not _name:
            st.warning("Donne un nom à la requête avant de sauvegarder.")
        elif not sql_input.strip():
            st.warning("La requête est vide.")
        else:
            _saved.setdefault(_db_key, {})[_name] = sql_input
            write_saved_queries(_saved)
            st.success(f"Requête « {_name} » sauvegardée pour {_db_key}.")
            st.rerun()

    c1, c2, c3 = st.columns([2, 2, 6])
    max_rows = c1.number_input("Lignes max", min_value=10, max_value=5000,
                                value=500, step=50, key="console_max_rows")
    run_btn = c2.button("▶️ Exécuter", type="primary", width='stretch')

    if run_btn:
        sql_clean = sql_input.strip().rstrip(";")

        # Sécurité : lecture seule — autorise SELECT et WITH…SELECT (CTE),
        # rejette tout mot-clé d'écriture/DDL présent comme token.
        import re as _re
        _tokens = set(_re.findall(r"[A-Za-z_]+", sql_clean.upper()))
        _first = sql_clean.lstrip("( \t\n").upper().split()[0] if sql_clean.split() else ""
        _forbidden = {
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
            "GRANT", "REVOKE", "MERGE", "CALL", "EXEC", "EXECUTE", "COMMIT",
            "ROLLBACK", "REPLACE", "UPSERT",
        }
        if _first not in {"SELECT", "WITH"}:
            st.error("❌ Seules les requêtes **SELECT** (ou `WITH … SELECT`) sont autorisées (lecture seule).")
            st.stop()
        _hit = _tokens & _forbidden
        if _hit:
            st.error(f"❌ Mot-clé d'écriture interdit détecté : **{', '.join(sorted(_hit))}**. "
                     "Console en lecture seule.")
            st.stop()

        t0 = _time.time()

        if is_oracle:
            try:
                from src.connectors.oracle_client import OracleClient
                with st.spinner("Connexion Oracle (VPN requis)…"):
                    _ora = OracleClient(settings=get_settings())
                with st.spinner("Exécution en cours…"):
                    rows = _ora.fetch_all(sql_clean)
                elapsed = _time.time() - t0
                df_res = pd.DataFrame(rows) if rows else pd.DataFrame()
                if len(df_res) > max_rows:
                    st.warning(f"⚠️ Résultat tronqué à {int(max_rows)} lignes "
                               f"({len(df_res)} retournées).")
                    df_res = df_res.head(int(max_rows))
                st.success(f"✅ {len(df_res)} ligne(s) — {elapsed:.2f} s")
                if not df_res.empty:
                    st.dataframe(df_res, width='stretch', hide_index=True)
                    st.download_button(
                        "⬇️ Télécharger CSV",
                        df_res.to_csv(index=False).encode("utf-8"),
                        file_name="oracle_result.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("Requête exécutée — aucune ligne retournée.")
            except Exception as exc:
                elapsed = _time.time() - t0
                st.error(f"❌ Erreur Oracle ({elapsed:.1f} s) : {exc}")
                _msg = str(exc)
                if "ORA-00942" in _msg:
                    st.info("💡 **Table ou vue inexistante.** Qualifie le schéma "
                            "(`SYSADM.PS_...`) et vérifie l'orthographe. "
                            "Ex. `SELECT * FROM SYSADM.PS_JRNL_LN FETCH FIRST 10 ROWS ONLY`.")
                elif "ORA-00904" in _msg:
                    st.info("💡 **Nom de colonne invalide.** Vérifie les colonnes de la table "
                            "avec `SELECT column_name FROM ALL_TAB_COLUMNS WHERE table_name='...'`.")
                elif "ORA-00933" in _msg or "ORA-00923" in _msg or "ORA-00936" in _msg:
                    st.info("💡 **Syntaxe SQL incorrecte.** En Oracle, la limite s'écrit "
                            "`FETCH FIRST n ROWS ONLY` (pas `LIMIT`), et il faut un nom de table "
                            "après `FROM`. Ex. `SELECT * FROM SYSADM.PSRECDEFN FETCH FIRST 10 ROWS ONLY`.")
                else:
                    st.info("💡 Vérifie que le VPN est actif et que l'instance Oracle "
                            "`192.168.11.111:1521/EP92U038` est joignable.")
        else:
            try:
                with st.spinner("Exécution PostgreSQL…"):
                    with get_engine().connect() as _conn:
                        df_res = pd.read_sql(text(sql_clean), _conn)
                elapsed = _time.time() - t0
                if len(df_res) > max_rows:
                    st.warning(f"⚠️ Résultat tronqué à {int(max_rows)} lignes "
                               f"({len(df_res)} retournées).")
                    df_res = df_res.head(int(max_rows))
                st.success(f"✅ {len(df_res)} ligne(s) — {elapsed:.2f} s")
                if not df_res.empty:
                    st.dataframe(df_res, width='stretch', hide_index=True)
                    st.download_button(
                        "⬇️ Télécharger CSV",
                        df_res.to_csv(index=False).encode("utf-8"),
                        file_name="postgres_result.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("Requête exécutée — aucune ligne retournée.")
            except Exception as exc:
                elapsed = _time.time() - t0
                st.error(f"❌ Erreur PostgreSQL ({elapsed:.1f} s) : {exc}")
                st.info("💡 Vérifiez que Docker / PostgreSQL est démarré.")


# ===========================================================================
# 9. TEST DU MODÈLE
# ===========================================================================
elif section == "🤖 Test du modèle":
    page_header(
        "Test du classifieur XLM-R v3",
        "Saisis les métadonnées d'une table et visualise la prédiction du domaine",
        "🤖",
    )
    st.caption(
        "XLM-RoBERTa v3 — ECE 0.011, 50 epochs, feature gating + Focal Loss."
    )

    _REGULATED = {"Finance & Contrôle", "RH", "Achats & Fournisseurs", "Ventes & Clients"}

    # ── Exemples prédéfinis ───────────────────────────────────────────────
    _PRESETS: dict[str, dict] = {
        "— Personnalisé —": {},
        "PS_VENDOR_ADDR — Achats": {
            "technical_name": "PS_VENDOR_ADDR",
            "source_ref": "AP",
            "column_names": "vendor_id setid address1 address2 city state postal country",
            "column_semantics": "VENDOR_ID:reference_identifier|ADDRESS1:postal_location|CITY:postal_location",
            "field_count": 12, "numeric_field_count": 2, "row_count": 5000, "size_mb": 1.2,
        },
        "PS_GL_ACCOUNT — Finance": {
            "technical_name": "PS_GL_ACCOUNT",
            "source_ref": "GL",
            "column_names": "account ledger amount currency_cd fiscal_year accounting_dt",
            "column_semantics": "ACCOUNT:reference_identifier|AMOUNT:financial_amount|CURRENCY_CD:classification",
            "field_count": 18, "numeric_field_count": 8, "row_count": 250000, "size_mb": 40.0,
        },
        "PS_EMPLOYEES — RH": {
            "technical_name": "PS_EMPLOYEES",
            "source_ref": "HR",
            "column_names": "emplid name job_code deptid hire_dt salary_admin_plan grade step",
            "column_semantics": "EMPLID:person_identifier|NAME:person_full_name|JOB_CODE:classification",
            "field_count": 24, "numeric_field_count": 4, "row_count": 8500, "size_mb": 3.1,
        },
        "PSROLEDEFN — IT": {
            "technical_name": "PSROLEDEFN",
            "source_ref": "PSROLE",
            "column_names": "rolename descr dynamic_role role_type can_exceed query_access",
            "column_semantics": "ROLENAME:user_identifier|ROLE_TYPE:classification",
            "field_count": 8, "numeric_field_count": 1, "row_count": 320, "size_mb": 0.05,
        },
        "PS_DEMAND_INF — Supply Chain": {
            "technical_name": "PS_DEMAND_INF",
            "source_ref": "IN",
            "column_names": "business_unit inv_item_id demand_source demand_type qty_requested ship_date",
            "column_semantics": "INV_ITEM_ID:reference_identifier|QTY_REQUESTED:quantity|SHIP_DATE:date_or_timestamp",
            "field_count": 16, "numeric_field_count": 5, "row_count": 42000, "size_mb": 8.5,
        },
    }

    preset_name = st.selectbox("Exemple rapide", list(_PRESETS), key="pred__preset")
    preset = _PRESETS[preset_name]

    # ── Formulaire (mode inclus pour éviter les reruns parasites) ─────────
    # BUG FIX: clés suffixées par preset_name → Streamlit crée un nouveau widget
    # à chaque changement de preset, forçant la réinitialisation via value=.
    # BUG FIX: le radio mode est DANS le formulaire pour que changer le mode
    # ne déclenche pas un rerun qui efface les résultats affichés.
    _pk = preset_name  # suffixe de clé — change quand le preset change
    with st.form("predict_form"):
        col_id, col_vol = st.columns([3, 2])

        with col_id:
            st.subheader("Identité de la table")
            technical_name = st.text_input(
                "Nom technique *",
                value=str(preset.get("technical_name", "")),
                placeholder="ex. PS_VENDOR_ADDR",
                key=f"pred__technical_name__{_pk}",
            )
            source_ref = st.text_input(
                "Module / source_ref *",
                value=str(preset.get("source_ref", "")),
                placeholder="ex. AP, HR, GL, PSROLE, IN…",
                key=f"pred__source_ref__{_pk}",
            )
            column_names = st.text_area(
                "Noms de colonnes *  (séparés par des espaces)",
                value=str(preset.get("column_names", "")),
                height=90,
                placeholder="vendor_id setid address1 city state postal country…",
                key=f"pred__column_names__{_pk}",
            )

        with col_vol:
            st.subheader("Volumétrie")
            field_count = st.number_input(
                "Nombre total de champs", min_value=0,
                value=int(preset.get("field_count", 0)), step=1,
                key=f"pred__field_count__{_pk}",
            )
            numeric_field_count = st.number_input(
                "dont champs numériques", min_value=0,
                value=int(preset.get("numeric_field_count", 0)), step=1,
                key=f"pred__numeric_fc__{_pk}",
            )
            row_count = st.number_input(
                "Nombre de lignes", min_value=0,
                value=int(preset.get("row_count", 0)), step=500,
                key=f"pred__row_count__{_pk}",
            )
            size_mb = st.number_input(
                "Taille (Mo)", min_value=0.0,
                value=float(preset.get("size_mb", 0.0)), step=0.1, format="%.2f",
                key=f"pred__size_mb__{_pk}",
            )

        with st.expander("Sémantique & types de colonnes (optionnel — enrichit la prédiction)"):
            column_semantics = st.text_area(
                "Sémantique   COL:label|COL:label…",
                value=str(preset.get("column_semantics", "")),
                height=80,
                placeholder="VENDOR_ID:reference_identifier|ADDRESS1:postal_location",
                key=f"pred__col_sem__{_pk}",
            )
            col_type_sig = st.text_input(
                "Signature de types   (column_type_signature_text)",
                value=str(preset.get("column_type_signature_text", "")),
                placeholder="VARCHAR:5|NUMBER:3|DATE:2",
                key=f"pred__col_types__{_pk}",
            )

        st.divider()
        mode_label = st.radio(
            "Mode de prédiction",
            [
                "Équilibré  (macro-F1 global)",
                "SLA-strict  (rappel ≥ 0.90 sur les domaines réglementés)",
            ],
            horizontal=True,
            key="pred__mode",
        )

        submitted = st.form_submit_button("🔍 Prédire", type="primary", width='stretch')

    apply_offsets: bool = mode_label.startswith("SLA")

    # ── Résultats ─────────────────────────────────────────────────────────
    if submitted:
        if not technical_name.strip() or not column_names.strip():
            st.error("Le nom technique et les noms de colonnes sont obligatoires.")
        else:
            try:
                clf = _load_classifier(apply_offsets)
                row_input = {
                    "technical_name":            technical_name.strip(),
                    "source_ref":                source_ref.strip(),
                    "column_names":              column_names.strip(),
                    "column_semantics":          column_semantics.strip(),
                    "column_type_signature_text": col_type_sig.strip(),
                    "field_count":               field_count,
                    "numeric_field_count":       numeric_field_count,
                    "row_count":                 row_count,
                    "size_mb":                   size_mb,
                }
                result = clf.predict(row_input)

                label      = result["label"]
                confidence = result["confidence"]
                review     = result["review_required"]
                probs      = result["probs"]
                color      = _PAL.get(label, "#555")
                conf_pct   = confidence * 100

                st.divider()
                st.subheader("Résultat")

                m1, m2, m3 = st.columns([3, 1, 1])
                with m1:
                    st.markdown(
                        f"<div style='background:{color};padding:14px 20px;border-radius:10px;"
                        f"color:white;font-size:1.25em;font-weight:600;letter-spacing:.02em'>"
                        f"{label}</div>",
                        unsafe_allow_html=True,
                    )
                m2.metric("Confiance", f"{conf_pct:.1f} %")
                m3.metric("Mode", "SLA-strict" if apply_offsets else "Équilibré")

                if review:
                    st.warning(
                        "**Revue humaine requise** — domaine réglementé avec confiance < 60 %. "
                        "En production, cet asset serait orienté vers la queue d'approbation "
                        "avec statut **A_EVALUER**."
                    )
                elif label in _REGULATED and confidence < 0.60:
                    st.warning("Domaine réglementé — confiance faible, vérification recommandée.")
                elif confidence >= 0.80:
                    st.success("Confiance élevée — prédiction fiable.")
                elif confidence >= 0.60:
                    st.info("Confiance modérée — vérification conseillée pour les assets critiques.")
                else:
                    st.warning("Confiance faible — prédiction incertaine.")

                # Barre de confiance visuelle
                st.progress(confidence, text=f"Score de confiance : {conf_pct:.1f} %")

                st.subheader("Distribution des probabilités par domaine")
                prob_df = (
                    pd.DataFrame.from_dict(probs, orient="index", columns=["probabilité"])
                    .reset_index()
                    .rename(columns={"index": "domaine"})
                    .sort_values("probabilité", ascending=True)
                )

                chart = (
                    alt.Chart(prob_df)
                    .mark_bar()
                    .encode(
                        x=alt.X(
                            "probabilité:Q",
                            scale=alt.Scale(domain=[0.0, 1.0]),
                            axis=alt.Axis(format=".0%", title="Probabilité calibrée"),
                        ),
                        y=alt.Y("domaine:N", sort="-x", title=None),
                        color=alt.Color(
                            "domaine:N",
                            scale=alt.Scale(
                                domain=list(_PAL),
                                range=list(_PAL.values()),
                            ),
                            legend=None,
                        ),
                        tooltip=[
                            alt.Tooltip("domaine:N",       title="Domaine"),
                            alt.Tooltip("probabilité:Q",   title="Probabilité", format=".3f"),
                        ],
                    )
                    .properties(height=230)
                )
                st.altair_chart(chart, width='stretch')

                # Détail JSON
                with st.expander("Détail complet (JSON)"):
                    st.json(result)

            except FileNotFoundError as exc:
                st.error(f"Modèle introuvable : {exc}")
                st.info(
                    "Vérifiez que le dossier `artifacts/xlmr_v3/artifacts/` contient "
                    "`model.onnx`, `class_labels.json`, `scaler_params.npz`, "
                    "`temperatures.json` et `tokenizer/`."
                )
            except Exception as exc:
                st.error(f"Erreur lors de la prédiction : {exc}")
                st.exception(exc)

    else:
        st.info(
            "Remplissez le formulaire ci-dessus et cliquez sur **Prédire** pour voir "
            "le domaine métier prédit par le modèle XLM-R v3 avec sa distribution "
            "de probabilités calibrée."
        )

