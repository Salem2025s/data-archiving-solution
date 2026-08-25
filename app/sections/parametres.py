"""Section « ⚙️ Paramètres » du dashboard."""
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
