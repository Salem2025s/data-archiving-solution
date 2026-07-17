"""Script interactif d'exploration de la base Oracle EP92U038.
Usage : python scripts/query_oracle.py
"""
from __future__ import annotations
import json
from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging

configure_logging()

s  = get_settings()
db = OracleClient(settings=s)

def show(title: str, rows: list[dict]) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}  ({len(rows)} ligne(s))")
    print(f"{'='*60}")
    for r in rows:
        print(json.dumps(r, indent=2, default=str))

# ── 1. Comptages globaux ────────────────────────────────────────────────
nb_log = db.fetch_one("SELECT COUNT(*) AS n FROM SYSADM.PSRECDEFN WHERE recname <> 'PSDUMMY'")
nb_phy = db.fetch_one("SELECT COUNT(*) AS n FROM ALL_TABLES WHERE owner = 'SYSADM'")
nb_fld = db.fetch_one("SELECT COUNT(*) AS n FROM SYSADM.PSDBFIELD")

print("\n" + "="*60)
print("  COMPTAGES GLOBAUX")
print("="*60)
print(f"  Records logiques PeopleSoft : {nb_log['n']:,}")
print(f"  Tables physiques Oracle     : {nb_phy['n']:,}")
print(f"  Champs (PSDBFIELD)          : {nb_fld['n']:,}")

# ── 2. Top 20 tables physiques par nb de lignes ─────────────────────────
rows = db.fetch_all("""
    SELECT t.table_name,
           t.num_rows,
           ROUND(t.blocks * 8192 / 1024 / 1024, 2) AS size_mb,
           t.last_analyzed
    FROM ALL_TABLES t
    WHERE t.owner = 'SYSADM'
      AND t.num_rows IS NOT NULL
    ORDER BY t.num_rows DESC
    FETCH FIRST 20 ROWS ONLY
""")
show("TOP 20 TABLES PHYSIQUES (nb lignes)", rows)

# ── 3. Top 20 records logiques PeopleSoft ───────────────────────────────
rows = db.fetch_all("""
    SELECT recname,
           recdescr,
           rectype,
           CASE
               WHEN TRIM(sqltablename) IS NOT NULL AND TRIM(sqltablename) <> ''
               THEN TRIM(sqltablename)
               ELSE 'PS_' || recname
           END AS physical_table_name
    FROM SYSADM.PSRECDEFN
    WHERE recname <> 'PSDUMMY'
    ORDER BY recname
    FETCH FIRST 20 ROWS ONLY
""")
show("TOP 20 RECORDS LOGIQUES PEOPLESOFT (PSRECDEFN)", rows)

# ── 4. Répartition des types de records ─────────────────────────────────
rows = db.fetch_all("""
    SELECT rectype, COUNT(*) AS nb
    FROM SYSADM.PSRECDEFN
    WHERE recname <> 'PSDUMMY'
    GROUP BY rectype
    ORDER BY nb DESC
""")
show("RÉPARTITION PAR TYPE DE RECORD", rows)

# ── 5. Répartition des types de record avec libellés ───────────────────
rows = db.fetch_all("""
    SELECT
        rectype,
        CASE rectype
            WHEN 0 THEN 'SQL Table'
            WHEN 1 THEN 'SQL View'
            WHEN 2 THEN 'Derived/Work Record'
            WHEN 3 THEN 'SubRecord'
            WHEN 5 THEN 'Dynamic View'
            WHEN 6 THEN 'Query View'
            WHEN 7 THEN 'Temporary Table'
            ELSE 'Autre'
        END AS libelle,
        COUNT(*) AS nb
    FROM SYSADM.PSRECDEFN
    WHERE recname <> 'PSDUMMY'
    GROUP BY rectype
    ORDER BY nb DESC
""")
show("RÉPARTITION PAR TYPE DE RECORD (avec libellés)", rows)

# ── 6. Tables physiques qui existent réellement (table_exists_flag=1) ───
rows = db.fetch_all("""
    SELECT r.recname,
           r.recdescr,
           CASE WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
                THEN TRIM(r.sqltablename) ELSE 'PS_' || r.recname END AS physical_table,
           t.num_rows,
           ROUND(t.blocks * 8192 / 1024 / 1024, 2) AS size_mb
    FROM SYSADM.PSRECDEFN r
    JOIN ALL_TABLES t
      ON t.owner = 'SYSADM'
     AND t.table_name = CASE WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''
                             THEN TRIM(r.sqltablename) ELSE 'PS_' || r.recname END
    WHERE r.recname <> 'PSDUMMY'
      AND r.rectype = 0
      AND t.num_rows > 10000
    ORDER BY t.num_rows DESC NULLS LAST
    FETCH FIRST 20 ROWS ONLY
""")
show("TOP 20 TABLES PHYSIQUES EXISTANTES (rectype=0, >10k lignes)", rows)

# ── 7. Aperçu PSACCESSLOG (table de logs d'accès, grosse table existante)
rows = db.fetch_all("""
    SELECT * FROM SYSADM.PSACCESSLOG
    FETCH FIRST 5 ROWS ONLY
""")
show("APERÇU PSACCESSLOG (5 premières lignes)", rows)

# ── 8. Colonnes de PSACCESSLOG ─────────────────────────────────────────
rows = db.fetch_all("""
    SELECT column_name, data_type, data_length, nullable
    FROM ALL_TAB_COLUMNS
    WHERE owner = 'SYSADM'
      AND table_name = 'PSACCESSLOG'
    ORDER BY column_id
""")
show("COLONNES DE PSACCESSLOG", rows)

# ── 9. Top préfixes de records (modules PeopleSoft) ─────────────────────
rows = db.fetch_all("""
    SELECT SUBSTR(recname, 1, 2) AS prefix,
           COUNT(*) AS nb_records
    FROM SYSADM.PSRECDEFN
    WHERE recname <> 'PSDUMMY'
    GROUP BY SUBSTR(recname, 1, 2)
    ORDER BY nb_records DESC
    FETCH FIRST 20 ROWS ONLY
""")
show("TOP 20 PRÉFIXES DE RECORDS (modules PeopleSoft)", rows)

# ── 10. Champs les plus utilisés dans PeopleSoft ────────────────────────
rows = db.fetch_all("""
    SELECT f.fieldname,
           f.fieldtype,
           COUNT(rf.recname) AS nb_records_utilisant
    FROM SYSADM.PSDBFIELD f
    JOIN SYSADM.PSRECFIELDDB rf ON rf.fieldname = f.fieldname
    GROUP BY f.fieldname, f.fieldtype
    ORDER BY nb_records_utilisant DESC
    FETCH FIRST 20 ROWS ONLY
""")
show("TOP 20 CHAMPS LES PLUS UTILISÉS (PSDBFIELD × PSRECFIELDDB)", rows)
