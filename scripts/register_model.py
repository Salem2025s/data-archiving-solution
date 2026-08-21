"""Registre de modèles — enregistre un modèle entraîné dans un registre versionné.

Brique du cycle CI/CD (C5.3.2) : à chaque nouveau modèle validé, on enregistre
sa version, ses métriques, son empreinte (hash) et le commit Git, dans
`artifacts/model_registry.json`. Le registre trace la lignée des modèles et
sert de source à la promotion en production.

Usage :
    python -m scripts.register_model \
        --model LLM/artifacts_business_domain/production_pipeline_latest.joblib \
        --version v3.4-human --algo "LinearSVC+Platt" \
        --macro-f1 0.869 --accuracy 0.907 --promote

    python -m scripts.register_model --list
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "artifacts" / "model_registry.json"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "file-absent"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load() -> list[dict]:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return []


def _save(entries: list[dict]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def register(args: argparse.Namespace) -> None:
    entries = _load()
    model_path = Path(args.model)
    entry = {
        "version": args.version,
        "algo": args.algo,
        "path": args.model,
        "sha256_16": _file_hash(model_path),
        "metrics": {"macro_f1": args.macro_f1, "accuracy": args.accuracy, "ece": args.ece},
        "git_commit": _git_commit(),
        "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": "production" if args.promote else "staging",
    }
    # une seule version en 'production' à la fois
    if args.promote:
        for e in entries:
            if e.get("stage") == "production":
                e["stage"] = "archived"
    # dédoublonnage par (version, hash)
    entries = [e for e in entries if (e["version"], e["sha256_16"]) != (entry["version"], entry["sha256_16"])]
    entries.append(entry)
    _save(entries)
    print(f"[OK] Modèle enregistré : {entry['version']} ({entry['stage']}) — "
          f"macro-F1 {entry['metrics']['macro_f1']} · commit {entry['git_commit']}")
    print(f"     Registre : {REGISTRY.relative_to(ROOT)} ({len(entries)} entrées)")


def list_registry(_: argparse.Namespace) -> None:
    entries = _load()
    if not entries:
        print("Registre vide.")
        return
    print(f"=== Registre de modèles ({len(entries)} entrées) ===")
    for e in entries:
        m = e["metrics"]
        flag = "★" if e.get("stage") == "production" else " "
        print(f"  {flag} {e['version']:<18} {e['algo']:<18} "
              f"F1={m.get('macro_f1')} acc={m.get('accuracy')} "
              f"[{e['stage']}] {e['registered_at'][:10]} {e['git_commit']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Registre de modèles ML")
    ap.add_argument("--list", action="store_true", help="afficher le registre")
    ap.add_argument("--model", type=str, help="chemin du modèle (.joblib / bundle)")
    ap.add_argument("--version", type=str, help="version du modèle (ex. v3.4-human)")
    ap.add_argument("--algo", type=str, default="", help="algorithme (ex. LinearSVC+Platt)")
    ap.add_argument("--macro-f1", type=float, default=None)
    ap.add_argument("--accuracy", type=float, default=None)
    ap.add_argument("--ece", type=float, default=None)
    ap.add_argument("--promote", action="store_true", help="promouvoir en production")
    args = ap.parse_args()

    if args.list:
        list_registry(args)
    elif args.model and args.version:
        register(args)
    else:
        ap.error("préciser --list, ou --model et --version pour enregistrer")


if __name__ == "__main__":
    main()
