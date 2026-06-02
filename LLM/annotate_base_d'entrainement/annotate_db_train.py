"""
annotate_db_train.py — Annotation LLM de la base d'entraînement (domaines métier).

Améliorations vs version précédente :
- Taxonomie à 6 classes sans "Other" : Finance & Comptabilité, IT & Technique,
  RH & Paie, Gestion de Projets & Actifs (nouvelle), Achats & Approvisionnement,
  Supply Chain & Ventes.
- technical_name inclus dans le contexte LLM avec extraction du préfixe PS.
- Dictionnaire de 90+ préfixes PeopleSoft → fallback heuristique quand le LLM
  renvoie une classe invalide ou hésite.
- Prompt système mis à jour : glossaire PS explicite, interdiction de "Other".
- Flag needs_review pour les prédictions à faible consensus (remplace "Other").
- Taxonomie mono-niveau : le LLM répond directement en français, pas de mapping
  intermédiaire anglais→français.
- Nouveau flag --force-reannotate-other : re-annote les lignes avec l'ancienne
  valeur "Other" même si --skip-existing est actif.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Taxonomie finale — 6 classes, sans "Other"
# ---------------------------------------------------------------------------

ALLOWED_DOMAINS: list[str] = [
    "Finance & Comptabilité",
    "IT & Technique",
    "RH & Paie",
    "Gestion de Projets & Actifs",
    "Achats & Approvisionnement",
    "Supply Chain & Ventes",
]

DOMAIN_SET: set[str] = set(ALLOWED_DOMAINS)

# Seuil en dessous duquel needs_review passe à True
LOW_CONSENSUS_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Dictionnaire de préfixes PeopleSoft → classe métier
# Utilisé comme fallback heuristique et comme hint dans le contexte LLM.
# ---------------------------------------------------------------------------

