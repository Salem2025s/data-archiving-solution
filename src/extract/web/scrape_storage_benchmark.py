"""Collecte par web scraping : benchmark tarifaire d'un fournisseur de stockage.

Technique de collecte C1.1.2 : **web crawling / scraping**.

Objectif métier : recouper le tarif d'archivage obtenu par l'API officielle (Azure)
avec celui d'un fournisseur concurrent publié sur une page web. On obtient une
**fourchette de marché** au lieu d'un prix unique — le `roi_score` et les
recommandations d'archivage reposent alors sur une réalité économique vérifiable.

Cible : page tarifaire publique Backblaze B2 (HTML statique, pas de rendu JS).

Éthique / conformité :
  · le `robots.txt` du site est **vérifié avant toute requête** (crawling responsable) ;
  · une seule requête, User-Agent explicite, aucune donnée personnelle collectée.

Limite assumée : le scraping dépend de la structure HTML de la page. Si le site
change sa mise en page, l'extraction échoue explicitement (jamais silencieusement).

Usage :
    python -m src.extract.web.scrape_storage_benchmark
"""
from __future__ import annotations

import re
import urllib.robotparser as robotparser

import requests
import truststore
from bs4 import BeautifulSoup
from loguru import logger

truststore.inject_into_ssl()  # SSL vérifié via le magasin de certificats de l'OS

SITE = "https://www.backblaze.com"
PAGE = "/cloud-storage/pricing"
USER_AGENT = "PFE-DataGovernance/1.0 (recherche academique; contact: etudiant@ynov.com)"
GB_PER_TB = 1024
MONTHS_PER_YEAR = 12

# Prix au Go/mois : « $0.006/GB » ou « $0.006 per GB »
_PRICE_GB = re.compile(r"\$\s*(0?\.\d{1,4})\s*(?:/|per\s+)GB", re.IGNORECASE)
# Prix au To/mois : « $6/TB » ou « $6 per TB »
_PRICE_TB = re.compile(r"\$\s*(\d{1,3}(?:\.\d{1,2})?)\s*(?:/|per\s+)TB", re.IGNORECASE)


def _assert_crawling_allowed() -> None:
    """Vérifie le robots.txt avant de scraper (crawling responsable)."""
    response = requests.get(f"{SITE}/robots.txt", timeout=15, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    parser = robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(USER_AGENT, SITE + PAGE):
        raise PermissionError(f"robots.txt interdit le scraping de {PAGE} — abandon.")
    logger.info("robots.txt : scraping de {} autorisé", PAGE)


def scrape_storage_benchmark(timeout: int = 20) -> dict[str, float | str]:
    """Scrape la page tarifaire et retourne le prix stockage en $/Go/mois et $/Go/an."""
    _assert_crawling_allowed()

    response = requests.get(SITE + PAGE, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    logger.info("Page récupérée : {} octets", len(response.text))

    per_gb_month: float | None = None
    if match := _PRICE_GB.search(text):
        per_gb_month = float(match.group(1))
    elif match := _PRICE_TB.search(text):  # repli : tarif exprimé au To
        per_gb_month = float(match.group(1)) / GB_PER_TB

    if per_gb_month is None:
        raise RuntimeError(
            "Aucun tarif $/Go ni $/To trouvé : la structure de la page a probablement changé."
        )

    return {
        "fournisseur": "Backblaze B2",
        "source": SITE + PAGE,
        "usd_per_gb_month": per_gb_month,
        "usd_per_gb_year": round(per_gb_month * MONTHS_PER_YEAR, 6),
    }


def main() -> None:
    bench = scrape_storage_benchmark()
    print("\nBenchmark tarifaire (web scraping) — stockage objet")
    print(f"  fournisseur : {bench['fournisseur']}")
    print(f"  source      : {bench['source']}")
    print(f"  tarif       : {bench['usd_per_gb_month']:.4f} $/Go/mois"
          f"  |  {bench['usd_per_gb_year']:.4f} $/Go/an")

    # Recoupement avec l'API officielle Azure (les deux techniques se complètent)
    try:
        from src.extract.external.fetch_cloud_storage_prices import fetch_storage_prices

        azure = fetch_storage_prices()
        lo = min(bench["usd_per_gb_year"], azure["archive"]["usd_per_gb_year"])
        hi = max(bench["usd_per_gb_year"], azure["archive"]["usd_per_gb_year"])
        print("\nFourchette de marche pour l'archivage ($/Go/an) :")
        print(f"  Azure Archive (API)      : {azure['archive']['usd_per_gb_year']:.4f}")
        print(f"  Backblaze B2  (scraping) : {bench['usd_per_gb_year']:.4f}")
        print(f"  -> fourchette retenue    : {lo:.4f} - {hi:.4f}")
    except Exception as exc:  # le benchmark seul reste exploitable
        logger.warning("Recoupement API indisponible : {}", exc)


if __name__ == "__main__":
    main()
