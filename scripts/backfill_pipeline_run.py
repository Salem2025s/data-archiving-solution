"""Reconstruit les entrées manquantes de admin.pipeline_run.

Contexte : la table admin.pipeline_run a été vidée à un moment ; seules les
exécutions les plus récentes y subsistent, alors que la couche processed
contient plusieurs runs complets (run_id 3..6). Ce script rétablit la
traçabilité en reconstruisant une entrée par run réellement présent dans
processed.dim_asset, à partir des HORODATAGES RÉELS de chargement
(processed.dim_asset.loaded_at) — aucune valeur n'est inventée.

Idempotent : n'insère que les run_id absents de admin.pipeline_run.

Usage :
    python scripts/backfill_pipeline_run.py            # aperçu (dry-run)
    python scripts/backfill_pipeline_run.py --apply    # écriture réelle
"""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from src.config.settings import get_settings

NOTE = "Entrée reconstruite depuis processed.dim_asset.loaded_at (horodatage réel de chargement)."


def main(apply: bool) -> None:
    engine = create_engine(get_settings().postgresql_url, connect_args={"connect_timeout": 5})
    with engine.begin() as conn:
        # Runs réellement présents dans processed, absents de pipeline_run
        rows = conn.execute(text("""
            SELECT d.run_id,
                   MIN(d.loaded_at) AS started_at,
                   MAX(d.loaded_at) AS ended_at,
                   COUNT(*)         AS n_assets
            FROM processed.dim_asset d
            WHERE d.run_id NOT IN (SELECT id FROM admin.pipeline_run)
            GROUP BY d.run_id
            ORDER BY d.run_id
        """)).mappings().all()

        if not rows:
            print("Rien à reconstruire : tous les runs de processed sont déjà journalisés.")
            return

        print(f"{'RUN':>4} | {'DÉBUT':^26} | {'ASSETS':>9} | action")
        print("-" * 60)
        for r in rows:
            print(f"{r['run_id']:>4} | {str(r['started_at']):^26} | {r['n_assets']:>9,} | "
                  f"{'INSERT' if apply else 'aperçu'}")

        if not apply:
            print("\n(dry-run) Relance avec --apply pour écrire dans admin.pipeline_run.")
            return

        for r in rows:
            conn.execute(text("""
                INSERT INTO admin.pipeline_run
                    (id, flow_name, run_type, source_system, status,
                     started_at, ended_at, error_message)
                VALUES
                    (:id, 'flow_full_pipeline', 'full', 'oracle+mongo', 'success',
                     :started_at, :ended_at, :note)
            """), {
                "id": int(r["run_id"]),
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "note": NOTE,
            })

        # Réaligne la séquence SERIAL sur le max(id) pour éviter tout futur conflit
        conn.execute(text(
            "SELECT setval(pg_get_serial_sequence('admin.pipeline_run','id'), "
            "(SELECT MAX(id) FROM admin.pipeline_run))"
        ))
        print(f"\n{len(rows)} entrée(s) reconstruite(s). Séquence SERIAL réalignée.")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