PS_MODULE_PREFIX_MAP: dict[str, str] = {
    # Finance & Comptabilité
    "GL":     "Finance & Comptabilité",
    "AP":     "Finance & Comptabilité",
    "AR":     "Finance & Comptabilité",
    "BI":     "Finance & Comptabilité",
    "TR":     "Finance & Comptabilité",
    "EX":     "Finance & Comptabilité",
    "KK":     "Finance & Comptabilité",
    "JRNL":   "Finance & Comptabilité",
    "VCHR":   "Finance & Comptabilité",
    "VAT":    "Finance & Comptabilité",
    "BNK":    "Finance & Comptabilité",
    "BANK":   "Finance & Comptabilité",
    "LEDGER": "Finance & Comptabilité",
    "CM":     "Finance & Comptabilité",
    "CC":     "Finance & Comptabilité",
    "PMT":    "Finance & Comptabilité",
    "INV":    "Finance & Comptabilité",
    "RE":     "Finance & Comptabilité",
    "CE":     "Finance & Comptabilité",
    "WTHD":   "Finance & Comptabilité",
    "CNAO":   "Finance & Comptabilité",
    "CA":     "Finance & Comptabilité",
    "PP":     "Finance & Comptabilité",
    "JGEN":   "Finance & Comptabilité",
    "LC":     "Finance & Comptabilité",
    "OMBI":   "Finance & Comptabilité",
    "EOCF":   "Finance & Comptabilité",
    "CP":     "Finance & Comptabilité",
    "SPB":    "Finance & Comptabilité",
    "SPR":    "Finance & Comptabilité",
    "SPA":    "Finance & Comptabilité",
    "PYCYCL": "Finance & Comptabilité",
    # Finance — préfixes complémentaires (period close, allocations, coûts, reporting)
    "CLO":    "Finance & Comptabilité",
    "CLOSE":  "Finance & Comptabilité",
    "ALC":    "Finance & Comptabilité",
    "COST":   "Finance & Comptabilité",
    "DEPR":   "Finance & Comptabilité",
    "LED":    "Finance & Comptabilité",
    "BP":     "Finance & Comptabilité",
    "TRX":    "Finance & Comptabilité",
    "IU":     "Finance & Comptabilité",
    "TRA":    "Finance & Comptabilité",
    "MC":     "Finance & Comptabilité",
    "GLRN":   "Finance & Comptabilité",
    "GLRCN":  "Finance & Comptabilité",
    "HDG":    "Finance & Comptabilité",
    "RPTG":   "Finance & Comptabilité",
    "SUMLED": "Finance & Comptabilité",
    "PG":     "Finance & Comptabilité",
    "EXS":    "Finance & Comptabilité",
    "EE":     "Finance & Comptabilité",
    "PYMNT":  "Finance & Comptabilité",
    "CURR":   "Finance & Comptabilité",
    "SII":    "Finance & Comptabilité",
    "VED":    "Finance & Comptabilité",
    "FAI":    "Finance & Comptabilité",
    "REG":    "Finance & Comptabilité",
    "DIST":   "Finance & Comptabilité",
    "STMT":   "Finance & Comptabilité",
    "PST":    "Finance & Comptabilité",
    "GTAS":   "Finance & Comptabilité",
    "TRP":    "Finance & Comptabilité",
    "ACH":    "Finance & Comptabilité",
    "CONSOL": "Finance & Comptabilité",
    "EXD":    "Finance & Comptabilité",
    "RP":     "Finance & Comptabilité",
    "VRBT":   "Finance & Comptabilité",
    "T":      "Finance & Comptabilité",

    # Gestion de Projets & Actifs  ← classe clé nouvelle
    "AM":     "Gestion de Projets & Actifs",
    "PC":     "Gestion de Projets & Actifs",
    "PROJ":   "Gestion de Projets & Actifs",
    "WM":     "Gestion de Projets & Actifs",
    "GM":     "Gestion de Projets & Actifs",
    "RS":     "Gestion de Projets & Actifs",
    "FO":     "Gestion de Projets & Actifs",

    # RH & Paie
    "HR":     "RH & Paie",
    "JOB":    "RH & Paie",
    "PERSON": "RH & Paie",
    "BEN":    "RH & Paie",
    "PAY":    "RH & Paie",
    "ABS":    "RH & Paie",
    "COMP":   "RH & Paie",
    "TL":     "RH & Paie",
    "TV":     "RH & Paie",
    "RETRO":  "RH & Paie",
    # RH — préfixes complémentaires
    "POS":    "RH & Paie",
    "POSN":   "RH & Paie",
    "EB":     "RH & Paie",
    "FC":     "RH & Paie",
    "SP":     "RH & Paie",
    "EMPL":   "RH & Paie",
    "EMPLMT": "RH & Paie",
    "EOEN":   "RH & Paie",
    "SDK":    "RH & Paie",

    # Gestion de Projets & Actifs — préfixes complémentaires
    "ASSET":  "Gestion de Projets & Actifs",
    "AMIF":   "Gestion de Projets & Actifs",

    # Achats & Approvisionnement
    "PO":     "Achats & Approvisionnement",
    "EP":     "Achats & Approvisionnement",
    "AUC":    "Achats & Approvisionnement",   # Auctions/eSourcing → Achats
    "PV":     "Achats & Approvisionnement",
    "SPF":    "Achats & Approvisionnement",
    "RFQ":    "Achats & Approvisionnement",
    "EM":     "Achats & Approvisionnement",
    "CON":    "Achats & Approvisionnement",
    "VND":    "Achats & Approvisionnement",
    "VNDR":   "Achats & Approvisionnement",
    "CNTRCT": "Achats & Approvisionnement",
    "REQ":    "Achats & Approvisionnement",
    "RECV":   "Achats & Approvisionnement",
    "SAC":    "Achats & Approvisionnement",
    "CS":     "Achats & Approvisionnement",
    "SCR":    "Achats & Approvisionnement",
    # Achats — préfixes complémentaires
    "SUP":    "Achats & Approvisionnement",
    "VENDOR": "Achats & Approvisionnement",
    "PRCR":   "Achats & Approvisionnement",
    "IST":    "Achats & Approvisionnement",
    "SSO":    "Achats & Approvisionnement",
    "RESP":   "Achats & Approvisionnement",

    # Supply Chain & Ventes
    "IN":     "Supply Chain & Ventes",
    "PL":     "Supply Chain & Ventes",
    "SF":     "Supply Chain & Ventes",
    "MG":     "Supply Chain & Ventes",
    "PROD":   "Supply Chain & Ventes",
    "OM":     "Supply Chain & Ventes",
    "SA":     "Supply Chain & Ventes",
    "CRM":    "Supply Chain & Ventes",
    "EN":     "Supply Chain & Ventes",
    "RMA":    "Supply Chain & Ventes",
    "TD":     "Supply Chain & Ventes",
    "ORD":    "Supply Chain & Ventes",
    "CUST":   "Supply Chain & Ventes",
    # Supply Chain & Ventes — préfixes complémentaires
    "ITEM":   "Supply Chain & Ventes",
    "ITM":    "Supply Chain & Ventes",
    "QS":     "Supply Chain & Ventes",
    "OMPB":   "Supply Chain & Ventes",
    "DLV":    "Supply Chain & Ventes",
    "EG":     "Supply Chain & Ventes",
    "OMC":    "Supply Chain & Ventes",
    "OMBCK":  "Supply Chain & Ventes",
    "OMEC":   "Supply Chain & Ventes",
    "OMB":    "Supply Chain & Ventes",

    # IT & Technique
    "IT":     "IT & Technique",
    "PRCS":   "IT & Technique",
    "PSAUTH": "IT & Technique",
    "PSOPR":  "IT & Technique",
    "PSROLE": "IT & Technique",
    "PT":     "IT & Technique",
    "PSMENU": "IT & Technique",
    "UPG":    "IT & Technique",
    "RUN":    "IT & Technique",
    "PGM":    "IT & Technique",
    "EOCM":   "IT & Technique",
    "P6":     "IT & Technique",
    "DP":     "IT & Technique",
    "PTLT":   "IT & Technique",
    "PTPPB":  "IT & Technique",
    "EOEW":   "IT & Technique",
    "EODP":   "IT & Technique",
    "EOEP":   "IT & Technique",
    "EODI":   "IT & Technique",
    "AGC":    "IT & Technique",
    "PSA":    "IT & Technique",
    "PTSF":   "IT & Technique",
    "EO":     "IT & Technique",
    "FS":     "IT & Technique",
    "RTBL":   "IT & Technique",
    "INTFC":  "IT & Technique",
    "BUS":    "IT & Technique",
    "DR":     "IT & Technique",
    "TREE":   "IT & Technique",
    "SEC":    "IT & Technique",
    "BU":     "IT & Technique",
    # IT & Technique — préfixes complémentaires
    "SCD":    "IT & Technique",
    "CF":     "IT & Technique",
    "IB":     "IT & Technique",
    "AE":     "IT & Technique",
    "OPR":    "IT & Technique",
    "BPW":    "IT & Technique",
    "DPA":    "IT & Technique",
    "COMBO":  "IT & Technique",
    "EOEC":   "IT & Technique",
    "EOAW":   "IT & Technique",
    "FSPC":   "IT & Technique",
    "TSE":    "IT & Technique",
    "TSEL":   "IT & Technique",
    "PTAI":   "IT & Technique",
    "PI":     "IT & Technique",
    "ARCH":   "IT & Technique",
    "COMB":   "IT & Technique",
    "GC":     "IT & Technique",
    "INSTALLATION": "IT & Technique",
    "BCT":    "IT & Technique",
    "OI":     "IT & Technique",
    "EXPLODE":"IT & Technique",
    "OCH":    "IT & Technique",
    "PRD":    "IT & Technique",
    "NET":    "IT & Technique",
}

