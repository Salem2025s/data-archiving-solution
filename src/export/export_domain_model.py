"""Export serving domain model views to a multi-sheet Excel workbook.

Reads three serving-layer objects (all on MAX run_id):
  - serving.mv_domain_profile      → sheet "Domain Profile"
  - serving.mv_domain_dependency   → sheet "Domain Shared Keys"
  - serving.v_archivability_by_domain → sheet "Top Archival Candidates"

Output: exports/domain_model_run<N>.xlsx  (N = current MAX run_id)
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.utils.logging_utils import configure_logging

PROFILE_SQL = """
SELECT
    domain_label,
    asset_count,
    ROUND(total_size_mb::numeric, 2)      AS total_size_mb,
    archival_candidates,
    ROUND(estimated_gain_mb::numeric, 2)  AS estimated_gain_mb,
    avg_archival_score,
    avg_roi_score,
    avg_lineage_out,
    avg_nullable_ratio,
    assets_without_description,
    risk_level
FROM serving.mv_domain_profile
ORDER BY asset_count DESC
"""

DEPENDENCY_SQL = """
SELECT
    source_domain,
    target_domain,
    bridge_field,
    shared_asset_count
FROM serving.mv_domain_dependency
ORDER BY shared_asset_count DESC, bridge_field
"""

CANDIDATES_SQL = """
SELECT
    domain_label,
    technical_name,
    business_name,
    source_system,
    asset_type,
    ROUND(archival_candidate_score::numeric, 2) AS archival_candidate_score,
    ROUND(roi_score::numeric, 2)                AS roi_score,
    ROUND(size_mb::numeric, 2)                  AS size_mb,
    lineage_out_count,
    row_count,
    domain_rank
FROM serving.v_archivability_by_domain
ORDER BY domain_label, domain_rank
"""

ARCHIVING_SUMMARY_SQL = """
SELECT
    domain_label,
    recommended_strategy,
    strategy_label,
    retention_years,
    asset_count,
    total_size_mb
FROM serving.v_archiving_policy_summary
ORDER BY domain_label, recommended_strategy
"""

ARCHIVING_POLICY_SQL = """
SELECT
    strategy_code,
    strategy_label,
    description,
    handling,
    retention_years,
    priority
FROM serving.dim_archiving_policy
ORDER BY priority
"""

ARCHIVING_ACTIONABLE_SQL = """
SELECT
    domain_label,
    technical_name,
    business_name,
    recommended_strategy,
    ROUND(size_mb::numeric, 2) AS size_mb,
    row_count,
    age_band,
    sensitivity_level,
    lineage_out_count,
    rationale
FROM serving.mv_archiving_recommendation
WHERE recommended_strategy IN ('ARCHIVAGE_FROID', 'ARCHIVAGE_CHIFFRE', 'COMPRESSION')
ORDER BY size_mb DESC
LIMIT 1000
"""

COST_BY_DOMAIN_SQL = """
SELECT
    domain_label,
    total_size_gb,
    current_cost_usd_year,
    annual_savings_usd,
    savings_pct,
    cost_share_pct,
    cumulative_cost_pct,
    cost_rank,
    optimization_potential
FROM serving.v_cost_by_domain
ORDER BY cost_rank
"""

N1_COMPARISON_SQL = """
SELECT
    domain_label,
    size_gb_n1,
    size_gb_n,
    growth_gb,
    cost_n1_usd,
    cost_n_usd,
    cost_increase_usd,
    growth_rate_pct
FROM serving.v_n1_comparison
ORDER BY cost_n_usd DESC
"""

ROI_PROJECTION_SQL = """
SELECT
    year_offset,
    volume_no_action_gb,
    cost_no_action_usd,
    cumul_cost_no_action_usd,
    total_volume_with_archiving_gb,
    cost_with_archiving_usd,
    cumul_cost_with_archiving_usd,
    net_savings_usd,
    breakeven
