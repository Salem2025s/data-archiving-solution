from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


DOMAIN_HINT_PATTERNS: dict[str, re.Pattern[str]] = {
    "HR": re.compile(
        r"\b(hr|human resources|employee|empl|emplid|payroll|benefit|job|absence|conge|salaire)\b",
        flags=re.IGNORECASE,
    ),
    "Finance": re.compile(
        r"\b(finance|ledger|account|acct|invoice|payment|budget|journal|asset|depr|tax|ap|ar|gl)\b",
        flags=re.IGNORECASE,
    ),
    "Sales": re.compile(
        r"\b(sales|customer|client|crm|opportunity|quote|deal|booking)\b",
        flags=re.IGNORECASE,
    ),
    "Procurement": re.compile(
        r"\b(procurement|purchase|purchasing|supplier|vendor|rfq|sourcing)\b",
        flags=re.IGNORECASE,
    ),
    "Supply Chain": re.compile(
        r"\b(supply chain|inventory|stock|shipment|warehouse|logistics|delivery|route)\b",
        flags=re.IGNORECASE,
    ),
    "IT": re.compile(
        r"\b(it|sysadm|system|security|auth|permission|role|user|portal|menu|page|config|server|prcs)\b",
        flags=re.IGNORECASE,
    ),
    "Risk": re.compile(
        r"\b(risk|control|compliance|incident|mitigation|policy)\b",
        flags=re.IGNORECASE,
    ),
    "Marketing": re.compile(
        r"\b(marketing|campaign|lead|segment|audience|conversion|promo)\b",
        flags=re.IGNORECASE,
    ),
}

PS_MODULE_PREFIXES: dict[str, str] = {
    "GL": "Finance",
    "AP": "Finance",
    "AR": "Finance",
    "AM": "Finance",
    "BI": "Finance",
    "TR": "Finance",
    "EX": "Finance",
    "HR": "HR",
    "JOB": "HR",
    "PERSON": "HR",
    "BEN": "HR",
    "PAY": "HR",
    "ABS": "HR",
    "COMP": "HR",
    "PO": "Procurement",
    "EP": "Procurement",
    "RFQ": "Procurement",
    "CON": "Procurement",
    "VND": "Procurement",
    "IN": "Supply Chain",
    "PL": "Supply Chain",
    "SF": "Supply Chain",
    "MG": "Supply Chain",
    "PROD": "Supply Chain",
    "SA": "Sales",
    "OM": "Sales",
    "CRM": "Sales",
    "PRCS": "IT",
    "PSAUTH": "IT",
    "PSOPR": "IT",
    "PSROLE": "IT",
    "PT": "IT",
    "PSMENU": "IT",
}


SYSTEM_PROMPT = """You are a senior data governance expert specialized in enterprise data classification.

Your task is to classify a data asset into a business domain.

You must choose ONLY ONE domain from this list:
- HR
- Finance
- Sales
- Procurement
- Supply Chain
- IT
- Risk
- Marketing
- Other

Instructions:
1. Analyze all available columns metadata carefully (such as technical_name, source_ref, column details, types, sizes, dataset shape, etc.).
2. Detect business meaning based on common enterprise naming conventions and semantic patterns in the column details:
   - HR: employee, payroll, job, person
   - Finance: account, ledger, invoice, payment
   - Sales: customer, order, revenue
   - Procurement: supplier, purchase, vendor
   - Supply Chain: inventory, stock, shipment
3. Base your decision on the global context brought by all these properties.
4. Use "Other" only as a last resort when metadata is truly sparse or conflicting.
5. If at least one strong signal exists, choose the best matching domain even with lower confidence.
6. Confidence policy:
    - 0.75-1.00: multiple strong aligned signals
    - 0.45-0.74: one strong signal
    - 0.20-0.44: weak but plausible signal
    - keep "Other" mostly for genuinely insufficient evidence
7. Do NOT invent domains outside the list.
8. Be concise and precise.
9. Output STRICT JSON ONLY.

Output format:
{
  "business_domain": "...",
  "confidence": 0.0,
  "reason": "short explanation"
}
"""


ALLOWED_DOMAINS = {
    "HR",
    "Finance",
    "Sales",
    "Procurement",
    "Supply Chain",
    "IT",
    "Risk",
    "Marketing",
    "Other",
}


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0
    timeout_seconds: int = 60
    max_retries: int = 3
    sleep_between_calls: float = 0.2


def build_user_prompt(row: dict[str, Any]) -> str:
    prompt_lines = ["INPUT DATA:"]
    for key, value in row.items():
        # Ignorer les colonnes de gestion ou vides
        if key in ("run_id", "asset_id", "business_domain_label", "labeling_notes"):
            continue
        # Ignorer les valeurs nulles (nan de pandas)
        if pd.isna(value) or str(value).strip() == "":
            continue
        # Formater correctement la clé et la valeur
        prompt_lines.append(f"- {key}: {value}")
        
    return "\n".join(prompt_lines) + "\n"


def extract_json_block(text: str) -> dict[str, Any]:
    text = text.strip()

    # Cas direct
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Cas où le modèle entoure le JSON de texte parasite
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj

    raise ValueError(f"Impossible de parser un JSON valide depuis la réponse: {text[:300]}")


def normalize_response(obj: dict[str, Any]) -> dict[str, Any]:
    business_domain = str(obj.get("business_domain", "Other") or "Other").strip()
    confidence = obj.get("confidence", 0.0)
    reason = str(obj.get("reason", "") or "").strip()

    if business_domain not in ALLOWED_DOMAINS:
        business_domain = "Other"

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))

    return {
        "business_domain": business_domain,
        "confidence": confidence,
        "reason": reason[:500],
    }