# Colonnes jamais transmises au LLM (métadonnées pipeline, annotations préexistantes).
PROMPT_EXCLUDED_COLUMNS: set[str] = {
    "run_id",
    "asset_id",
    "business_domain",
    "business_domain_label",
    "business_domain_raw",
    "confidence",
    "reason",
    "labeling_notes",
    "llm_status",
    "llm_votes_json",
    "llm_models_used",
    "llm_prompt_version",
    "llm_consensus_score",
    "needs_review",
    "ps_prefix",
    "ps_prefix_hint",
}

# Colonnes principales du contexte métier.
PRIMARY_CONTEXT_COLUMNS: list[str] = [
    "technical_name",
    "source_ref",
    "column_names_text",
    "column_type_signature_text",
    "column_value_semantics_text",
    "column_sample_values_text",
]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Table de référence PS intégrée dans le prompt pour guider le LLM.
_PS_GUIDE_TABLE = """\
PeopleSoft module prefix → domain (use as strong signal):
  GL AP AR BI TR EX KK JRNL VCHR VAT BNK LEDGER CM CC PMT INV RE CE WTHD CA → Finance & Comptabilité
  AM PC PROJ WM GM RS FO                                                      → Gestion de Projets & Actifs
  HR JOB PERSON BEN PAY ABS COMP TL TV                                        → RH & Paie
  PO EP AUC PV SPF RFQ EM CON VND CNTRCT REQ RECV SAC CS                      → Achats & Approvisionnement
  IN PL SF MG PROD OM SA CRM EN RMA ORD                                       → Supply Chain & Ventes
  IT PRCS PSAUTH PSOPR PSROLE PT PSMENU UPG RUN PGM EO FS RTBL INTFC BUS     → IT & Technique

Critical disambiguations (common LLM mistakes to avoid):
  AUC = PeopleSoft Auctions/eSourcing            → ALWAYS Achats & Approvisionnement
  WM  = Work/Maintenance Management (assets)     → ALWAYS Gestion de Projets & Actifs
  PC  = Project Costing (not Cost Center)        → ALWAYS Gestion de Projets & Actifs
  PROJ= Project Management                       → ALWAYS Gestion de Projets & Actifs
  GM  = Grants Management                        → ALWAYS Gestion de Projets & Actifs
  KK  = Commitment Control / Budget checking     → ALWAYS Finance & Comptabilité
  FO  = Field Operations / Workforce Scheduling  → ALWAYS Gestion de Projets & Actifs"""

SYSTEM_PROMPT = f"""\
You are a senior PeopleSoft ERP data governance expert (Oracle PeopleSoft EP92U038).

TASK
Assign exactly ONE business domain to the data asset described in the input context.

ALLOWED DOMAINS — choose exactly one, no other value is accepted:
1. Finance & Comptabilité      — GL, AP/AR, billing, treasury, expenses, tax, budget control, journals
2. IT & Technique              — PeopleTools, security/roles, process scheduler, technical configs, interfaces
3. RH & Paie                   — HR records, payroll, benefits, absences, compensation, time & labour
4. Gestion de Projets & Actifs — fixed assets (AM), project costing (PC), project mgmt (PROJ),
                                  maintenance (WM), grants (GM), resource scheduling (RS)
5. Achats & Approvisionnement  — purchase orders, eSourcing/auctions (AUC), vendors, requisitions,
                                  receiving, supplier contracts
6. Supply Chain & Ventes       — inventory, planning, manufacturing, shipments, customer orders (OM),
                                  sales, CRM

{_PS_GUIDE_TABLE}

DECISION RULES (in priority order)
1. If ps_prefix_hint is present in the context, it is a strong domain signal — use it unless column
   evidence clearly contradicts it.
2. Analyse column names, semantic roles, and sample values to confirm or override the prefix signal.
3. "Other" is NOT an allowed domain. When uncertain, pick the CLOSEST domain based on column
   evidence. Prefer Finance & Comptabilité for cross-module accounting tables, IT & Technique for
   pure system/configuration tables with no business columns.
4. Return STRICT JSON only — no extra text, no markdown.

OUTPUT FORMAT
{{"business_domain": "<exact domain name from the list above>"}}"""

ADJUDICATOR_SYSTEM_PROMPT = """\
You are a senior PeopleSoft ERP data governance expert.

You receive an asset context and a set of candidate votes from previous LLM passes.
Choose exactly ONE final domain from this list:
- Finance & Comptabilité
- IT & Technique
- RH & Paie
- Gestion de Projets & Actifs
- Achats & Approvisionnement
- Supply Chain & Ventes

Rules:
- Base the decision on the asset context, not on majority vote alone.
- Candidate votes are hints, not ground truth.
- "Other" is NOT allowed — pick the closest domain.
- Return STRICT JSON only: {"business_domain": "<exact domain name>"}"""


# ---------------------------------------------------------------------------
# Normalisation des labels
# ---------------------------------------------------------------------------

