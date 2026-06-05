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
)


# ---------------------------------------------------------------------------
# Accès base (lecture seule, mis en cache)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    return create_engine(get_settings().postgresql_url, pool_pre_ping=True)


@st.cache_data(ttl=300)
def run_query(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


def safe_query(sql: str) -> pd.DataFrame:
    try:
        return run_query(sql)
    except Exception as exc:  # base indisponible / vue absente
        st.warning(f"Requête indisponible : {exc}")
        return pd.DataFrame()


def run_command(label: str, module: str, extra_args: list[str] | None = None) -> None:
    """Exécute `python -m <module>` en sous-processus, logs streamés dans l'UI."""
    cmd = [sys.executable, "-m", module, *(extra_args or [])]
    with st.status(f"{label} — en cours…", expanded=True) as status:
        placeholder = st.empty()
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            status.update(label=f"{label} — échec de lancement", state="error")
            st.error(str(exc))
            return

        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))
            placeholder.code("\n".join(lines[-300:]), language="log")
        proc.wait()

        if proc.returncode == 0:
            status.update(label=f"{label} — terminé ✅", state="complete")
            run_query.clear()  # invalider le cache pour refléter les nouvelles données
        else:
            status.update(label=f"{label} — échec (code {proc.returncode}) ❌", state="error")


# ---------------------------------------------------------------------------
# Barre latérale
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Gouvernance des données")
st.sidebar.caption("Oracle PeopleSoft EP92U038 — couche serving")

run_df = safe_query("SELECT MAX(run_id) AS run_id FROM processed.dim_asset")
run_id = int(run_df["run_id"].iloc[0]) if not run_df.empty and run_df["run_id"].iloc[0] is not None else 0
st.sidebar.metric("Run actif", f"#{run_id}")

section = st.sidebar.radio(
    "Navigation",
    [
        "Vue d'ensemble",
        "Domaines",
        "Clés partagées",
        "Archivage",
        "Coûts & ROI",
        "🚀 Pipelines",
        "⚙️ Paramètres",
    ],
)
st.sidebar.button("🔄 Rafraîchir les données", on_click=st.cache_data.clear)


# ===========================================================================
# 1. VUE D'ENSEMBLE
# ===========================================================================
if section == "Vue d'ensemble":
    st.title("Vue d'ensemble du patrimoine de données")

    impact = safe_query("SELECT * FROM serving.v_storage_impact_summary")
    profile = safe_query("SELECT * FROM serving.mv_domain_profile ORDER BY asset_count DESC")

    total_assets = int(profile["asset_count"].sum()) if not profile.empty else 0
    n_domains = profile["domain_label"].nunique() if not profile.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Assets classifiés", f"{total_assets:,}".replace(",", " "))
    c2.metric("Domaines métier", n_domains)
    if not impact.empty:
        row = impact.iloc[0]
        c3.metric("Patrimoine", f"{row['total_patrimoine_gb']:.1f} Go")
        c4.metric("Coût actuel", f"${row['current_cost_usd_year']:.2f}/an")
        c5.metric("Économie possible", f"${row['annual_savings_usd']:.2f}/an",
                  delta=f"-{row['reduction_pct']:.0f}%")

    if not impact.empty:
        row = impact.iloc[0]
        st.info(
            f"**Taux d'économie normalisé : ${row['savings_usd_per_tb_archived_year']:.0f} / To archivé / an** "
            f"(actif {row['cost_active_usd_per_gb_year']} $/Go/an → froid {row['cost_cold_usd_per_gb_year']} $/Go/an). "
            "Métrique transposable à l'échelle production."
        )

    if not profile.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Assets par domaine")
            st.bar_chart(profile.set_index("domain_label")["asset_count"], horizontal=True)
        with col_b:
            st.subheader("Volume par domaine (Mo)")
            st.bar_chart(profile.set_index("domain_label")["total_size_mb"], horizontal=True)


