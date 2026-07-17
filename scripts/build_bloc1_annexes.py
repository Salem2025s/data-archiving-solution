"""Génère le document Word final des annexes du Bloc 1, images embarquées.

- 13 captures d'écran intégrées, légendées et rangées par annexe (A→G) ;
- Annexe C mise à jour (6 runs, dont le run 9) ;
- textes (arborescence, DDL, réconciliation, code sécurité, requête) conservés.

Usage : python scripts/build_bloc1_annexes.py
"""
from __future__ import annotations

import glob
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "docs" / "certification" / "Bloc 1"
OUT = ROOT / "docs" / "certification" / "BLOC1_Annexes.docx"

ACCENT = RGBColor(0x25, 0x63, 0xEB)
GREY = RGBColor(0x4B, 0x55, 0x63)
CODE_BG = "F1F3F8"
IMG_W = Cm(16.0)


def find_img(prefix: str) -> str | None:
    hits = [m for m in glob.glob(str(IMG_DIR / f"{prefix}*"))
            if m.lower().endswith((".png", ".jpg", ".jpeg"))]
    return sorted(hits)[0] if hits else None


def style_base(doc: Document) -> None:
    n = doc.styles["Normal"]
    n.font.name = "Calibri"
    n.font.size = Pt(10.5)
    for h, sz, col in (("Heading 1", 16, ACCENT), ("Heading 2", 13, ACCENT),
                       ("Heading 3", 11.5, GREY)):
        s = doc.styles[h]
        s.font.name = "Calibri"
        s.font.size = Pt(sz)
        s.font.color.rgb = col


def add_bold(p, text: str) -> None:
    import re
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part:
            continue
        r = p.add_run(part)
        if i % 2 == 1:
            r.bold = True


def para(doc, text: str) -> None:
    add_bold(doc.add_paragraph(), text)


def code(doc, text: str) -> None:
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.cell(0, 0)
    tcpr = cell._tc.get_or_add_tcPr()
    tcpr.append(tcpr.makeelement(qn("w:shd"),
                {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): CODE_BG}))
    cell.paragraphs[0].text = ""
    for idx, ln in enumerate(text.split("\n")):
        p = cell.paragraphs[0] if idx == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        r = p.add_run(ln or " ")
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
    tblpr = t._tbl.tblPr
    b = tblpr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right"):
        b.append(tblpr.makeelement(qn(f"w:{edge}"),
                 {qn("w:val"): "single", qn("w:sz"): "4", qn("w:color"): "D0D7E5"}))
    tblpr.append(b)


def table(doc, header: list[str], rows: list[list[str]]) -> None:
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(header):
        c = t.rows[0].cells[j]
        c.paragraphs[0].text = ""
        add_bold(c.paragraphs[0], h)
        for r in c.paragraphs[0].runs:
            r.bold = True
    for row in rows:
        cells = t.add_row().cells
        for j, val in enumerate(row):
            cells[j].paragraphs[0].text = ""
            add_bold(cells[j].paragraphs[0], val)


def image(doc, prefix: str, caption: str) -> None:
    path = find_img(prefix)
    if not path:
        para(doc, f"_[capture {prefix} introuvable]_")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=IMG_W)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(caption)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = GREY