DOMAIN_ALIASES: dict[str, str] = {
    # Finance & Comptabilité
    "finance":                                   "Finance & Comptabilité",
    "finance comptabilite":                      "Finance & Comptabilité",
    "finance and comptabilite":                  "Finance & Comptabilité",
    "finance controle":                          "Finance & Comptabilité",
    "finance and controle":                      "Finance & Comptabilité",
    "finance and control":                       "Finance & Comptabilité",
    "finance control":                           "Finance & Comptabilité",
    "finance comptabilite controle":             "Finance & Comptabilité",
    "risk":                                      "Finance & Comptabilité",
    "risque":                                    "Finance & Comptabilité",
    # IT & Technique
    "it":                                        "IT & Technique",
    "it technique":                              "IT & Technique",
    "it securite":                               "IT & Technique",
    "it security":                               "IT & Technique",
    "it and technique":                          "IT & Technique",
    "security":                                  "IT & Technique",
    "securite":                                  "IT & Technique",
    "technique":                                 "IT & Technique",
    "technical":                                 "IT & Technique",
    # RH & Paie
    "rh":                                        "RH & Paie",
    "hr":                                        "RH & Paie",
    "rh paie":                                   "RH & Paie",
    "hr paie":                                   "RH & Paie",
    "rh and paie":                               "RH & Paie",
    "human resources":                           "RH & Paie",
    "ressources humaines":                       "RH & Paie",
    "payroll":                                   "RH & Paie",
    "paie":                                      "RH & Paie",
    # Gestion de Projets & Actifs
    "gestion de projets et actifs":              "Gestion de Projets & Actifs",
    "gestion de projets and actifs":             "Gestion de Projets & Actifs",
    "projets actifs":                            "Gestion de Projets & Actifs",
    "projets et actifs":                         "Gestion de Projets & Actifs",
    "project management":                        "Gestion de Projets & Actifs",
    "asset management":                          "Gestion de Projets & Actifs",
    "gestion des actifs":                        "Gestion de Projets & Actifs",
    "gestion de projets":                        "Gestion de Projets & Actifs",
    "immobilisations":                           "Gestion de Projets & Actifs",
    "maintenance":                               "Gestion de Projets & Actifs",
    # Achats & Approvisionnement
    "achats":                                    "Achats & Approvisionnement",
    "achats fournisseurs":                       "Achats & Approvisionnement",
    "achats and approvisionnement":              "Achats & Approvisionnement",
    "procurement":                               "Achats & Approvisionnement",
    "purchasing":                                "Achats & Approvisionnement",
    "vendors":                                   "Achats & Approvisionnement",
    "vendor":                                    "Achats & Approvisionnement",
    "suppliers":                                 "Achats & Approvisionnement",
    "supplier":                                  "Achats & Approvisionnement",
    "approvisionnement":                         "Achats & Approvisionnement",
    # Supply Chain & Ventes
    "supply chain":                              "Supply Chain & Ventes",
    "supply chain ventes":                       "Supply Chain & Ventes",
    "supply chain and ventes":                   "Supply Chain & Ventes",
    "supply chain logistique production":        "Supply Chain & Ventes",
    "supply chain / logistique / production":    "Supply Chain & Ventes",
    "logistique":                                "Supply Chain & Ventes",
    "logistics":                                 "Supply Chain & Ventes",
    "production":                                "Supply Chain & Ventes",
    "manufacturing":                             "Supply Chain & Ventes",
    "ventes":                                    "Supply Chain & Ventes",
    "ventes clients":                            "Supply Chain & Ventes",
    "sales":                                     "Supply Chain & Ventes",
    "sales clients":                             "Supply Chain & Ventes",
    "crm":                                       "Supply Chain & Ventes",
    "marketing":                                 "Supply Chain & Ventes",
    "commerce":                                  "Supply Chain & Ventes",
}

# Valeurs à traiter comme "à re-annoter" (ancienne taxonomie)
LEGACY_OTHER_VALUES: set[str] = {
    "other", "autre", "non classe", "non renseigne", "inconnu", "unknown",
}


# ---------------------------------------------------------------------------
# Poids sémantiques (inchangés de la version précédente)
# ---------------------------------------------------------------------------

SEMANTIC_WEIGHTS: dict[str, float] = {
    "person_identifier":    4.5,
    "person_full_name":     4.5,
    "person_first_name":    3.8,
    "person_last_name":     3.8,
    "job_label":            4.0,
    "financial_amount":     4.5,
    "percentage_or_rate":   2.2,
    "postal_location":      3.0,
    "email_address":        3.2,
    "phone_number":         3.2,
    "url":                  1.8,
    "status":               2.2,
    "classification":       1.8,
    "reference_identifier": 2.0,
    "identifier":           1.1,
    "technical_identifier": 2.6,
    "user_identifier":      3.0,
    "processing_identifier":2.9,
    "technical_timestamp":  1.6,
    "date_or_timestamp":    1.3,
    "date_part":            1.0,
    "comment_text":         1.8,
    "score":                1.2,
    "duration":             1.1,
    "flag":                 0.9,
    "quantity":             0.7,
    "label":                0.4,
}

LOW_INFORMATION_NAME_TOKENS: set[str] = {
    "id", "code", "num", "nbr", "no", "seq", "flag", "type", "value", "name",
    "descr", "descrlong", "descr50", "setid", "status", "dt", "dttm", "date",
    "amt", "qty", "cnt", "ind", "key", "line", "row", "col", "field", "text",
    "process", "instance", "language", "lang", "cd", "tbl", "tao", "lng",
}

