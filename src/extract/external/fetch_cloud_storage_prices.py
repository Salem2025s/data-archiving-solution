"""Collecte par API externe : tarifs réels de stockage cloud (Azure Retail Prices).

Technique de collecte C1.1.2 : **appel d'API externe** (publique, sans authentification).

Objectif métier : remplacer les coûts de stockage codés en dur du modèle de ROI par
des **tarifs de marché réels**, ce qui crédibilise `roi_score` et les recommandations
d'archivage (un actif migré du chaud vers l'archive doit refléter un vrai écart de prix).

Source : https://prices.azure.com/api/retail/prices  (API publique Microsoft, sans clé)
On retient la redondance **LRS** (standard) sur le produit **Blob Storage**, qui est
la référence de marché pour du stockage d'archive.

Note SSL : en environnement d'entreprise, le proxy inspecte le TLS. `truststore`
fait utiliser le magasin de certificats de l'OS (où la CA du proxy est installée),
ce qui permet de **conserver la vérification SSL** au lieu de la désactiver.

Usage :
    python -m src.extract.external.fetch_cloud_storage_prices
    python -m src.extract.external.fetch_cloud_storage_prices --apply   # met à jour dim_cost_params
"""
from __future__ import annotations

import argparse
from typing import Any

import requests
import truststore
from loguru import logger

truststore.inject_into_ssl()  # SSL vérifié via le magasin de certificats de l'OS

API_URL = "https://prices.azure.com/api/retail/prices"
DEFAULT_REGION = "francecentral"
MONTHS_PER_YEAR = 12

# Compteurs Azure retenus → rôle dans notre modèle de coût
METERS: dict[str, str] = {
    "Hot LRS Data Stored": "actif",      # stockage chaud (données vivantes)
    "Cool LRS Data Stored": "tiede",     # palier intermédiaire
    "Archive LRS Data Stored": "archive",  # cible d'archivage
}
PRODUCT = "Blob Storage"


def fetch_storage_prices(region: str = DEFAULT_REGION, timeout: int = 25) -> dict[str, dict[str, Any]]:
    """Interroge l'API Azure et retourne les tarifs $/Go/mois et $/Go/an par palier."""
    flt = (
        f"serviceName eq 'Storage' and armRegionName eq '{region}' "
        f"and priceType eq 'Consumption' and endswith(meterName, 'Data Stored')"
    )
    response = requests.get(API_URL, params={"$filter": flt}, timeout=timeout)
    response.raise_for_status()
    items = response.json().get("Items", [])
    logger.info("API Azure Retail Prices : {} tarifs reçus (région={})", len(items), region)

    prices: dict[str, dict[str, Any]] = {}
    for item in items:
        meter, product = item.get("meterName"), item.get("productName")
        if meter in METERS and product == PRODUCT:
            per_month = float(item["retailPrice"])
            prices[METERS[meter]] = {
                "meter": meter,
                "usd_per_gb_month": per_month,
                "usd_per_gb_year": round(per_month * MONTHS_PER_YEAR, 6),
                "currency": item.get("currencyCode"),
                "region": item.get("armRegionName"),
            }

    missing = set(METERS.values()) - set(prices)
    if missing:
        raise RuntimeError(f"Tarifs introuvables pour les paliers : {sorted(missing)}")
    return prices


def apply_to_cost_params(prices: dict[str, dict[str, Any]]) -> None:
    """Injecte les tarifs réels dans serving.dim_cost_params (alimente roi_score)."""
    from sqlalchemy import text

    from src.config.settings import get_settings
    from src.connectors.postgres_client import PostgresClient

    client = PostgresClient(settings=get_settings())
    updates = {
        "storage_cost_per_gb_per_year": prices["actif"]["usd_per_gb_year"],
        "cold_storage_cost_per_gb_year": prices["archive"]["usd_per_gb_year"],
    }
    with client.engine.begin() as conn:
        for name, value in updates.items():
            conn.execute(
                text(
                    "UPDATE serving.dim_cost_params "
                    "SET param_value = :v, updated_at = now() WHERE param_name = :n"
                ),
                {"v": float(value), "n": name},
            )
    logger.info("dim_cost_params mis à jour depuis les tarifs de marché : {}", updates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tarifs stockage cloud via API Azure (publique).")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--apply", action="store_true",
                        help="Écrit les tarifs dans serving.dim_cost_params")
    args = parser.parse_args()

    prices = fetch_storage_prices(region=args.region)

    print(f"\nTarifs stockage Azure — région {args.region} (source : API publique, SSL vérifié)")
    print(f"{'palier':10} | {'compteur':26} | {'$/Go/mois':>10} | {'$/Go/an':>9}")
    print("-" * 68)
    for tier in ("actif", "tiede", "archive"):
        p = prices[tier]
        print(f"{tier:10} | {p['meter']:26} | {p['usd_per_gb_month']:>10.4f} | {p['usd_per_gb_year']:>9.4f}")

    ratio = prices["actif"]["usd_per_gb_year"] / prices["archive"]["usd_per_gb_year"]
    gain = prices["actif"]["usd_per_gb_year"] - prices["archive"]["usd_per_gb_year"]
    print(f"\nEcart actif/archive : x{ratio:.1f}  -> gain potentiel par Go archive : "
          f"{gain:.4f} $/an")

    if args.apply:
        apply_to_cost_params(prices)
        print("\n-> serving.dim_cost_params mis a jour (roi_score recalculable).")
    else:
        print("\n(aperçu) Relancer avec --apply pour alimenter dim_cost_params.")


if __name__ == "__main__":
    main()