# ===========================================================================
# 2. DOMAINES
# ===========================================================================
elif section == "Domaines":
    st.title("Profil par domaine métier")

    profile = safe_query("SELECT * FROM serving.mv_domain_profile ORDER BY asset_count DESC")
    if profile.empty:
        st.stop()

    st.dataframe(profile, width="stretch", hide_index=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Score d'archivage moyen")
        st.bar_chart(profile.set_index("domain_label")["avg_archival_score"], horizontal=True)
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
    st.title("Graphe des clés métier partagées entre domaines")
    st.caption("Domaines employant le même nom de champ-clé (ex. SETID). Signal de "
               "vocabulaire commun / couplage potentiel — PeopleSoft ne déclare pas de "
               "clés étrangères, ce ne sont donc pas des dépendances prouvées.")

    dep = safe_query("SELECT * FROM serving.mv_domain_dependency ORDER BY shared_asset_count DESC")
    if dep.empty:
        st.stop()

    domains = sorted(set(dep["source_domain"]) | set(dep["target_domain"]))
    pick = st.selectbox("Filtrer par domaine", ["(tous)"] + domains)
    view = dep if pick == "(tous)" else dep[(dep["source_domain"] == pick) | (dep["target_domain"] == pick)]

    st.metric("Liens (clés partagées)", len(view))
    top = view.head(20).copy()
    top["paire"] = top["source_domain"] + " ↔ " + top["target_domain"] + " (" + top["bridge_field"] + ")"
    st.subheader("Top 20 liens (nb records partagés)")
    st.bar_chart(top.set_index("paire")["shared_asset_count"], horizontal=True)
    st.dataframe(view, width="stretch", hide_index=True)


# ===========================================================================
# 4. ARCHIVAGE
# ===========================================================================
elif section == "Archivage":
    st.title("Recommandations d'archivage")

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
            st.bar_chart(by_strat.set_index("recommended_strategy")["volume_mb"], horizontal=True)
        with c2:
            st.subheader("Nb d'assets par stratégie")
            st.bar_chart(by_strat.set_index("recommended_strategy")["nb_assets"], horizontal=True)

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
    if dom != "(tous)":
        where.append(f"domain_label = '{dom}'")
    if strat != "(toutes)":
        where.append(f"recommended_strategy = '{strat}'")
    clause = " AND ".join(where)
    reco = safe_query(
        f"""SELECT technical_name, domain_label, recommended_strategy,
                   ROUND(size_mb::numeric,2) AS size_mb, age_band, sensitivity_level,
                   lineage_out_count, rationale
            FROM serving.mv_archiving_recommendation
            WHERE {clause}
            ORDER BY size_mb DESC LIMIT 300"""
    )
    st.caption(f"{len(reco)} assets (top 300 par taille)")
    st.dataframe(reco, width="stretch", hide_index=True)


# ===========================================================================
# 5. COÛTS & ROI
# ===========================================================================
elif section == "Coûts & ROI":
    st.title("Analyse des coûts & projection ROI")

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
            st.altair_chart(pie, width="stretch")
        with c2:
            st.subheader("Pareto des coûts")
            base = alt.Chart(cost).encode(x=alt.X("domain_label:N", sort="-y", title=None))
            bars = base.mark_bar().encode(y=alt.Y("current_cost_usd_year:Q", title="Coût $/an"))
            line = base.mark_line(point=True, color="red").encode(
                y=alt.Y("cumulative_cost_pct:Q", title="% cumulé")
            )
            st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent"), width="stretch")

        st.dataframe(cost, width="stretch", hide_index=True)

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
            st.altair_chart(line, width="stretch")
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
            st.altair_chart(band + median, width="stretch")

        st.dataframe(roi, width="stretch", hide_index=True)

    if not n1.empty:
        with st.expander("📉 Comparaison N-1 (réelle, snapshots historiques)"):
            st.dataframe(n1, width="stretch", hide_index=True)


# ===========================================================================
# 6. PIPELINES — Centre de contrôle
# ===========================================================================
elif section == "🚀 Pipelines":
    st.title("Centre de contrôle des pipelines")
    st.caption("Lance les traitements sans terminal. Les logs s'affichent en direct.")

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
    st.subheader("🗄️ Pipeline complet (lourd — VPN Oracle + MongoDB requis)")
    st.warning(
        "L'extraction interroge Oracle (~87 000 records) puis MongoDB, "
        "reconstruit toute la couche processed + le scoring ML, et crée un "
        "**nouveau run_id**. Durée : plusieurs minutes. À n'utiliser que connecté au VPN."
    )
    if st.button("Initialiser la base (schémas + tables)"):
        run_command("Initialisation base", "src.prefect.flows.flow_init_db")

    confirm = st.checkbox("Je confirme vouloir lancer une extraction (VPN Oracle requis)")
    col_p = st.columns(2)
    if col_p[0].button("🗄️ Pipeline Oracle seul (sans MongoDB)", disabled=not confirm, width="stretch"):
        run_command("Pipeline Oracle seul", "src.prefect.flows.flow_oracle_only")
    if col_p[1].button("🚀 Pipeline complet (Oracle + MongoDB)", disabled=not confirm, type="primary", width="stretch"):
        run_command("Pipeline complet", "src.prefect.flows.flow_full_pipeline")

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
    st.title("Paramètres de coût & ROI")
    st.caption("Édite les paramètres (serving.dim_cost_params) puis relance les calculs en un clic.")

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
