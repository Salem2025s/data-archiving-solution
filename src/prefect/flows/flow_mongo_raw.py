"""Prefect flow for Mongo raw extraction and loading (V1 full reload)."""

from __future__ import annotations

from loguru import logger
from prefect import flow

from src.config.settings import get_settings
from src.connectors.postgres_client import PostgresClient
from src.extract.mongo.extract_archlog_purge import extract_archlog_purge
from src.extract.mongo.extract_business_term import extract_business_term
from src.extract.mongo.extract_classification_definition import (
    extract_classification_definition,
)
from src.extract.mongo.extract_collection_inventory import extract_collection_inventory
from src.extract.mongo.extract_datalineage import extract_datalineage
from src.extract.mongo.extract_fields import extract_fields
from src.extract.mongo.extract_glossary import extract_glossary
from src.extract.mongo.extract_metadatastable import extract_metadatastable
from src.extract.mongo.extract_project_catalog import extract_project_catalog
from src.load.load_raw_mongo import RawMongoLoader
from src.utils.logging_utils import configure_logging


@flow(name="flow_mongo_raw")
def flow_mongo_raw(run_id: int) -> int:
    """Run Mongo raw pipeline for one full-reload run.

    Steps:
    - extract Mongo datasets
    - load into `raw_mongo.*`

    Args:
        run_id: Current run identifier.

    Returns:
        Total number of loaded rows across Mongo raw target tables.
    """
    configure_logging()
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    loader = RawMongoLoader(postgres_client=postgres_client)

    logger.info("Starting flow_mongo_raw for run_id={}", run_id)

    try:
        collection_inventory_rows = extract_collection_inventory()
        metadatastable_rows = extract_metadatastable()
        fields_rows = extract_fields()
        datalineage_rows = extract_datalineage()
        business_term_rows = extract_business_term()
        glossary_rows = extract_glossary()
        classification_definition_rows = extract_classification_definition()
        archlog_purge_rows = extract_archlog_purge()
        project_catalog_rows = extract_project_catalog()

        loaded_collection_inventory = loader.load_collection_inventory(
            rows=collection_inventory_rows,
            run_id=run_id,
        )
        loaded_metadatastable = loader.load_metadatastable(
            rows=metadatastable_rows,
            run_id=run_id,
        )
        loaded_fields = loader.load_fields(rows=fields_rows, run_id=run_id)
        loaded_datalineage = loader.load_datalineage(rows=datalineage_rows, run_id=run_id)
        loaded_business_term = loader.load_business_term(
            rows=business_term_rows,
            run_id=run_id,
        )
        loaded_glossary = loader.load_glossary(rows=glossary_rows, run_id=run_id)
        loaded_classification_definition = loader.load_classification_definition(
            rows=classification_definition_rows,
            run_id=run_id,
        )
        loaded_archlog_purge = loader.load_archlog_purge(
            rows=archlog_purge_rows,
            run_id=run_id,
        )
        loaded_project_catalog = loader.load_project_catalog(
            rows=project_catalog_rows,
            run_id=run_id,
        )

        total_loaded = (
            loaded_collection_inventory
            + loaded_metadatastable
            + loaded_fields
            + loaded_datalineage
            + loaded_business_term
            + loaded_glossary
            + loaded_classification_definition
            + loaded_archlog_purge
            + loaded_project_catalog
        )
        logger.info(
            "flow_mongo_raw completed for run_id={} with total_loaded={}",
            run_id,
            total_loaded,
        )
        return total_loaded
    except Exception:
        logger.exception("flow_mongo_raw failed for run_id={}", run_id)
        raise


if __name__ == "__main__":
    flow_mongo_raw(run_id=1)