ABBREVIATION_MAP: dict[str, str] = {
    "empl": "employee", "emp": "employee", "dept": "department",
    "cust": "customer", "cst": "customer", "vend": "vendor",
    "vndr": "vendor", "sup": "supplier", "po": "purchase_order",
    "req": "requisition", "inv": "invoice", "acct": "account",
    "gl": "general_ledger", "ar": "accounts_receivable",
    "ap": "accounts_payable", "itm": "item", "whse": "warehouse",
    "ship": "shipment", "rcv": "receiving", "pay": "payment",
    "mkt": "marketing", "cmpgn": "campaign", "usr": "user",
    "sec": "security", "perm": "permission", "wf": "workflow",
    "proc": "process", "sched": "schedule", "proj": "project",
    "am": "asset_management", "wm": "work_management",
    "gm": "grants_management", "pc": "project_costing",
    "auc": "auction", "fo": "field_operations",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    models: list[str]
    temperature: float = 0.0
    timeout_seconds: int = 90
    max_retries: int = 3
    sleep_between_calls: float = 0.2
    top_k_columns: int = 24
    max_sample_chars: int = 140
    max_context_chars: int = 7000
    prompt_version: str = "business_domain_v5_6classes_nps"
    adjudicate_on_tie: bool = True


# ---------------------------------------------------------------------------
# Utilitaires génériques
# ---------------------------------------------------------------------------

def normalize_ws(text: Any) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = str(text).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_label_key(text: Any) -> str:
    value = normalize_ws(text)
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[\/_\-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_domain(raw_value: Any) -> str:
    """Normalise une valeur brute renvoyée par le LLM vers une des 6 classes."""
    value = normalize_ws(raw_value)
    if not value:
        return ""

    norm = normalize_label_key(value)

    # Correspondance directe sur la clé normalisée
    if norm in DOMAIN_ALIASES:
        return DOMAIN_ALIASES[norm]

    # Correspondance exacte (insensible à la casse et aux accents)
    for domain in ALLOWED_DOMAINS:
        if norm == normalize_label_key(domain):
            return domain

    # Correspondance partielle : le nom normalisé est contenu dans la clé d'un alias
    for alias_key, domain in DOMAIN_ALIASES.items():
        if norm in alias_key or alias_key in norm:
            return domain

    return ""


def extract_ps_prefix(technical_name: Any) -> str:
    """Extrait le préfixe de module PeopleSoft depuis le nom technique."""
    name = normalize_ws(technical_name)
    if not name:
        return ""
    s = name.upper()
    s = re.sub(r"^[A-Z]+\.", "", s)     # retire le schema (ex: SYSADM.)
    s = re.sub(r"^PS[_]?", "", s)       # retire le préfixe PS_
    m = re.match(r"([A-Z][A-Z0-9]+)_", s)
    if m:
        return m.group(1)
    return s.split("_")[0][:8] if "_" in s else s[:8]


def ps_prefix_hint(technical_name: Any) -> tuple[str, str]:
    """Retourne (préfixe, classe_suggérée) depuis le nom technique."""
    prefix = extract_ps_prefix(technical_name)
    domain = PS_MODULE_PREFIX_MAP.get(prefix, "")
    return prefix, domain


def detect_csv_separator(path: str, fallback: str = ",") -> str:
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            sample = f.read(8192)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return fallback


def resolve_separator(sep_arg: str, input_path: str) -> str:
    if sep_arg == "auto":
        return detect_csv_separator(input_path)
    if sep_arg == r"\t":
        return "\t"
    return sep_arg


def read_csv_file(path: str, sep: str) -> pd.DataFrame:
    return pd.read_csv(path, sep=sep, low_memory=False)


def load_existing_output(output_path: str, sep: str) -> pd.DataFrame | None:
    if not os.path.exists(output_path):
        return None
    try:
        return pd.read_csv(output_path, sep=sep, low_memory=False)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Préparation des features pour le contexte LLM
# ---------------------------------------------------------------------------

def split_pipe(text: Any) -> list[str]:
    text = normalize_ws(text)
    if not text:
        return []
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in text:
        if ch == "[":
            depth += 1
            current.append(ch)
        elif ch == "]":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "|" and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_key_value_pipe(text: Any) -> OrderedDict[str, str]:
    out: OrderedDict[str, str] = OrderedDict()
    for part in split_pipe(text):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = normalize_ws(key)
        value = normalize_ws(value)
        if key and key not in out:
            out[key] = value
    return out


def truncate_text(text: str, max_chars: int) -> str:
    text = normalize_ws(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def clean_sample_value(sample_value: str, max_chars: int) -> str:
    sample_value = normalize_ws(sample_value)
    if not sample_value or sample_value.lower() == "nan":
        return ""
    sample_value = sample_value.strip("[]")
    atoms = [a.strip() for a in sample_value.split("|") if a.strip()]
    return truncate_text(" | ".join(atoms[:4]), max_chars)


def tokenize_identifier(text: str) -> list[str]:
    text = normalize_ws(text)
    if not text:
        return []
    text = text.replace(".", "_").replace("/", "_").replace("-", "_")
    text = re.sub(r"([a-z])([A-Z])", r"\1_\2", text)
    raw_tokens = [t.lower() for t in re.split(r"[^A-Za-z0-9]+", text) if t]
    expanded: list[str] = []
    for tok in raw_tokens:
        expanded.append(tok)
        if tok in ABBREVIATION_MAP:
            expanded.append(ABBREVIATION_MAP[tok])
    return expanded


def score_column_signal(name: str, dtype: str, semantic: str, sample: str) -> float:
    score = SEMANTIC_WEIGHTS.get(semantic, 0.8)
    informative = [
        t for t in tokenize_identifier(name)
        if t not in LOW_INFORMATION_NAME_TOKENS and len(t) > 1
    ]
    score += min(len(set(informative)), 4) * 0.45
    dtype = normalize_ws(dtype).upper()
    if dtype.startswith("DATE") or dtype.startswith("TIMESTAMP"):
        score += 0.4
    elif "CLOB" in dtype or "TEXT" in dtype:
        score += 0.5
    elif "NUMBER" in dtype or "DECIMAL" in dtype:
        score += 0.3
    if sample:
        score += 1.1
    if name.upper() in {"PROCESS_INSTANCE", "LANGUAGE_CD", "SETID",
                        "ROW_ADDED_DTTM", "ROW_LASTMANT_DTTM"}:
        score -= 0.6
    return round(score, 3)


def semantic_profile(column_records: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rec in column_records:
        sem = normalize_ws(rec.get("semantic"))
        if sem:
            counter[sem] += 1
    return dict(counter.most_common(12))


def type_profile(column_records: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rec in column_records:
        dtype = normalize_ws(rec.get("dtype")).upper()
        if not dtype:
            continue
        counter[dtype.split("(", 1)[0]] += 1
    return dict(counter.most_common(8))


def build_column_records(row: dict[str, Any], config: LLMConfig) -> list[dict[str, Any]]:
    names = split_pipe(row.get("column_names_text"))
    types = parse_key_value_pipe(row.get("column_type_signature_text"))
    semantics = parse_key_value_pipe(row.get("column_value_semantics_text"))
    samples = parse_key_value_pipe(row.get("column_sample_values_text"))

    ordered_names: list[str] = []
    seen: set[str] = set()
    for name in names + list(types.keys()) + list(semantics.keys()) + list(samples.keys()):
        if name and name not in seen:
            ordered_names.append(name)
            seen.add(name)

    records: list[dict[str, Any]] = []
    for name in ordered_names:
        dtype = types.get(name, "")
        semantic = semantics.get(name, "")
        sample = clean_sample_value(samples.get(name, ""), config.max_sample_chars)
        records.append({
            "name": name,
            "dtype": dtype,
            "semantic": semantic,
            "sample": sample,
            "score": score_column_signal(name, dtype, semantic, sample),
        })
    return records


def build_asset_info(row: dict[str, Any]) -> dict[str, Any]:
    """Construit la section 'asset' du contexte, incluant le hint PS."""
    tech_name = normalize_ws(row.get("technical_name"))
    source_ref = normalize_ws(row.get("source_ref"))

    prefix, hint_domain = ps_prefix_hint(tech_name or source_ref)

    src_tokens = tokenize_identifier(source_ref)
    cleaned_tokens = [
        t for t in src_tokens
        if t not in {"ps", "tbl", "tao", "lng", "sysadm"} and len(t) > 1
    ]

    asset: dict[str, Any] = {
        "source_ref": source_ref,
        "source_ref_tokens": list(dict.fromkeys(cleaned_tokens))[:16],
    }
    if tech_name:
        asset["technical_name"] = tech_name
    if prefix:
        asset["ps_prefix"] = prefix
    if hint_domain:
        asset["ps_prefix_hint"] = hint_domain

    return asset


def build_llm_context(
    row: dict[str, Any],
    config: LLMConfig,
    variant: str = "salient_first",
) -> dict[str, Any]:
    records = build_column_records(row, config)
    asset_info = build_asset_info(row)

    if variant == "semantic_first":
        sorted_records = sorted(
            records,
            key=lambda r: (
                SEMANTIC_WEIGHTS.get(r.get("semantic", ""), 0.8),
                r.get("score", 0.0),
            ),
            reverse=True,
        )
    elif variant == "samples_first":
        sorted_records = sorted(
            records,
            key=lambda r: (1 if r.get("sample") else 0, r.get("score", 0.0)),
            reverse=True,
        )
    else:
        sorted_records = sorted(records, key=lambda r: r.get("score", 0.0), reverse=True)

    top_records = sorted_records[: config.top_k_columns]

    context: dict[str, Any] = {
        "asset": asset_info,
        "feature_policy": {
            "samples_present": any(r.get("sample") for r in records),
            "total_columns": len(records),
            "columns_in_prompt": len(top_records),
            "variant": variant,
        },
        "profiles": {
            "semantic_profile": semantic_profile(records),
            "type_profile": type_profile(records),
        },
        "salient_columns": [
            {
                "name": r["name"],
                "type": r["dtype"] or "unknown",
                "semantic": r["semantic"] or "unknown",
                **({"sample_values": r["sample"]} if r["sample"] else {}),
            }
            for r in top_records
        ],
    }

    if len(json.dumps(context, ensure_ascii=False)) > config.max_context_chars:
        context["salient_columns"] = context["salient_columns"][: max(8, config.top_k_columns // 2)]

    return context


def build_user_prompt(row: dict[str, Any], config: LLMConfig, variant: str) -> str:
    context = build_llm_context(row, config, variant=variant)
    return (
        "Classify the asset into exactly one business domain (French name).\n"
        "Return STRICT JSON only.\n\n"
        "ASSET_CONTEXT=\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n"
    )


# ---------------------------------------------------------------------------
# Appels LLM
# ---------------------------------------------------------------------------

def extract_json_block(text: str) -> dict[str, Any]:
    text = normalize_ws(text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
    if match:
        obj = json.loads(match.group(0))
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"Cannot parse JSON from response: {text[:300]}")


def call_llm(
    config: LLMConfig,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "temperature": config.temperature if temperature is None else temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    # json_object n'est pas supporté par tous les backends Ollama —
    # on l'ajoute seulement si le modèle le supporte (ignoré silencieusement sinon).
    payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        url, headers=headers, json=payload, timeout=config.timeout_seconds
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return extract_json_block(content)


def single_prediction(
    row: dict[str, Any],
    config: LLMConfig,
    model: str,
    variant: str,
) -> dict[str, Any]:
    user_prompt = build_user_prompt(row, config=config, variant=variant)
    raw = call_llm(
        config=config, model=model,
        system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt,
    )
    domain = normalize_domain(raw.get("business_domain", ""))
    return {
        "model": model,
        "variant": variant,
        "business_domain": domain,
        "raw_response": str(raw.get("business_domain", "")),
    }


def adjudicate_votes(
    row: dict[str, Any],
    config: LLMConfig,
    votes: list[dict[str, Any]],
) -> str:
    context = build_llm_context(row, config, variant="salient_first")
    payload = {
        "context": context,
        "candidate_votes": [
            {"model": v.get("model"), "variant": v.get("variant"),
             "business_domain": v.get("business_domain")}
            for v in votes
        ],
        "instruction": "Choose the single best final business_domain.",
    }
    raw = call_llm(
        config=config, model=config.models[0],
        system_prompt=ADJUDICATOR_SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    return normalize_domain(raw.get("business_domain", ""))


# ---------------------------------------------------------------------------
# Fallback heuristique PS
# ---------------------------------------------------------------------------

def apply_ps_fallback(row: dict[str, Any]) -> str:
    """
    Tente de déterminer la classe via le préfixe PeopleSoft.
    Retourne la classe si trouvée, sinon chaîne vide.
    """
    for field_name in ("technical_name", "source_ref"):
        _, domain = ps_prefix_hint(row.get(field_name, ""))
        if domain:
            return domain
    return ""


# ---------------------------------------------------------------------------
# Consensus + fallback
# ---------------------------------------------------------------------------

def predict_with_consensus(row: dict[str, Any], config: LLMConfig) -> dict[str, Any]:
    votes: list[dict[str, Any]] = []

    variants = ["salient_first", "semantic_first"]
    if normalize_ws(row.get("column_sample_values_text")):
        variants.append("samples_first")

    planned: list[tuple[str, str]] = [
        (m, v) for m in config.models for v in variants
    ]

    for model, variant in planned:
        for attempt in range(1, config.max_retries + 1):
            try:
                pred = single_prediction(row=row, config=config, model=model, variant=variant)
                votes.append(pred)
                time.sleep(config.sleep_between_calls)
                break
            except Exception as exc:
                if attempt < config.max_retries:
                    time.sleep(1.2 * attempt)
                else:
                    votes.append({
                        "model": model,
                        "variant": variant,
                        "business_domain": "",
                        "error": str(exc)[:200],
                    })

    valid_votes = [v for v in votes if v.get("business_domain") in DOMAIN_SET]
    counter: Counter[str] = Counter(v["business_domain"] for v in valid_votes)

    # Pas de vote valide → fallback PS puis Finance par défaut
    if not counter:
        fallback = apply_ps_fallback(row)
        prefix, _ = ps_prefix_hint(row.get("technical_name") or row.get("source_ref", ""))
        return {
            "business_domain": fallback or "Finance & Comptabilité",
            "llm_consensus_score": 0.0,
            "llm_votes_json": json.dumps(votes, ensure_ascii=False),
            "llm_models_used": ",".join(config.models),
            "llm_prompt_version": config.prompt_version,
            "llm_status": f"error_fallback_ps:{prefix}" if fallback else "error_fallback_default",
            "needs_review": True,
            "ps_prefix": prefix,
        }

    winner, winner_count = counter.most_common(1)[0]
    consensus_score = winner_count / max(len(valid_votes), 1)

    # Adjudication sur égalité ou faible consensus
    if config.adjudicate_on_tie and (
        list(counter.values()).count(winner_count) > 1 or consensus_score < LOW_CONSENSUS_THRESHOLD
    ):
        try:
            adjudicated = adjudicate_votes(row=row, config=config, votes=votes)
            if adjudicated in DOMAIN_SET:
                winner = adjudicated
        except Exception:
            pass

    # Vérification par fallback PS : si le préfixe PS contredit le winner
    # avec un score très élevé et un consensus faible, on signale la révision.
    prefix, ps_domain = ps_prefix_hint(row.get("technical_name") or row.get("source_ref", ""))
    ps_disagrees = bool(ps_domain) and ps_domain != winner

    needs_review = consensus_score < LOW_CONSENSUS_THRESHOLD or ps_disagrees

    return {
        "business_domain": winner,
        "llm_consensus_score": round(consensus_score, 4),
        "llm_votes_json": json.dumps(votes, ensure_ascii=False),
        "llm_models_used": ",".join(config.models),
        "llm_prompt_version": config.prompt_version,
        "llm_status": "ok",
        "needs_review": needs_review,
        "ps_prefix": prefix,
    }


# ---------------------------------------------------------------------------
# Validation et logique de saut
# ---------------------------------------------------------------------------

def validate_input_columns(df: pd.DataFrame) -> None:
    required = ["source_ref", "column_names_text"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes requises manquantes dans le CSV d'entrée: {missing}")


def is_valid_domain(value: Any) -> bool:
    return normalize_domain(value) in DOMAIN_SET


def is_legacy_other(value: Any) -> bool:
    norm = normalize_label_key(value)
    return norm in LEGACY_OTHER_VALUES


def should_skip_row(
    row: dict[str, Any],
    skip_existing: bool,
    force_reannotate_other: bool,
) -> bool:
    if not skip_existing:
        return False
    current = normalize_ws(row.get("business_domain", ""))
    if not current:
        return False
    if force_reannotate_other and is_legacy_other(current):
        return False
    return is_valid_domain(current)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Annotation LLM de la base d'entraînement — 6 classes métier sans 'Other', "
            "avec fallback heuristique PeopleSoft et flag needs_review."
        )
    )
    parser.add_argument(
        "--input",
        default="exports/dataset_asset_ml_run_5_for_labeling_sample_20000_enriched_annotated.csv",
        help="Chemin du CSV source",
    )
    parser.add_argument(
        "--output",
        default="exports/dataset_asset_ml_training_v5_6classes.csv",
        help="Chemin du CSV annoté en sortie",
    )
    parser.add_argument("--sep", default="auto",
                        help="Séparateur CSV : auto, ',', ';', '\\t', '|'")
    parser.add_argument("--limit", type=int, default=None,
                        help="Nombre maximum de lignes à traiter")
    parser.add_argument("--resume", action="store_true",
                        help="Reprendre depuis le fichier de sortie existant")
    parser.add_argument("--id-column", default="asset_id",
                        help="Colonne identifiant unique")
    parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        help="URL de base du LLM compatible OpenAI (Ollama, LM Studio…)",
    )
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", "ollama"),
                        help="Clé API (factice pour Ollama)")
    parser.add_argument(
        "--models",
        default=os.getenv("LLM_MODELS", "qwen2.5:14b,mistral"),
        help="Modèles séparés par virgule (ex: qwen2.5:14b,mistral)",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=90,
                        help="Timeout requête en secondes")
    parser.add_argument("--sleep", type=float, default=0.2,
                        help="Pause entre appels LLM (secondes)")
    parser.add_argument("--top-k-columns", type=int, default=24,
                        help="Nombre max de colonnes saillantes envoyées au LLM")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Sauter les lignes déjà annotées avec une classe valide")
    parser.add_argument(
        "--force-reannotate-other", action="store_true",
        help="Ré-annoter les lignes dont business_domain est 'Other' ou vide, "
             "même si --skip-existing est actif",
    )

    args = parser.parse_args()

    models = [m.strip() for m in str(args.models).split(",") if m.strip()]
    if not models:
        raise ValueError("Au moins un modèle requis via --models")

    resolved_sep = resolve_separator(args.sep, args.input)

    config = LLMConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        models=models,
        temperature=args.temperature,
        timeout_seconds=args.timeout,
        sleep_between_calls=args.sleep,
        top_k_columns=args.top_k_columns,
    )

    df = read_csv_file(args.input, sep=resolved_sep)
    validate_input_columns(df)

    if args.id_column not in df.columns:
        raise ValueError(f"Colonne identifiant manquante : {args.id_column}")

    if args.limit is not None:
        df = df.head(args.limit).copy()

    already_done_ids: set[Any] = set()
    if args.resume:
        existing = load_existing_output(args.output, sep=resolved_sep)
        if existing is not None and args.id_column in existing.columns:
            already_done_ids = set(existing[args.id_column].dropna().tolist())

    domain_counter: Counter[str] = Counter()
    output_exists = os.path.exists(args.output)
    write_header = not output_exists or not args.resume

    with open(args.output, "a" if args.resume else "w",
              newline="", encoding="utf-8") as f:
        writer: csv.DictWriter | None = None

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            row_id = row_dict.get(args.id_column)

            if row_id in already_done_ids:
                continue

            if should_skip_row(
                row_dict,
                skip_existing=args.skip_existing,
                force_reannotate_other=args.force_reannotate_other,
            ):
                # Conserver et normaliser l'annotation existante
                enriched = dict(row_dict)
                current_domain = normalize_domain(row_dict.get("business_domain", ""))
                enriched["business_domain"] = current_domain or row_dict.get("business_domain", "")
                prefix, _ = ps_prefix_hint(row_dict.get("technical_name") or row_dict.get("source_ref", ""))
                enriched.setdefault("ps_prefix", prefix)
                enriched.setdefault("needs_review", False)
                enriched["llm_status"] = "skipped_valid_domain"
                enriched["llm_prompt_version"] = config.prompt_version
                enriched["llm_models_used"] = ",".join(config.models)
                enriched.setdefault("llm_consensus_score", "")
                enriched.setdefault("llm_votes_json", "")
            else:
                annotation = predict_with_consensus(row_dict, config=config)
                enriched = dict(row_dict)
                enriched.update(annotation)

            domain_counter[enriched.get("business_domain", "")] += 1

            if writer is None:
                fieldnames = list(enriched.keys())
                writer = csv.DictWriter(
                    f, fieldnames=fieldnames,
                    delimiter=resolved_sep,
                    quoting=csv.QUOTE_MINIMAL,
                    extrasaction="ignore",
                )
                if write_header:
                    writer.writeheader()

            writer.writerow(enriched)
            f.flush()

            print(
                f"[{idx + 1}/{len(df)}] id={row_id}"
                f"  domain={enriched.get('business_domain', '')}"
                f"  consensus={enriched.get('llm_consensus_score', '')}"
                f"  review={enriched.get('needs_review', '')}"
                f"  ps={enriched.get('ps_prefix', '')}"
                f"  status={enriched.get('llm_status', '')}"
            )

            time.sleep(config.sleep_between_calls)

    print("\n=== Distribution finale ===")
    total = sum(domain_counter.values())
    for domain in ALLOWED_DOMAINS + [""]:
        cnt = domain_counter.get(domain, 0)
        if cnt:
            print(f"  {domain or '(vide)':45s} {cnt:5d}  ({cnt / total * 100:.1f}%)")


if __name__ == "__main__":
    main()
