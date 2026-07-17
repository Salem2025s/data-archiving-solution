"""Cartographie complète de l'architecture Oracle EP92U038."""
from __future__ import annotations
import json
from src.config.settings import get_settings
from src.connectors.oracle_client import OracleClient
from src.utils.logging_utils import configure_logging

configure_logging()
db = OracleClient(settings=get_settings())

def show(title, rows):
    print(f"\n{'='*70}\n  {title}  ({len(rows)})\n{'='*70}")
    for r in rows:
        print(json.dumps(r, indent=2, default=str, ensure_ascii=False))

# 1. Schémas/users et taille de leurs données
rows = db.fetch_all("""
    SELECT owner, COUNT(*) AS nb_tables,
           ROUND(SUM(NVL(num_rows,0))) AS total_rows
    FROM ALL_TABLES
    GROUP BY owner
    ORDER BY nb_tables DESC
""")
show("SCHÉMAS (owners) ET NB DE TABLES", rows)

# 2. Tablespaces visibles par l'utilisateur courant (DBA_DATA_FILES non accessible à SYSADM)
rows = db.fetch_all("""
    SELECT tablespace_name, status, contents, extent_management
    FROM USER_TABLESPACES
    ORDER BY tablespace_name
""")
show("TABLESPACES VISIBLES (USER_TABLESPACES)", rows)

# 3. Vue Oracle classique (objets) dans SYSADM
rows = db.fetch_all("""
    SELECT object_type, COUNT(*) AS nb
    FROM ALL_OBJECTS
    WHERE owner = 'SYSADM'
    GROUP BY object_type
    ORDER BY nb DESC
""")
show("TYPES D'OBJETS ORACLE DANS SYSADM", rows)

# 4. Architecture data dictionary PeopleSoft (les tables système clés)
rows = db.fetch_all("""
    SELECT table_name, num_rows
    FROM ALL_TABLES
    WHERE owner = 'SYSADM'
      AND table_name IN (
        'PSRECDEFN','PSDBFIELD','PSRECFIELD','PSRECFIELDDB',
        'PSDBOWNER','PSPNLDEFN','PSPNLFIELD','PSPNLGROUP',
        'PSMENUDEFN','PSAUTHITEM','PSOPRDEFN','PSROLEDEFN',
        'PSCLASSDEFN','PSPRCSDEFN','PSTREEDEFN','PSQRYDEFN',
        'PSXLATITEM','PSSTATUS','PSLANGUAGES','PSVERSION'
      )
    ORDER BY num_rows DESC NULLS LAST
""")
show("TABLES SYSTÈME PEOPLETOOLS (data dictionary applicatif)", rows)

# 5. Relations clés (FK déclarées au niveau Oracle, rares chez PeopleSoft)
rows = db.fetch_all("""
    SELECT COUNT(*) AS nb_fk_oracle
    FROM ALL_CONSTRAINTS
    WHERE owner = 'SYSADM' AND constraint_type = 'R'
""")
show("CONTRAINTES FK DÉCLARÉES AU NIVEAU ORACLE", rows)

# 6. Index — combien et quel type
rows = db.fetch_all("""
    SELECT index_type, COUNT(*) AS nb
    FROM ALL_INDEXES
    WHERE owner = 'SYSADM'
    GROUP BY index_type
    ORDER BY nb DESC
""")
show("TYPES D'INDEX DANS SYSADM", rows)

# 7. Version PeopleTools / Application
rows = db.fetch_all("SELECT * FROM SYSADM.PSSTATUS WHERE ROWNUM <= 5")
show("PSSTATUS — version applicative", rows)

rows = db.fetch_all("SELECT * FROM SYSADM.PSVERSION")
show("PSVERSION — version PeopleTools", rows)

# 8. Taille totale estimée (DBA_SEGMENTS non accessible — approximation via ALL_TABLES)
rows = db.fetch_all("""
    SELECT ROUND(SUM(NVL(num_rows,0) * NVL(avg_row_len,0)) / 1024 / 1024 / 1024, 2) AS taille_estimee_gb
    FROM ALL_TABLES
    WHERE owner = 'SYSADM'
""")
show("TAILLE ESTIMÉE SYSADM (num_rows × avg_row_len, hors index)", rows)

# 9. Comptage des records par parentage (hiérarchie PeopleSoft)
rows = db.fetch_all("""
    SELECT CASE WHEN TRIM(parentrecname) IS NULL THEN '(racine, pas de parent)'
                ELSE 'a un parent' END AS hierarchie,
           COUNT(*) AS nb
    FROM SYSADM.PSRECDEFN
    WHERE recname <> 'PSDUMMY'
    GROUP BY CASE WHEN TRIM(parentrecname) IS NULL THEN '(racine, pas de parent)'
                ELSE 'a un parent' END
""")
show("HIÉRARCHIE PARENT/ENFANT DES RECORDS", rows)
