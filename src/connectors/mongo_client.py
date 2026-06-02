"""MongoDB read-only connector utilities.

This module exposes a robust wrapper for MongoDB reads in the pfe-data-ia
pipeline, with retry support and JSON-friendly output.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from loguru import logger
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.settings import Settings


class MongoClientWrapper:
    """Simple read-only MongoDB client.

    The wrapper uses a persistent ``pymongo.MongoClient`` instance and provides
    helper methods for common read operations.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = self._create_client()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(PyMongoError),
        before_sleep=before_sleep_log(logger, "WARNING"),  # type: ignore[arg-type]
        reraise=True,
    )
    def _create_client(self) -> MongoClient[Any]:
        """Create a Mongo client with retry support."""
        client = MongoClient(self.settings.mongo_uri)
        client.admin.command("ping")
        return client

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """Serialize non-JSON-native values (e.g. ObjectId) recursively."""
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, dict):
            return {key: MongoClientWrapper._serialize_value(val) for key, val in value.items()}
        if isinstance(value, list):
            return [MongoClientWrapper._serialize_value(item) for item in value]
        return value

    @classmethod
    def _serialize_document(cls, document: dict[str, Any]) -> dict[str, Any]:
        """Serialize a Mongo document into a plain Python dictionary."""
        return {key: cls._serialize_value(value) for key, value in document.items()}

    def close(self) -> None:
        """Close underlying Mongo client resources."""
        self._client.close()

    def test_connection(self) -> bool:
        """Test MongoDB connectivity with a ping command.

        Returns:
            True when connection is healthy.
        """
        try:
            self._client.admin.command("ping")
            logger.info("MongoDB connection successful")
            return True
        except PyMongoError:
            logger.exception("MongoDB connection failed")
            raise

    def get_database(self) -> Database[Any]:
        """Return configured Mongo database instance."""
        return self._client[self.settings.mongo_db_name]

    def list_collection_names(self) -> list[str]:
        """List all collection names from configured Mongo database."""
        try:
            names = self.get_database().list_collection_names()
            logger.info("MongoDB collections discovered: {}", len(names))
            return names
        except PyMongoError:
            logger.exception("Failed to list MongoDB collection names")
            raise

    def find_one(
        self,
        collection_name: str,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Read one document from a collection.

        Args:
            collection_name: Name of collection to query.
            query: Optional Mongo filter.

        Returns:
            Serialized document or ``None`` when no match is found.
        """
        try:
            document = self.get_database()[collection_name].find_one(query or {})
            if document is None:
                return None
            return self._serialize_document(document)
        except PyMongoError:
            logger.exception("find_one failed for collection={} query={}", collection_name, query)
            raise

    def find_many(
        self,
        collection_name: str,
        query: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read many documents from a collection.

        Args:
            collection_name: Name of collection to query.
            query: Optional Mongo filter.
            limit: Optional max number of documents to return.

        Returns:
            List of serialized documents.
        """
        try:
            cursor = self.get_database()[collection_name].find(query or {})
            if limit is not None and limit > 0:
                cursor = cursor.limit(limit)
            documents = [self._serialize_document(doc) for doc in cursor]
            logger.info(
                "find_many returned {} document(s) from {}",
                len(documents),
                collection_name,
            )
            return documents
        except PyMongoError:
            logger.exception("find_many failed for collection={} query={}", collection_name, query)
            raise

    def aggregate(self, collection_name: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run an aggregation pipeline on a collection.

        Args:
            collection_name: Name of collection to aggregate.
            pipeline: Mongo aggregation pipeline.

        Returns:
            List of serialized result documents.
        """
        try:
            cursor = self.get_database()[collection_name].aggregate(pipeline)
            results = [self._serialize_document(doc) for doc in cursor]
            logger.info(
                "aggregate returned {} document(s) from {}",
                len(results),
                collection_name,
            )
            return results
        except PyMongoError:
            logger.exception("aggregate failed for collection={}", collection_name)
            raise

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Return collection statistics using the Mongo ``collStats`` command."""
        try:
            stats = self.get_database().command("collStats", collection_name)
            serialized = self._serialize_document(stats)
            logger.info("Fetched stats for collection={}", collection_name)
            return serialized
        except PyMongoError:
            logger.exception("get_collection_stats failed for collection={}", collection_name)
            raise

    def check_connection(self) -> None:
        """Compatibility wrapper for existing pipeline code."""
        self.test_connection()

    def fetch_collection_documents(self, collection_name: str) -> list[dict[str, Any]]:
        """Compatibility wrapper returning all documents of a collection."""
        return self.find_many(collection_name=collection_name)


class MongoDbClient(MongoClientWrapper):
    """Backward-compatible alias for previous class name."""


if __name__ == "__main__":
    from src.config.settings import get_settings
    from src.utils.logging_utils import configure_logging

    settings = get_settings()
    configure_logging()

    client = MongoClientWrapper(settings=settings)
    try:
        ok = client.test_connection()
        logger.info("Mongo connection test result: {}", ok)
        collections = client.list_collection_names()
        logger.info("Mongo collections sample: {}", collections[:10])
    finally:
        client.close()
