"""Section « Recherche de table » du dashboard."""
from __future__ import annotations

import streamlit as st
from dashboard_common import page_header, safe_query, safe_query_params


def render() -> None:
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
