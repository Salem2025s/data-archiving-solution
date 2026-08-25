"""Helpers partagés du dashboard de gouvernance (connexion, cache, requêtes,
style, palette, commandes). Importé par app/streamlit_dashboard.py.
"""
from __future__ import annotations

import importlib.util as _ilu  # noqa: F401  (utilisé dans _load_classifier)
import json as _json  # noqa: F401
import subprocess  # noqa: F401
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402,F401

from src.config.settings import get_settings  # noqa: E402,F401

# ---------------------------------------------------------------------------
# Design system — CSS global injecté une seule fois
# ---------------------------------------------------------------------------
def _inject_css() -> None:
    st.markdown(
        """
        <style>
        /* ---------- Layout général ---------- */
        .main .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }
        #MainMenu, footer { visibility: hidden; }

        /* ---------- Typographie ---------- */
        html, body, [class*="css"] { font-family: "Inter", "Segoe UI", system-ui, sans-serif; }
        h1, h2, h3 { color: #0F172A; letter-spacing: -0.01em; }

        /* ---------- En-tête de page (hero) ---------- */
        .page-header {
            display: flex; align-items: center; gap: 18px;
            padding: 22px 26px; margin-bottom: 24px;
            background: linear-gradient(120deg, #2563EB 0%, #4F46E5 100%);
            border-radius: 16px; color: #fff;
            box-shadow: 0 10px 30px -12px rgba(37,99,235,.55);
        }
        .page-header-icon { font-size: 2.4rem; line-height: 1; }
        .page-header-title { color: #fff !important; margin: 0; font-size: 1.7rem; font-weight: 700; }
        .page-header-sub { color: rgba(255,255,255,.88); margin: 4px 0 0; font-size: .95rem; }

        /* ---------- Cartes métriques ---------- */
        [data-testid="stMetric"] {
            background: #FFFFFF; border: 1px solid #E6EAF2;
            border-radius: 14px; padding: 16px 18px;
            box-shadow: 0 1px 3px rgba(16,24,40,.06);
            transition: box-shadow .18s ease, transform .18s ease;
        }
        [data-testid="stMetric"]:hover {
            box-shadow: 0 8px 24px -10px rgba(37,99,235,.35);
            transform: translateY(-2px);
        }
        [data-testid="stMetricLabel"] { color: #64748B; font-weight: 600; }
        [data-testid="stMetricValue"] { color: #0F172A; font-weight: 700; }

        /* ---------- Boutons ---------- */
        .stButton > button, .stDownloadButton > button {
            border-radius: 10px; font-weight: 600; border: 1px solid #E2E8F0;
            transition: all .15s ease;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            border-color: #2563EB; transform: translateY(-1px);
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(120deg, #2563EB, #4F46E5); border: none;
        }

        /* ---------- Sidebar (slate sombre raffiné) ---------- */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #111C33 0%, #0B1220 100%);
            border-right: 1px solid #1E293B;
        }
        [data-testid="stSidebar"] * { color: #CBD5E1; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
        .sidebar-brand {
            padding: 4px 2px 12px; margin-bottom: 10px;
            border-bottom: 1px solid #1E293B;
        }
        .sidebar-brand h2 { color: #fff !important; font-size: 1.12rem; margin: 0; font-weight: 700; letter-spacing: -.01em; }
        .sidebar-brand p  { color: #7C8BA5 !important; font-size: .76rem; margin: 4px 0 0; }
        .sidebar-badge {
            display: inline-flex; align-items: center; gap: 8px;
            background: rgba(37,99,235,.12); border: 1px solid rgba(37,99,235,.35);
            border-radius: 999px; padding: 6px 13px; font-size: .8rem; font-weight: 600;
            color: #E2E8F0 !important; margin: 2px 0 4px;
        }
        .sidebar-badge .dot { width: 8px; height: 8px; border-radius: 50%; }
        .dot-on  { background: #22C55E; box-shadow: 0 0 9px #22C55E; }
        .dot-off { background: #EF4444; box-shadow: 0 0 9px #EF4444; }

        /* Navigation → menu (pas des boutons radio) */
        [data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            padding: 10px 13px; border-radius: 10px; margin: 0;
            border-left: 3px solid transparent;
            transition: background .15s ease, border-color .15s ease; cursor: pointer;
        }
        /* Masque la pastille radio pour un vrai rendu de menu */
        [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
        [data-testid="stSidebar"] [role="radiogroup"] label p {
            font-size: .93rem; font-weight: 500; color: #CBD5E1;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover { background: #1B2740; }
        /* Item actif : fond bleuté + barre d'accent + texte blanc */
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: rgba(37,99,235,.18);
            border-left-color: #2563EB;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
            color: #FFFFFF; font-weight: 600;
        }

        /* Bouton dans la sidebar sombre → contraste lisible */
        [data-testid="stSidebar"] .stButton > button {
            background: #1B2740; color: #E2E8F0; border: 1px solid #2A3B5C;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: #24344F; border-color: #2563EB; color: #fff;
        }

        /* ---------- Expanders & tableaux ---------- */
        [data-testid="stExpander"] {
            border: 1px solid #E6EAF2; border-radius: 12px; overflow: hidden;
        }
        [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }

        /* ---------- Divider plus discret ---------- */
        hr { margin: 1.4rem 0; border-color: #E6EAF2; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "", icon: str = "📊") -> None:
    """En-tête de section cohérent (hero avec dégradé)."""
    st.markdown(
        f"""
        <div class="page-header">
          <div class="page-header-icon">{icon}</div>
          <div>
            <div class="page-header-title">{title}</div>
            <div class="page-header-sub">{subtitle}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )




# ---------------------------------------------------------------------------
# Accès base (lecture seule, mis en cache)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    # connect_timeout=3 : abandon immédiat si PostgreSQL n'est pas joignable
    # pool_timeout=5    : n'attend pas plus de 5 s pour obtenir une connexion du pool
    return create_engine(
        get_settings().postgresql_url,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 3},
    )


@st.cache_data(ttl=900, show_spinner=False)
def run_query(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


def safe_query(sql: str) -> pd.DataFrame:
    try:
        return run_query(sql)
    except Exception as exc:
        st.warning(f"Base indisponible : {exc}")
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def run_query_params(sql: str, params: tuple[tuple, ...]) -> pd.DataFrame:
    """Parameterized query — params is a tuple of (name, value) pairs (hashable for cache)."""
    p = dict(params)
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=p)


def safe_query_params(sql: str, params: dict) -> pd.DataFrame:
    try:
        return run_query_params(sql, tuple(sorted(params.items())))
    except Exception as exc:
        st.warning(f"Base indisponible : {exc}")
        return pd.DataFrame()


# Palette de couleurs cohérente sur tout le dashboard
_PAL: dict[str, str] = {
    "Finance & Contrôle":                      "#1f77b4",
    "IT & Sécurité":                           "#8c564b",
    "Supply Chain / Logistique / Production":  "#d62728",
    "Achats & Fournisseurs":                   "#ff7f0e",
    "Ventes & Clients":                        "#9467bd",
    "RH":                                      "#2ca02c",
    "Other":                                   "#7f7f7f",
}


# ---------------------------------------------------------------------------
# Requêtes SQL sauvegardées (persistées dans un fichier JSON local)
# ---------------------------------------------------------------------------
import json as _json

_SAVED_QUERIES_PATH = _PROJECT_ROOT / ".streamlit" / "saved_queries.json"


def load_saved_queries() -> dict[str, dict[str, str]]:
    """Charge les requêtes sauvegardées ({'oracle': {...}, 'postgres': {...}})."""
    if _SAVED_QUERIES_PATH.exists():
        try:
            data = _json.loads(_SAVED_QUERIES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def write_saved_queries(data: dict[str, dict[str, str]]) -> None:
    """Écrit le catalogue des requêtes sauvegardées sur disque."""
    _SAVED_QUERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SAVED_QUERIES_PATH.write_text(
        _json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@st.cache_resource(show_spinner="Chargement du modèle XLM-R v3…")
def _load_classifier(apply_offsets: bool):
    """Load the XLM-R v3 ONNX classifier.  Cached per (apply_offsets) value."""
    import importlib.util as _ilu

    xlmr_dir = _PROJECT_ROOT / "artifacts" / "xlmr_v3"
    if not (xlmr_dir / "artifacts" / "model.onnx").exists():
        raise FileNotFoundError(f"Modèle introuvable : {xlmr_dir / 'artifacts' / 'model.onnx'}")

    # Register features module under its bare name so predict.py's
    # `from features import ...` resolves through sys.modules correctly.
    if "features" not in sys.modules:
        feat_spec = _ilu.spec_from_file_location("features", xlmr_dir / "features.py")
        feat_mod = _ilu.module_from_spec(feat_spec)
        sys.modules["features"] = feat_mod
        feat_spec.loader.exec_module(feat_mod)  # type: ignore[union-attr]

    pred_spec = _ilu.spec_from_file_location("xlmr_v3_predict", xlmr_dir / "predict.py")
    pred_mod = _ilu.module_from_spec(pred_spec)
    pred_spec.loader.exec_module(pred_mod)  # type: ignore[union-attr]

    return pred_mod.DomainClassifier(
        artifacts_dir=xlmr_dir / "artifacts",
        apply_offsets=apply_offsets,
    )


def run_command(label: str, module: str, extra_args: list[str] | None = None) -> None:
    """Exécute `python -m <module>` en sous-processus, logs streamés dans l'UI."""
    cmd = [sys.executable, "-m", module, *(extra_args or [])]
    with st.status(f"{label} — en cours…", expanded=True) as status:
        placeholder = st.empty()
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            status.update(label=f"{label} — échec de lancement", state="error")
            st.error(str(exc))
            return

        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))
            placeholder.code("\n".join(lines[-300:]), language="log")
        proc.wait()

        if proc.returncode == 0:
            status.update(label=f"{label} — terminé ✅", state="complete")
            st.cache_data.clear()  # invalide TOUT le cache data (run_query + run_query_params)
        else:
            status.update(label=f"{label} — échec (code {proc.returncode}) ❌", state="error")
