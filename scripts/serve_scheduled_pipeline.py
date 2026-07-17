"""Déploiement Prefect PLANIFIÉ (cron) du pipeline Oracle.

Répond au critère C1.1.3 de la grille : « mettre en place des tâches planifiées ».

Ce script publie deux déploiements planifiés et se met à l'écoute :
  · pipeline-oracle-quotidien   → 02h00 tous les jours (collecte complète, VPN requis)
  · serving-refresh-horaire     → toutes les heures (recalcul serving, sans VPN)

Usage (2 terminaux) :
    # Terminal 1 — serveur + UI Prefect (http://127.0.0.1:4200)
    prefect server start

    # Terminal 2 — publie les déploiements planifiés et poll les runs
    python scripts/serve_scheduled_pipeline.py

Le script est BLOQUANT (il poll les exécutions planifiées) : Ctrl+C pour arrêter.

⚠️ Le déploiement quotidien déclenchera une extraction Oracle réelle à 02h00
   (VPN requis). Pour une simple démonstration, capturer l'écran puis Ctrl+C.
"""
from __future__ import annotations

from prefect import serve

from src.prefect.flows.flow_oracle_only import flow_oracle_only
from src.prefect.flows.flow_publish_serving import flow_publish_serving

if __name__ == "__main__":
    # Collecte complète Oracle → processed → serving, chaque nuit à 02h00
    collecte_quotidienne = flow_oracle_only.to_deployment(
        name="pipeline-oracle-quotidien",
        cron="0 2 * * *",
        tags=["oracle", "collecte", "production"],
        description=(
            "Collecte planifiée : extraction Oracle EP92U038 → couche processed "
            "(+ scoring ML) → publication serving. Nouveau run_id à chaque exécution."
        ),
    )

    # Recalcul de la couche analytique, léger, toutes les heures (ne nécessite pas le VPN)
    refresh_serving = flow_publish_serving.to_deployment(
        name="serving-refresh-horaire",
        cron="0 * * * *",
        tags=["serving", "analytics"],
        description="Rafraîchissement horaire des vues matérialisées de la couche serving.",
    )

    serve(collecte_quotidienne, refresh_serving)