# ===========================================================================
def build() -> None:
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(2.0); sec.bottom_margin = Cm(2.0)
        sec.left_margin = Cm(2.2); sec.right_margin = Cm(2.2)
    style_base(doc)

    doc.add_heading("BLOC 1 — Annexes", level=1)
    para(doc, "**Titre RNCP 39586 · Bloc 1 — Collecter, transformer et sécuriser des données**")
    para(doc, "Candidat : HAOUARI Salem · Date : 14/07/2026 · Annexes au dossier écrit (hors décompte de pages)")
    para(doc, "Ces annexes apportent les **preuves d'exécution** du pipeline décrit dans le dossier. "
              "Les données proviennent d'exécutions réelles sur l'instance Oracle EP92U038 et "
              "l'entrepôt PostgreSQL pfe_data_ia.")

    # ---- Annexe A ----
    doc.add_heading("Annexe A — Modules de collecte", level=2)
    para(doc, "Organisation du code de collecte, par source (aucune écriture sur la source).")
    code(doc,
         "src/\n"
         "├── connectors/            oracle_client · postgres_client\n"
         "├── extract/\n"
         "│   ├── oracle/   (5)  record_catalog · table_catalog · column_catalog\n"
         "│   │                   index_catalog · segment_access\n"
         "│   ├── external/      fetch_cloud_storage_prices   (API publique Azure)\n"
         "│   └── web/           scrape_storage_benchmark     (scraping tarifaire)\n"
         "└── load/              load_raw_oracle")
    image(doc, "#1 ", "Capture #1 — Connexions Oracle (EP92U038) et PostgreSQL réussies (C1.1.1).")

    # ---- Annexe B ----
    doc.add_heading("Annexe B — Base de données (stockage)", level=2)
    para(doc, "**B.1 — Architecture médaillon** : 4 schémas principaux aux responsabilités "
              "séparées (+ un schéma `security` dédié au coffre PII chiffré, cf. F.4).")
    code(doc,
         "CREATE SCHEMA admin;        -- traçabilité des exécutions\n"
         "CREATE SCHEMA raw_oracle;   -- bronze : copie brute Oracle\n"
         "CREATE SCHEMA processed;    -- silver : modèle en étoile conformé\n"
         "CREATE SCHEMA serving;      -- gold : vues / MV analytiques")
    image(doc, "#5 ", "Capture #5 — Les schémas de l'entrepôt PostgreSQL et leur nb de tables (C1.2.1).")
    para(doc, "**B.2 — Modèle en étoile** : structure de la dimension centrale `processed.dim_asset`.")
    image(doc, "#6 ", "Capture #6 — Colonnes et types de processed.dim_asset (C1.2.1).")

    para(doc, "**B.3 — Détail du modèle en étoile (constellation).** Le hub `dim_asset` "
              "(1 ligne = 1 actif) est entouré de dimensions et de faits, tous rattachés "
              "par la clé `asset_id` + `run_id`.")
    table(doc,
          ["Table", "Type", "Grain", "Rôle / colonnes clés"],
          [["dim_asset", "Dimension (hub)", "1 actif",
            "Entité centrale : technical_name, asset_type, source_ref, description"],
           ["dim_field", "Dimension", "1 colonne",
            "Champs de chaque actif : data_type, nullable_flag, data_length"],
           ["bridge_asset_term", "Pont N–N", "1 lien",
            "Actif ↔ terme métier : term_name, domain_name, confidence_score"],
           ["fact_asset_profile", "Fait", "1 actif × snapshot",
            "Volumétrie & qualité : row_count, size_mb, column_count, index_count"],
           ["fact_lineage_edge", "Fait", "1 arête",
            "Dépendances actif→actif : source_asset_id, target_asset_id, lineage_level"],
           ["fact_archiving_event", "Fait", "1 événement",
            "Archivage : event_type, rows_affected, volume_mb, status"],
           ["features_asset", "Mart dérivé", "1 actif",
            "Variables agrégées + scores : lineage_out_count, archival_candidate_score, roi_score"],
           ["dataset_asset_ml", "Mart dérivé", "1 actif",
            "Table plate dénormalisée prête pour le classifieur (features + signatures texte)"]])

    para(doc, "**Le versionnement par `run_id`** joue le rôle d'une dimension temps : chaque "
              "table le porte, toute requête le filtre, chaque exécution produit un instantané "
              "complet — d'où la reproductibilité et la comparaison N-1 (run 5 vs run 6).")

    para(doc, "**Exemple de requête** — « tables Finance de plus de 10 Mo, avec volume et nb "
              "de colonnes » : on part du hub et on rattache les faits par `asset_id` + `run_id`.")
    code(doc,
         "SELECT d.technical_name, p.size_mb, p.column_count, b.domain_name\n"
         "FROM processed.dim_asset d\n"
         "JOIN processed.fact_asset_profile p\n"
         "     ON p.asset_id = d.id AND p.run_id = d.run_id\n"
         "JOIN processed.bridge_asset_term b\n"
         "     ON b.asset_id = d.id AND b.run_id = d.run_id\n"
         "WHERE d.run_id = 6\n"
         "  AND b.domain_name = 'Finance & Contrôle'\n"
         "  AND p.size_mb > 10\n"
         "ORDER BY p.size_mb DESC;")

    # ---- Annexe C ----
    doc.add_heading("Annexe C — Traçabilité des exécutions", level=2)
    para(doc, "Chaque exécution complète est journalisée dans `admin.pipeline_run`. "
              "La stabilité du volume entre runs (~167 k actifs) atteste de la reproductibilité.")
    table(doc,
          ["id (run)", "flow", "type", "statut", "horodatage", "actifs"],
          [["3", "flow_full_pipeline", "full", "success", "2026-03-13", "167 378"],
           ["4", "flow_full_pipeline", "full", "success", "2026-03-23", "167 378"],
           ["5", "flow_full_pipeline", "full", "success", "2026-04-22", "167 381"],
           ["6", "flow_full_pipeline", "full", "**success**", "2026-05-31", "**167 260 (run traité)**"],
           ["8", "flow_full_pipeline", "full", "failed", "2026-05-30", "— (interrompu)"],
           ["9", "flow_oracle_only", "full", "success", "2026-07-14", "extraction Oracle"]])
    para(doc, "**Note méthodologique.** La table avait été partiellement vidée en cours de projet ; "
              "les entrées des runs 3 à 6 ont été **rétablies à partir des horodatages de chargement "
              "réels** (`processed.dim_asset.loaded_at`) via un script reproductible "
              "(`scripts/backfill_pipeline_run.py`) — aucune valeur inventée. Le run **8 (échoué)** "
              "est conservé : il illustre la **gestion des erreurs** (statut `failed` journalisé). "
              "Le run **9** est une extraction Oracle réelle postérieure.")
    image(doc, "#10 ", "Capture #10 — Historique des exécutions dans le dashboard (C1.1.3 / C1.3.3).")

    # ---- Annexe D ----
    doc.add_heading("Annexe D — Comptages de contrôle (qualité de la collecte)", level=2)
    para(doc, "**D.1 — Exhaustivité** : réconciliation source Oracle ↔ volumes chargés (écart nul).")
    table(doc,
          ["Objet", "Compté sur Oracle", "Chargé en base", "Écart"],
          [["Records logiques (PSRECDEFN)", "87 627", "87 627", "**0**"],
           ["Tables physiques (ALL_TABLES SYSADM)", "79 633", "79 633", "**0**"]])
    image(doc, "#7 ", "Capture #7 — Réconciliation par couche : 87 627 et 79 633 identiques (C1.1.2).")
    image(doc, "#2 ", "Capture #2 — Interrogation directe de la source Oracle (types de records) (C1.1.2).")
    image(doc, "#4 ", "Capture #4 — Données brutes chargées dans raw_oracle.record_catalog (C1.1.2).")

    # ---- Annexe E ----
    doc.add_heading("Annexe E — Valorisation (dashboard)", level=2)
    para(doc, "Données transformées rendues exploitables via l'application de gouvernance.")
    image(doc, "#3 ", "Capture #3 — Centre de contrôle des pipelines / automatisation (C1.1.3).")
    image(doc, "#8 ", "Capture #8 — Vue d'ensemble : cartographie 167 260 actifs (C1.3.2).")
    image(doc, "#9 ", "Capture #9 — Profil par domaine métier (C1.3.2).")
    para(doc, "**Artefact #11** — export Excel `domain_model_run9.xlsx` (13 feuilles) fourni en "
              "pièce jointe : livrable exploitable issu de la couche serving.")

    # ---- Annexe F ----
    doc.add_heading("Annexe F — Sécurisation", level=2)
    para(doc, "**F.1 — Secrets hors dépôt** : le fichier `.env` réel est gitignoré.")
    code(doc, "# .gitignore\n.env\n*.env\n!.env.example")
    image(doc, "#12 ", "Capture #12 — .env exclu du dépôt (règle *.env, fichier non suivi) (C1.4.1).")
    para(doc, "**F.2 — Masquage des données personnelles (RGPD)** dans les exports de labellisation.")
    image(doc, "PII", "Capture #13 — Bloc PII_SEMANTICS et masquage [*** masqué PII ***] (C1.4.1).")
    para(doc, "**F.3 — Accès en lecture seule** : la Console SQL rejette toute écriture.")
    image(doc, "#14 ", "Capture #14 — UPDATE rejeté « lecture seule » (C1.4.1 / C1.4.2).")

    para(doc, "**F.4 — Chiffrement au repos des données personnelles (`pgcrypto`).** "
              "La valeur PII est stockée chiffrée (BYTEA) dans `security.pii_vault` — un schéma "
              "dédié, distinct de la couche analytique `serving` : illisible au repos, "
              "déchiffrable uniquement avec la clé, échec sans la bonne clé.")
    image(doc, "pgcrypto", "Capture #16 — pgcrypto : illisible au repos, déchiffré avec la clé, "
                           "« Wrong key or corrupt data » sans la clé (C1.4.1).")

    para(doc, "**F.5 — Moindre privilège : comptes PostgreSQL séparés.** "
              "`pfe_reader` (SELECT seul) pour la consultation, `pfe_writer` (CRUD) pour le pipeline ETL.")
    image(doc, "Création des rôles", "Capture #17 — Privilèges séparés : pfe_reader = SELECT, "
                                     "pfe_writer = DELETE/INSERT/SELECT/UPDATE (C1.4.1).")
    image(doc, "Preuve du moindre", "Capture #18 — Connecté en pfe_reader : lecture de 167 260 assets "
                                    "autorisée, mais « permission denied » en écriture et suppression (C1.4.1).")

    # ---- Annexe G ----
    doc.add_heading("Annexe G — Requête d'extraction commentée", level=2)
    para(doc, "Cœur de la collecte : réconciliation logique (PeopleSoft) ↔ physique (Oracle).")
    code(doc,
         "SELECT r.recname, r.recdescr, r.rectype,\n"
         "       CASE WHEN TRIM(r.sqltablename) IS NOT NULL AND TRIM(r.sqltablename) <> ''\n"
         "            THEN TRIM(r.sqltablename) ELSE 'PS_' || r.recname END AS physical_table_name,\n"
         "       CASE WHEN t.table_name IS NOT NULL THEN 1 ELSE 0 END AS table_exists_flag\n"
         "FROM SYSADM.PSRECDEFN r\n"
         "LEFT JOIN ALL_TABLES t          -- LEFT JOIN : aucune définition perdue\n"
         "       ON t.owner = :owner       -- requête paramétrée (anti-injection)\n"
         "      AND t.table_name = /* nom physique reconstruit */\n"
         "WHERE r.recname <> 'PSDUMMY'\n"
         "ORDER BY r.recname")

    # ---- Annexe H — collecte externe ----
    doc.add_heading("Annexe H — Collecte externe : API publique et web scraping", level=2)
    para(doc, "Les coûts de stockage du modèle de ROI ne sont plus des constantes codées en dur : "
              "ils proviennent de **sources externes réelles et rejouables** (C1.1.2).")

    para(doc, "**H.1 — API externe (Azure Retail Prices, publique, sans clé).** "
              "Tarifs officiels Hot / Cool / Archive convertis en $/Go/an, injectables dans "
              "`serving.dim_cost_params` pour alimenter `roi_score`.")
    image(doc, "scrapping1", "Capture #19 — API Azure : 229 tarifs reçus, Hot 0,2120 / Archive 0,0216 $/Go/an, "
                             "écart x9,8 (SSL vérifié via truststore) (C1.1.2).")

    para(doc, "**H.2 — Web scraping responsable (Backblaze B2).** "
              "`robots.txt` vérifié avant toute requête ; le tarif concurrent recoupe l'API "
              "et établit une **fourchette de marché** pour l'archivage.")
    image(doc, "scrapping2", "Capture #20 — Scraping : robots.txt autorisé, page récupérée (204 924 octets), "
                             "0,1200 $/Go/an, fourchette de marché 0,0216–0,1200 (C1.1.2).")

    # ---- Annexe I — tâches planifiées ----
    doc.add_heading("Annexe I — Tâches planifiées (déploiements cron Prefect)", level=2)
    para(doc, "Deux déploiements Prefect planifiés répondent au critère « tâches planifiées » (C1.1.3). "
              "Fréquences motivées : la collecte Oracle est lourde (~87 000 records, VPN requis) donc "
              "planifiée **de nuit** ; le recalcul analytique est léger donc **horaire**.")
    table(doc,
          ["Déploiement", "Flow", "CRON", "Fréquence"],
          [["pipeline-oracle-quotidien", "flow_oracle_only", "0 2 * * *", "Chaque nuit à 02h00"],
           ["serving-refresh-horaire", "flow_publish_serving", "0 * * * *", "Toutes les heures"]])
    image(doc, "Prefect", "Capture #15 — Interface Prefect : 2 déploiements à l'état Ready avec leurs "
                          "planifications « At 02:00 AM every day » et « Every hour every day » (C1.1.3).")

    # ---- Save (gère le verrou Word) ----
    try:
        doc.save(str(OUT))
        print(f"OK -> {OUT}  ({OUT.stat().st_size:,} octets)")
    except PermissionError:
        alt = OUT.with_name("BLOC1_Annexes_FINAL.docx")
        doc.save(str(alt))
        print(f"[verrou Word sur {OUT.name}] Sauvé sous -> {alt}  ({alt.stat().st_size:,} octets)")


if __name__ == "__main__":
    build()
