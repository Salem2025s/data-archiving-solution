"""Section « 🤖 Test du modèle » du dashboard."""
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
