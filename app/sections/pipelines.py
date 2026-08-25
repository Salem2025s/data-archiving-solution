"""Section « 🚀 Pipelines » du dashboard."""
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
