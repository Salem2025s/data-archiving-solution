"""Section « 💾 Console SQL » du dashboard."""
from __future__ import annotations

import altair as alt  # noqa: F401
import pandas as pd  # noqa: F401
import streamlit as st
from sqlalchemy import text  # noqa: F401

from dashboard_common import (  # noqa: F401
    _PAL, _load_classifier, get_engine, get_settings, load_saved_queries,
    page_header, run_command, run_query, safe_query, safe_query_params,
    write_saved_queries,
)


def render() -> None:
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
