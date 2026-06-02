"""
remap_to_6classes.py — Conversion rapide de l'ancien dataset annoté vers la nouvelle
taxonomie à 6 classes, sans ré-appel LLM.

Stratégie :
1. Remap direct des 5 classes stables (Finance, IT, HR, Procurement, Supply Chain).
2. Fallback heuristique PS pour les lignes "Other" (préfixe PeopleSoft → classe).
3. Marquage needs_review pour les lignes "Other" non-résolues par le dictionnaire PS
   et pour les modules ambigus (PC, WM, AM, GM, PROJ, AUC actuellement mal classifiés).

Sortie :
- Un CSV prêt à l'entraînement avec la colonne `business_domain` dans la nouvelle taxonomie.
- Une colonne `remap_status` indiquant la provenance du label.
- Une colonne `needs_review` pour identifier les cas à valider manuellement.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Nouvelle taxonomie
# ---------------------------------------------------------------------------

ALLOWED_DOMAINS: list[str] = [
    "Finance & Comptabilité",
    "IT & Technique",
    "RH & Paie",
    "Gestion de Projets & Actifs",
    "Achats & Approvisionnement",
    "Supply Chain & Ventes",
]

# ---------------------------------------------------------------------------
# Mapping ancienne taxonomie → nouvelle
# ---------------------------------------------------------------------------

LEGACY_CLASS_MAP: dict[str, str] = {
    # Classes de l'annotation LLM v1 (anglais)
    "finance":           "Finance & Comptabilité",
    "it":                "IT & Technique",
    "hr":                "RH & Paie",
    "risk":              "Finance & Comptabilité",
    "procurement":       "Achats & Approvisionnement",
    "sales":             "Supply Chain & Ventes",
    "marketing":         "Supply Chain & Ventes",
    "supply chain":      "Supply Chain & Ventes",
    # Classes de l'annotation LLM v2 (français partiel)
    "finance & contrôle":                        "Finance & Comptabilité",
    "finance & controle":                        "Finance & Comptabilité",
    "it & sécurité":                             "IT & Technique",
    "it & securite":                             "IT & Technique",
    "achats & fournisseurs":                     "Achats & Approvisionnement",
    "ventes & clients":                          "Supply Chain & Ventes",
    "supply chain / logistique / production":    "Supply Chain & Ventes",
    "supply chain logistique production":        "Supply Chain & Ventes",
    # Classes nouvelle taxonomie (déjà bonnes)
    "finance & comptabilité":                    "Finance & Comptabilité",
    "finance & comptabilite":                    "Finance & Comptabilité",
    "it & technique":                            "IT & Technique",
    "rh & paie":                                 "RH & Paie",
    "gestion de projets & actifs":               "Gestion de Projets & Actifs",
    "gestion de projets et actifs":              "Gestion de Projets & Actifs",
    "achats & approvisionnement":                "Achats & Approvisionnement",
    "supply chain & ventes":                     "Supply Chain & Ventes",
    # Classes de l'ancien `prepare_labeled_dataset.py`
    "technique":         "IT & Technique",
    "rh":                "RH & Paie",
    "achats":            "Achats & Approvisionnement",
    "paie":              "RH & Paie",
}

# ---------------------------------------------------------------------------
# Dictionnaire de préfixes PeopleSoft (identique à annotate_db_train.py)
# ---------------------------------------------------------------------------

PS_MODULE_PREFIX_MAP: dict[str, str] = {
    "GL": "Finance & Comptabilité", "AP": "Finance & Comptabilité",
    "AR": "Finance & Comptabilité", "BI": "Finance & Comptabilité",
    "TR": "Finance & Comptabilité", "EX": "Finance & Comptabilité",
    "KK": "Finance & Comptabilité", "JRNL": "Finance & Comptabilité",
    "VCHR": "Finance & Comptabilité", "VAT": "Finance & Comptabilité",
    "BNK": "Finance & Comptabilité", "BANK": "Finance & Comptabilité",
    "LEDGER": "Finance & Comptabilité", "CM": "Finance & Comptabilité",
    "CC": "Finance & Comptabilité", "PMT": "Finance & Comptabilité",
    "INV": "Finance & Comptabilité", "RE": "Finance & Comptabilité",
    "CE": "Finance & Comptabilité", "WTHD": "Finance & Comptabilité",
    "CNAO": "Finance & Comptabilité", "CA": "Finance & Comptabilité",
    "PP": "Finance & Comptabilité", "JGEN": "Finance & Comptabilité",
    "LC": "Finance & Comptabilité", "OMBI": "Finance & Comptabilité",
    "EOCF": "Finance & Comptabilité", "CP": "Finance & Comptabilité",
    "SPB": "Finance & Comptabilité", "SPR": "Finance & Comptabilité",
    "SPA": "Finance & Comptabilité", "PYCYCL": "Finance & Comptabilité",
    "CLO": "Finance & Comptabilité", "CLOSE": "Finance & Comptabilité",
    "ALC": "Finance & Comptabilité", "COST": "Finance & Comptabilité",
    "DEPR": "Finance & Comptabilité", "LED": "Finance & Comptabilité",
    "BP": "Finance & Comptabilité", "TRX": "Finance & Comptabilité",
    "IU": "Finance & Comptabilité", "TRA": "Finance & Comptabilité",
    "MC": "Finance & Comptabilité", "GLRN": "Finance & Comptabilité",
    "GLRCN": "Finance & Comptabilité", "HDG": "Finance & Comptabilité",
    "RPTG": "Finance & Comptabilité", "SUMLED": "Finance & Comptabilité",
    "PG": "Finance & Comptabilité", "EXS": "Finance & Comptabilité",
    "EE": "Finance & Comptabilité", "PYMNT": "Finance & Comptabilité",
    "CURR": "Finance & Comptabilité", "SII": "Finance & Comptabilité",
    "VED": "Finance & Comptabilité", "FAI": "Finance & Comptabilité",
    "REG": "Finance & Comptabilité", "DIST": "Finance & Comptabilité",
    "STMT": "Finance & Comptabilité", "PST": "Finance & Comptabilité",
    "GTAS": "Finance & Comptabilité", "TRP": "Finance & Comptabilité",
    "ACH": "Finance & Comptabilité", "CONSOL": "Finance & Comptabilité",
    "EXD": "Finance & Comptabilité", "RP": "Finance & Comptabilité",
    "VRBT": "Finance & Comptabilité", "T": "Finance & Comptabilité",

    "AM": "Gestion de Projets & Actifs", "PC": "Gestion de Projets & Actifs",
    "PROJ": "Gestion de Projets & Actifs", "WM": "Gestion de Projets & Actifs",
    "GM": "Gestion de Projets & Actifs", "RS": "Gestion de Projets & Actifs",
    "FO": "Gestion de Projets & Actifs", "ASSET": "Gestion de Projets & Actifs",
    "AMIF": "Gestion de Projets & Actifs",

    "HR": "RH & Paie", "JOB": "RH & Paie", "PERSON": "RH & Paie",
    "BEN": "RH & Paie", "PAY": "RH & Paie", "ABS": "RH & Paie",
    "COMP": "RH & Paie", "TL": "RH & Paie", "TV": "RH & Paie",
    "RETRO": "RH & Paie", "POS": "RH & Paie", "POSN": "RH & Paie",
    "EB": "RH & Paie", "FC": "RH & Paie", "SP": "RH & Paie",
    "EMPL": "RH & Paie", "EMPLMT": "RH & Paie", "EOEN": "RH & Paie",
    "SDK": "RH & Paie",

    "PO": "Achats & Approvisionnement", "EP": "Achats & Approvisionnement",
    "AUC": "Achats & Approvisionnement", "PV": "Achats & Approvisionnement",
    "SPF": "Achats & Approvisionnement", "RFQ": "Achats & Approvisionnement",
    "EM": "Achats & Approvisionnement", "CON": "Achats & Approvisionnement",
    "VND": "Achats & Approvisionnement", "VNDR": "Achats & Approvisionnement",
    "CNTRCT": "Achats & Approvisionnement", "REQ": "Achats & Approvisionnement",
    "RECV": "Achats & Approvisionnement", "SAC": "Achats & Approvisionnement",
    "CS": "Achats & Approvisionnement", "SCR": "Achats & Approvisionnement",
    "SUP": "Achats & Approvisionnement", "VENDOR": "Achats & Approvisionnement",
    "PRCR": "Achats & Approvisionnement", "IST": "Achats & Approvisionnement",
    "SSO": "Achats & Approvisionnement", "RESP": "Achats & Approvisionnement",

    "IN": "Supply Chain & Ventes", "PL": "Supply Chain & Ventes",
    "SF": "Supply Chain & Ventes", "MG": "Supply Chain & Ventes",
    "PROD": "Supply Chain & Ventes", "OM": "Supply Chain & Ventes",
    "SA": "Supply Chain & Ventes", "CRM": "Supply Chain & Ventes",
    "EN": "Supply Chain & Ventes", "RMA": "Supply Chain & Ventes",
    "TD": "Supply Chain & Ventes", "ORD": "Supply Chain & Ventes",
    "CUST": "Supply Chain & Ventes", "ITEM": "Supply Chain & Ventes",
    "ITM": "Supply Chain & Ventes", "QS": "Supply Chain & Ventes",
    "OMPB": "Supply Chain & Ventes", "DLV": "Supply Chain & Ventes",
    "EG": "Supply Chain & Ventes", "OMC": "Supply Chain & Ventes",
    "OMBCK": "Supply Chain & Ventes", "OMEC": "Supply Chain & Ventes",
    "OMB": "Supply Chain & Ventes",

    "IT": "IT & Technique", "PRCS": "IT & Technique",
    "PSAUTH": "IT & Technique", "PSOPR": "IT & Technique",
    "PSROLE": "IT & Technique", "PT": "IT & Technique",
    "PSMENU": "IT & Technique", "UPG": "IT & Technique",
    "RUN": "IT & Technique", "PGM": "IT & Technique",
    "EOCM": "IT & Technique", "P6": "IT & Technique",
    "DP": "IT & Technique", "PTLT": "IT & Technique",
    "PTPPB": "IT & Technique", "EOEW": "IT & Technique",
    "EODP": "IT & Technique", "EOEP": "IT & Technique",
    "EODI": "IT & Technique", "AGC": "IT & Technique",
    "PSA": "IT & Technique", "PTSF": "IT & Technique",
    "EO": "IT & Technique", "FS": "IT & Technique",
    "RTBL": "IT & Technique", "INTFC": "IT & Technique",
    "BUS": "IT & Technique", "DR": "IT & Technique",
    "TREE": "IT & Technique", "SEC": "IT & Technique",
    "BU": "IT & Technique", "SCD": "IT & Technique",
    "CF": "IT & Technique", "IB": "IT & Technique",
    "AE": "IT & Technique", "OPR": "IT & Technique",
    "BPW": "IT & Technique", "DPA": "IT & Technique",
    "COMBO": "IT & Technique", "EOEC": "IT & Technique",
    "EOAW": "IT & Technique", "FSPC": "IT & Technique",
    "TSE": "IT & Technique", "TSEL": "IT & Technique",
    "PTAI": "IT & Technique", "PI": "IT & Technique",
    "ARCH": "IT & Technique", "COMB": "IT & Technique",
    "GC": "IT & Technique", "BCT": "IT & Technique",
    "OI": "IT & Technique", "OCH": "IT & Technique",
    "PRD": "IT & Technique", "NET": "IT & Technique",
}

# Préfixes qui ont été mal classifiés par l'ancien LLM et doivent être
# corrigés même si le label existant n'est pas "Other".
KNOWN_MISCLASSIFIED: dict[str, str] = {
    "PC":   "Gestion de Projets & Actifs",
    "PROJ": "Gestion de Projets & Actifs",
    "WM":   "Gestion de Projets & Actifs",
    "GM":   "Gestion de Projets & Actifs",
    "AM":   "Gestion de Projets & Actifs",
    "AUC":  "Achats & Approvisionnement",
    "FO":   "Gestion de Projets & Actifs",
    "RS":   "Gestion de Projets & Actifs",
}


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _normalize_key(text: str) -> str:
    v = text.strip().lower()
    v = unicodedata.normalize("NFKD", v)
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = v.replace("&", " and ")
    v = re.sub(r"[\/_\-]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def extract_prefix(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        return ""
    s = name.strip().upper()
    s = re.sub(r"^[A-Z]+\.", "", s)
    s = re.sub(r"^PS[_]?", "", s)
    m = re.match(r"([A-Z][A-Z0-9]+)_", s)
    if m:
        return m.group(1)
    return s.split("_")[0][:8] if "_" in s else s[:8]


def map_legacy_label(raw_label: object) -> str:
    """Traduit un ancien label vers la nouvelle taxonomie. Retourne '' si inconnu."""
    if raw_label is None:
        return ""
    if isinstance(raw_label, float):
        import math
        if math.isnan(raw_label):
            return ""
    key = _normalize_key(str(raw_label))
    # Vérification directe
    if key in LEGACY_CLASS_MAP:
        return LEGACY_CLASS_MAP[key]
    # Correspondance partielle
    for alias, domain in LEGACY_CLASS_MAP.items():
        if key in alias or alias in key:
            return domain
    return ""


def ps_fallback(technical_name: object, source_ref: object) -> str:
    """Tente une résolution via préfixe PS. Retourne '' si aucun match."""
    for value in (technical_name, source_ref):
        prefix = extract_prefix(value)
        if prefix and prefix in PS_MODULE_PREFIX_MAP:
            return PS_MODULE_PREFIX_MAP[prefix]
    return ""


# ---------------------------------------------------------------------------
# Logique de remapping ligne par ligne
# ---------------------------------------------------------------------------

def remap_row(row: pd.Series) -> dict[str, object]:
    raw_label = row.get("business_domain", "")
    tech_name = row.get("technical_name", "")
    source_ref = row.get("source_ref", "")

    prefix = extract_prefix(tech_name or source_ref)
    label_key = _normalize_key(str(raw_label)) if raw_label else ""
    is_other = label_key in {"other", "autre", "non classe", "inconnu", "unknown", ""}

    # --- Priorité 1 : correction des modules connus mal classifiés ---
    if prefix in KNOWN_MISCLASSIFIED:
        new_domain = KNOWN_MISCLASSIFIED[prefix]
        old_was_correct = (map_legacy_label(raw_label) == new_domain)
        status = "corrected_misclassified_module" if not old_was_correct else "remap_direct"
        needs_review = not old_was_correct
        return {
            "business_domain": new_domain,
            "remap_status": status,
            "needs_review": needs_review,
            "ps_prefix": prefix,
        }

    # --- Priorité 2 : remapping direct de l'ancien label ---
    if not is_other:
        mapped = map_legacy_label(raw_label)
        if mapped:
            return {
                "business_domain": mapped,
                "remap_status": "remap_direct",
                "needs_review": False,
                "ps_prefix": prefix,
            }

    # --- Priorité 3 : fallback PS pour les "Other" ---
    fallback = ps_fallback(tech_name, source_ref)
    if fallback:
        return {
            "business_domain": fallback,
            "remap_status": "fallback_ps_prefix",
            "needs_review": False,
            "ps_prefix": prefix,
        }

    # --- Cas non-résolu : marquer pour ré-annotation LLM ---
    return {
        "business_domain": "",
        "remap_status": "unresolved_needs_llm",
        "needs_review": True,
        "ps_prefix": prefix,
    }


# ---------------------------------------------------------------------------
# Script principal
# ---------------------------------------------------------------------------

def remap_dataset(input_path: str, output_path: str, output_review_path: str) -> None:
    print(f"Lecture : {input_path}")
    df = pd.read_csv(input_path, encoding="utf-8-sig", on_bad_lines="skip", low_memory=False)
    print(f"  {len(df)} lignes chargées")

    results = df.apply(remap_row, axis=1, result_type="expand")

    df_out = df.copy()
    df_out["business_domain"] = results["business_domain"]
    df_out["remap_status"]    = results["remap_status"]
    df_out["needs_review"]    = results["needs_review"]
    df_out["ps_prefix"]       = results["ps_prefix"]

    # --- Statistiques ---
    total = len(df_out)
    print()
    print("=== Distribution nouvelle taxonomie ===")
    for domain in ALLOWED_DOMAINS + [""]:
        n = (df_out["business_domain"] == domain).sum()
        if n:
            label = domain or "(non-résolu)"
            print(f"  {label:45s} {n:5d}  ({n/total*100:.1f}%)")

    print()
    print("=== Statuts de remapping ===")
    for status, n in df_out["remap_status"].value_counts().items():
        print(f"  {status:40s} {n:5d}  ({n/total*100:.1f}%)")

    n_review = df_out["needs_review"].sum()
    print(f"\nneeds_review=True : {n_review} lignes ({n_review/total*100:.1f}%)")

    # --- Export dataset principal (domaine assigné uniquement) ---
    df_assigned = df_out[df_out["business_domain"].isin(ALLOWED_DOMAINS)].copy()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df_assigned.to_csv(output_path, index=False, encoding="utf-8")
    print(f"\nDataset remappé : {output_path}  ({len(df_assigned)} lignes)")

    # --- Export file de révision LLM ---
    df_review = df_out[df_out["remap_status"] == "unresolved_needs_llm"].copy()
    if not df_review.empty:
        Path(output_review_path).parent.mkdir(parents=True, exist_ok=True)
        df_review.to_csv(output_review_path, index=False, encoding="utf-8")
        print(f"File LLM à ré-annoter : {output_review_path}  ({len(df_review)} lignes)")
    else:
        print("Aucune ligne non-résolue — pas de file LLM nécessaire.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remap du dataset annoté vers la taxonomie 6 classes sans LLM."
    )
    parser.add_argument(
        "--input",
        default="exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_annotated.csv",
    )
    parser.add_argument(
        "--output",
        default="exports/dataset_asset_ml_training_v5_remapped.csv",
    )
    parser.add_argument(
        "--output-review",
        default="exports/dataset_asset_ml_training_v5_needs_llm.csv",
        help="Lignes non-résolues à soumettre au script LLM.",
    )
    args = parser.parse_args()
    remap_dataset(
        input_path=args.input,
        output_path=args.output,
        output_review_path=args.output_review,
    )


if __name__ == "__main__":
    main()