FROM serving.v_roi_projection_summary
ORDER BY year_offset
"""

COST_PARAMS_SQL = """
SELECT param_name, param_value, unit, description
FROM serving.dim_cost_params
ORDER BY param_id
"""

ARCHIVING_BY_STRATEGY_SQL = """
SELECT
    recommended_strategy,
    COUNT(*)::bigint                  AS asset_count,
    ROUND(SUM(size_mb)::numeric, 1)   AS total_size_mb
FROM serving.mv_archiving_recommendation
GROUP BY recommended_strategy
ORDER BY total_size_mb DESC
"""

RUN_ID_SQL = "SELECT MAX(run_id) AS run_id FROM processed.dim_asset"

_HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
_ALT_FILL = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")

_SHEET_HEADERS: dict[str, list[str]] = {
    "Domain Profile": [
        "Domaine", "Nb assets", "Volume total (MB)", "Candidats archivage",
        "Gain estimé (MB)", "Score archivage moyen", "Score ROI moyen",
        "Dépendances sortantes moy.", "Ratio nullables moyen",
        "Assets sans description", "Niveau de risque",
    ],
    "Domain Shared Keys": [
        "Domaine source", "Domaine cible", "Champ-clé partagé", "Nb assets partagés",
    ],
    "Top Archival Candidates": [
        "Domaine", "Nom technique", "Nom métier", "Système source",
        "Type asset", "Score archivage", "Score ROI",
        "Taille (MB)", "Dépendances sortantes", "Nb lignes", "Rang domaine",
    ],
    "Archiving Policies": [
        "Code stratégie", "Libellé", "Description", "Traitement opérationnel",
        "Rétention (ans)", "Priorité",
    ],
    "Archiving by Domain": [
        "Domaine", "Stratégie", "Libellé stratégie",
        "Rétention (ans)", "Nb assets", "Volume (MB)",
    ],
    "Archiving Actions": [
        "Domaine", "Nom technique", "Nom métier", "Stratégie recommandée",
        "Taille (MB)", "Nb lignes", "Ancienneté", "Sensibilité",
        "Dépendances sortantes", "Justification",
    ],
    "Cost Parameters": [
        "Paramètre", "Valeur", "Unité", "Description",
    ],
    "Cost by Domain": [
        "Domaine", "Volume (Go)", "Coût actuel ($/an)", "Économie ($/an)",
        "% économie", "% du coût total", "% cumulé (Pareto)",
        "Rang coût", "Potentiel optimisation",
    ],
    "N-1 Comparison": [
        "Domaine", "Volume N-1 (Go)", "Volume N (Go)", "Croissance (Go)",
        "Coût N-1 ($/an)", "Coût N ($/an)", "Surcoût ($/an)", "Taux croissance %",
    ],
    "ROI Projection": [
        "Année", "Volume sans action (Go)", "Coût sans action ($/an)",
        "Coût cumulé sans action ($)", "Volume avec archivage (Go)",
        "Coût avec archivage ($/an)", "Coût cumulé avec archivage ($)",
        "Économie nette cumulée ($)", "Rentable",
    ],
    "Archiving by Strategy": [
        "Stratégie", "Nb assets", "Volume (MB)",
    ],
}


def _write_sheet(
    ws: Any,
    headers: list[str],
    rows: list[dict[str, Any]],
    col_keys: list[str],
) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, row in enumerate(rows, start=2):
        values = [row.get(key) for key in col_keys]
        ws.append(values)
        if idx % 2 == 0:
            for cell in ws[idx]:
                cell.fill = _ALT_FILL

    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 22

    ws.freeze_panes = "A2"


def _build_dashboard(
    ws_dash: Any,
    *,
    cost_dom_ws: Any,
    cost_dom_n: int,
    roi_ws: Any,
    roi_n: int,
    strategy_ws: Any,
    strategy_n: int,
    profile_ws: Any,
    profile_n: int,
) -> None:
    """Build a Dashboard sheet with native Excel charts referencing data sheets."""
    ws_dash["A1"] = "Tableau de bord — Gouvernance & Archivage des données"
    ws_dash["A1"].font = Font(bold=True, size=14, color="1F4E79")
    ws_dash["A2"] = "Données : feuilles Cost by Domain, ROI Projection, Archiving by Strategy, Domain Profile"
    ws_dash["A2"].font = Font(italic=True, size=9, color="808080")

    # 1. Camembert — répartition du coût de stockage par domaine
    if cost_dom_n > 0:
        pie = PieChart()
        pie.title = "Répartition du coût de stockage par domaine"
        pie.height = 8
        pie.width = 15
        data = Reference(cost_dom_ws, min_col=3, min_row=1, max_row=1 + cost_dom_n)
        cats = Reference(cost_dom_ws, min_col=1, min_row=2, max_row=1 + cost_dom_n)
        pie.add_data(data, titles_from_data=True)
        pie.set_categories(cats)
        ws_dash.add_chart(pie, "B4")

    # 2. Histogramme — volume par stratégie d'archivage
    if strategy_n > 0:
        bar = BarChart()
        bar.type = "col"
        bar.title = "Volume par stratégie d'archivage (Mo)"
        bar.height = 8
        bar.width = 15
        bar.legend = None
        data = Reference(strategy_ws, min_col=3, min_row=1, max_row=1 + strategy_n)
        cats = Reference(strategy_ws, min_col=1, min_row=2, max_row=1 + strategy_n)
        bar.add_data(data, titles_from_data=True)
        bar.set_categories(cats)
        ws_dash.add_chart(bar, "L4")

    # 3. Courbe — projection ROI sur 5 ans (sans action vs avec archivage)
    if roi_n > 0:
        line = LineChart()
        line.title = "Projection coût 5 ans : sans action vs avec archivage ($/an)"
        line.height = 8
        line.width = 15
        line.y_axis.title = "$/an"
        line.x_axis.title = "Année (N+k)"
        cats = Reference(roi_ws, min_col=1, min_row=2, max_row=1 + roi_n)
        for col in (3, 6):  # cost_no_action_usd, cost_with_archiving_usd
            data = Reference(roi_ws, min_col=col, min_row=1, max_row=1 + roi_n)
            line.add_data(data, titles_from_data=True)
        line.set_categories(cats)
        ws_dash.add_chart(line, "B22")

    # 4. Histogramme horizontal — nombre d'assets par domaine
    if profile_n > 0:
        bar2 = BarChart()
        bar2.type = "bar"
        bar2.title = "Nombre d'assets par domaine"
        bar2.height = 8
        bar2.width = 15
        bar2.legend = None
        data = Reference(profile_ws, min_col=2, min_row=1, max_row=1 + profile_n)
        cats = Reference(profile_ws, min_col=1, min_row=2, max_row=1 + profile_n)
        bar2.add_data(data, titles_from_data=True)
        bar2.set_categories(cats)
        ws_dash.add_chart(bar2, "L22")

    # 5. Pareto — coût par domaine (barres) + % cumulé (courbe, axe secondaire)
    if cost_dom_n > 0:
        pareto = BarChart()
        pareto.type = "col"
        pareto.title = "Pareto des coûts par domaine"
        pareto.height = 8
        pareto.width = 15
        pareto.legend = None
        data = Reference(cost_dom_ws, min_col=3, min_row=1, max_row=1 + cost_dom_n)
        pareto.add_data(data, titles_from_data=True)
        pareto.set_categories(Reference(cost_dom_ws, min_col=1, min_row=2, max_row=1 + cost_dom_n))

        cumul = LineChart()
        cumul_data = Reference(cost_dom_ws, min_col=8, min_row=1, max_row=1 + cost_dom_n)
        cumul.add_data(cumul_data, titles_from_data=True)
        cumul.y_axis.axId = 200
        cumul.y_axis.title = "% cumulé"
        cumul.y_axis.crosses = "max"
        pareto += cumul
        ws_dash.add_chart(pareto, "B40")


def export_domain_model(output_path: str | None = None) -> str:
    """Export domain model views to an Excel workbook.

    Args:
        output_path: Optional explicit output path. Defaults to
            exports/domain_model_run<N>.xlsx.

    Returns:
        Absolute path of the generated file.
    """
    settings = get_settings()
    pg = PostgresClient(settings=settings)

    run_row = pg.fetch_one(RUN_ID_SQL)
    run_id = int(run_row["run_id"]) if run_row and run_row.get("run_id") else 0

    if output_path is not None:
        out_file = Path(output_path)
    else:
        out_file = Path("exports") / f"domain_model_run{run_id}.xlsx"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting domain model for run_id={} -> {}", run_id, out_file)

    profile_rows = pg.fetch_all(PROFILE_SQL)
    dependency_rows = pg.fetch_all(DEPENDENCY_SQL)
    candidate_rows = pg.fetch_all(CANDIDATES_SQL)
    policy_rows = pg.fetch_all(ARCHIVING_POLICY_SQL)
    archiving_by_domain_rows = pg.fetch_all(ARCHIVING_SUMMARY_SQL)
    archiving_action_rows = pg.fetch_all(ARCHIVING_ACTIONABLE_SQL)
    cost_param_rows = pg.fetch_all(COST_PARAMS_SQL)
    cost_by_domain_rows = pg.fetch_all(COST_BY_DOMAIN_SQL)
    n1_rows = pg.fetch_all(N1_COMPARISON_SQL)
    roi_rows = pg.fetch_all(ROI_PROJECTION_SQL)
    strategy_rows = pg.fetch_all(ARCHIVING_BY_STRATEGY_SQL)

    logger.info(
        "Fetched: {} profile, {} dependency, {} candidate, {} policy, "
        "{} archiving-by-domain, {} archiving-action, {} cost-param, "
        "{} cost-by-domain, {} n1, {} roi row(s)",
        len(profile_rows),
        len(dependency_rows),
        len(candidate_rows),
        len(policy_rows),
        len(archiving_by_domain_rows),
        len(archiving_action_rows),
        len(cost_param_rows),
        len(cost_by_domain_rows),
        len(n1_rows),
        len(roi_rows),
    )

    wb = Workbook()
    wb.remove(wb.active)

    ws_profile = wb.create_sheet("Domain Profile")
    _write_sheet(
        ws=ws_profile,
        headers=_SHEET_HEADERS["Domain Profile"],
        rows=profile_rows,
        col_keys=[
            "domain_label", "asset_count", "total_size_mb", "archival_candidates",
            "estimated_gain_mb", "avg_archival_score", "avg_roi_score",
            "avg_lineage_out", "avg_nullable_ratio",
            "assets_without_description", "risk_level",
        ],
    )

    ws_dep = wb.create_sheet("Domain Shared Keys")
    _write_sheet(
        ws=ws_dep,
        headers=_SHEET_HEADERS["Domain Shared Keys"],
        rows=dependency_rows,
        col_keys=["source_domain", "target_domain", "bridge_field", "shared_asset_count"],
    )

    ws_cand = wb.create_sheet("Top Archival Candidates")
    _write_sheet(
        ws=ws_cand,
        headers=_SHEET_HEADERS["Top Archival Candidates"],
        rows=candidate_rows,
        col_keys=[
            "domain_label", "technical_name", "business_name", "source_system",
            "asset_type", "archival_candidate_score", "roi_score",
            "size_mb", "lineage_out_count", "row_count", "domain_rank",
        ],
    )

    ws_policy = wb.create_sheet("Archiving Policies")
    _write_sheet(
        ws=ws_policy,
        headers=_SHEET_HEADERS["Archiving Policies"],
        rows=policy_rows,
        col_keys=[
            "strategy_code", "strategy_label", "description",
            "handling", "retention_years", "priority",
        ],
    )

    ws_arch_dom = wb.create_sheet("Archiving by Domain")
    _write_sheet(
        ws=ws_arch_dom,
        headers=_SHEET_HEADERS["Archiving by Domain"],
        rows=archiving_by_domain_rows,
        col_keys=[
            "domain_label", "recommended_strategy", "strategy_label",
            "retention_years", "asset_count", "total_size_mb",
        ],
    )

    ws_actions = wb.create_sheet("Archiving Actions")
    _write_sheet(
        ws=ws_actions,
        headers=_SHEET_HEADERS["Archiving Actions"],
        rows=archiving_action_rows,
        col_keys=[
            "domain_label", "technical_name", "business_name", "recommended_strategy",
            "size_mb", "row_count", "age_band", "sensitivity_level",
            "lineage_out_count", "rationale",
        ],
    )

    ws_cost_param = wb.create_sheet("Cost Parameters")
    _write_sheet(
        ws=ws_cost_param,
        headers=_SHEET_HEADERS["Cost Parameters"],
        rows=cost_param_rows,
        col_keys=["param_name", "param_value", "unit", "description"],
    )

    ws_cost_dom = wb.create_sheet("Cost by Domain")
    _write_sheet(
        ws=ws_cost_dom,
        headers=_SHEET_HEADERS["Cost by Domain"],
        rows=cost_by_domain_rows,
        col_keys=[
            "domain_label", "total_size_gb", "current_cost_usd_year",
            "annual_savings_usd", "savings_pct", "cost_share_pct",
            "cumulative_cost_pct", "cost_rank", "optimization_potential",
        ],
    )

    ws_n1 = wb.create_sheet("N-1 Comparison")
    _write_sheet(
        ws=ws_n1,
        headers=_SHEET_HEADERS["N-1 Comparison"],
        rows=n1_rows,
        col_keys=[
            "domain_label", "size_gb_n1", "size_gb_n", "growth_gb",
            "cost_n1_usd", "cost_n_usd", "cost_increase_usd", "growth_rate_pct",
        ],
    )

    ws_roi = wb.create_sheet("ROI Projection")
    _write_sheet(
        ws=ws_roi,
        headers=_SHEET_HEADERS["ROI Projection"],
        rows=roi_rows,
        col_keys=[
            "year_offset", "volume_no_action_gb", "cost_no_action_usd",
            "cumul_cost_no_action_usd", "total_volume_with_archiving_gb",
            "cost_with_archiving_usd", "cumul_cost_with_archiving_usd",
            "net_savings_usd", "breakeven",
        ],
    )

    ws_strategy = wb.create_sheet("Archiving by Strategy")
    _write_sheet(
        ws=ws_strategy,
        headers=_SHEET_HEADERS["Archiving by Strategy"],
        rows=strategy_rows,
        col_keys=["recommended_strategy", "asset_count", "total_size_mb"],
    )

    # Dashboard (placé en première position) — graphiques natifs
    ws_dash = wb.create_sheet("Dashboard", 0)
    _build_dashboard(
        ws_dash,
        cost_dom_ws=ws_cost_dom,
        cost_dom_n=len(cost_by_domain_rows),
        roi_ws=ws_roi,
        roi_n=len(roi_rows),
        strategy_ws=ws_strategy,
        strategy_n=len(strategy_rows),
        profile_ws=ws_profile,
        profile_n=len(profile_rows),
    )

    ws_meta = wb.create_sheet("Metadata")
    ws_meta.append(["Clé", "Valeur"])
    ws_meta.append(["run_id", run_id])
    ws_meta.append(["generated_at", datetime.now().isoformat(timespec="seconds")])
    ws_meta.append(["domains", len(profile_rows)])
    ws_meta.append(["dependency_edges", len(dependency_rows)])
    ws_meta.append(["archival_candidates_rows", len(candidate_rows)])
    ws_meta.append(["archiving_policies", len(policy_rows)])
    ws_meta.append(["archiving_by_domain_rows", len(archiving_by_domain_rows)])
    ws_meta.append(["archiving_action_rows", len(archiving_action_rows)])
    ws_meta.append(["cost_by_domain_rows", len(cost_by_domain_rows)])
    ws_meta.append(["roi_projection_rows", len(roi_rows)])
    ws_meta.append(["archiving_by_strategy_rows", len(strategy_rows)])
    for cell in ws_meta[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL

    wb.save(out_file)
    logger.info("Excel workbook saved: {}", out_file)
    return str(out_file)


def main() -> None:
    """CLI entrypoint for domain model export."""
    parser = argparse.ArgumentParser(description="Export serving domain model to Excel")
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Optional output .xlsx path",
    )
    args = parser.parse_args()
    configure_logging()
    out = export_domain_model(output_path=args.output_path)
    logger.info("Export complete: {}", out)


if __name__ == "__main__":
    main()