def extract_prefix(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.upper().strip()
    text = re.sub(r"^[A-Z]+\.", "", text)
    text = re.sub(r"^PS[_]?", "", text)
    match = re.match(r"([A-Z]+)_", text)
    if match:
        return match.group(1)
    token = text.split("_")[0]
    return token[:6]


def infer_domain_from_metadata(row: dict[str, Any]) -> tuple[str | None, str]:
    text_parts: list[str] = []
    for key in (
        "technical_name",
        "source_ref",
        "column_names_text",
        "column_type_signature_text",
        "column_value_semantics_text",
        "column_sample_values_text",
        "column_observed_pattern_text",
    ):
        value = row.get(key)
        if value is not None:
            text_parts.append(str(value))

    merged_text = " ".join(text_parts)
    scores = {domain: 0 for domain in DOMAIN_HINT_PATTERNS}
    evidence: list[str] = []

    for domain, pattern in DOMAIN_HINT_PATTERNS.items():
        hits = len(pattern.findall(merged_text))
        if hits > 0:
            scores[domain] += hits

    for field in ("technical_name", "source_ref"):
        prefix = extract_prefix(row.get(field))
        mapped_domain = PS_MODULE_PREFIXES.get(prefix)
        if mapped_domain:
            scores[mapped_domain] += 2
            evidence.append(f"{field}_prefix={prefix}")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_domain, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if top_score < 2 or top_score == second_score:
        return None, ""

    detail = f"top_score={top_score}"
    if evidence:
        detail = f"{detail};" + ";".join(evidence[:3])
    return top_domain, detail


def call_openai_compatible_chat(
    config: LLMConfig,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    url = f"{config.base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return extract_json_block(content)


def annotate_row(row: dict[str, Any], config: LLMConfig) -> dict[str, Any]:
    user_prompt = build_user_prompt(row)

    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            raw = call_openai_compatible_chat(config, SYSTEM_PROMPT, user_prompt)
            normalized = normalize_response(raw)

            if normalized["business_domain"] == "Other":
                inferred_domain, evidence = infer_domain_from_metadata(row)
                if inferred_domain is not None:
                    normalized["business_domain"] = inferred_domain
                    normalized["confidence"] = max(normalized["confidence"], 0.45)
                    if evidence:
                        existing_reason = normalized["reason"].strip()
                        fallback_reason = f"heuristic_fallback:{evidence}"
                        normalized["reason"] = (
                            f"{existing_reason} | {fallback_reason}" if existing_reason else fallback_reason
                        )

            return normalized
        except Exception as exc:
            last_error = exc
            if attempt < config.max_retries:
                time.sleep(1.5 * attempt)

    return {
        "business_domain": "Other",
        "confidence": 0.0,
        "reason": f"annotation_error: {str(last_error)[:300]}",
    }


def load_existing_output(output_path: str) -> pd.DataFrame | None:
    if not os.path.exists(output_path):
        return None
    return pd.read_csv(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch annotation LLM pour dataset_asset_ml exporté en CSV."
    )
    parser.add_argument(
        "--input", 
        default="dataset_asset_ml_run_5_for_labeling_sample_5000_enriched.csv", 
        help="Chemin du CSV source"
    )
    parser.add_argument(
        "--output", 
        default="dataset_asset_ml_run_5_for_labeling_sample_5000_enriched_annotated.csv", 
        help="Chemin du CSV annoté"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nombre max de lignes à traiter",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reprendre à partir du fichier output existant",
    )
    parser.add_argument(
        "--id-column",
        default="asset_id",
        help="Colonne identifiant unique",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        help="Base URL OpenAI-compatible du LLM local",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LLM_API_KEY", "ollama"),
        help="Clé API factice ou réelle selon backend",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", "mistral"),
        help="Nom du modèle local",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature LLM",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Pause entre appels",
    )

    args = parser.parse_args()

    config = LLMConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        temperature=args.temperature,
        sleep_between_calls=args.sleep,
    )

    df = pd.read_csv(args.input)

    # On vérifie seulement que des informations minimales sont là
    required_cols = ["technical_name", "source_ref"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes minimales manquantes dans le CSV d'entrée: {missing}")

    if args.id_column not in df.columns:
        raise ValueError(f"Colonne id absente: {args.id_column}")

    if args.limit is not None:
        df = df.head(args.limit).copy()

    already_done_ids: set[Any] = set()
    existing_output = None

    if args.resume:
        existing_output = load_existing_output(args.output)
        if existing_output is not None and args.id_column in existing_output.columns:
            already_done_ids = set(existing_output[args.id_column].dropna().tolist())

    output_exists = os.path.exists(args.output)
    write_header = not output_exists or not args.resume

    with open(args.output, "a" if args.resume else "w", newline="", encoding="utf-8") as f:
        writer = None

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            row_id = row_dict.get(args.id_column)

            if row_id in already_done_ids:
                continue

            annotation = annotate_row(row_dict, config)

            merged = dict(row_dict)
            merged.update(annotation)

            if writer is None:
                fieldnames = list(merged.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()

            writer.writerow(merged)
            f.flush()

            print(
                f"[{idx + 1}/{len(df)}] "
                f"asset_id={row_id} "
                f"-> {annotation['business_domain']} "
                f"(confidence={annotation['confidence']:.2f})"
            )

            time.sleep(config.sleep_between_calls)


if __name__ == "__main__":
    main()