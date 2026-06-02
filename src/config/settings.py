"""Centralized configuration module for the pfe-data-ia data pipeline.

Settings are loaded from environment variables and/or a `.env` file via
pydantic-settings.  A single ``Settings`` instance is cached after first
instantiation through ``get_settings()``.

Sections
--------
- App          : application identity and run mode
- PostgreSQL   : target database connection parameters
- Oracle       : PeopleSoft EP92U038 source connection parameters
- MongoDB      : DDTMdbDemo source connection parameters
- Logging      : log verbosity
- Pipeline     : execution strategy defaults

Usage example::

    from src.config.settings import get_settings

    settings = get_settings()
    print(settings.postgresql_url)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from uuid import uuid4

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Allowed log level literals
# ---------------------------------------------------------------------------

_LOG_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


# ---------------------------------------------------------------------------
# Settings class
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Strongly-typed, centralized settings for the pfe-data-ia pipeline.

    All fields can be overridden via environment variables or a ``.env``
    file placed in the working directory.  Field names map to environment
    variable names in uppercase (e.g. ``APP_NAME`` → ``app_name``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------

    app_name: str = Field(
        default="pfe-data-ia",
        description="Human-readable application name.",
    )
    app_env: Literal["dev", "staging", "prod"] = Field(
        default="dev",
        description="Deployment environment: dev | staging | prod.",
    )
    debug: bool = Field(
        default=True,
        description="Enable debug mode. Should be False in production.",
    )

    # ------------------------------------------------------------------
    # PostgreSQL (target)
    # ------------------------------------------------------------------

    postgres_host: str = Field(
        default="localhost",
        description="PostgreSQL server hostname or IP address.",
    )
    postgres_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="PostgreSQL server TCP port.",
    )
    postgres_db: str = Field(
        default="pfe_data_ia",
        description="Target PostgreSQL database name.",
    )
    postgres_user: str = Field(
        default="postgres",
        description="PostgreSQL login username.",
    )
    postgres_password: str = Field(
        default="postgres",
        description=(
            "PostgreSQL login password. "
            "Override in .env for any non-local environment."
        ),
    )

    # ------------------------------------------------------------------
    # Oracle PeopleSoft EP92U038 (source)
    # ------------------------------------------------------------------

    oracle_host: str = Field(
        default="192.168.11.111",
        description="Oracle database server hostname or IP address.",
    )
    oracle_port: int = Field(
        default=1521,
        ge=1,
        le=65535,
        description="Oracle listener TCP port.",
    )
    oracle_service_name: str = Field(
        default="EP92U038",
        description="Oracle service name (used to build the DSN).",
    )
    oracle_user: str = Field(
        default="SYSADM",
        description="Oracle login username.",
    )
    oracle_password: str = Field(
        description="Oracle login password.  Must be provided via .env.",
    )
    oracle_owner: str = Field(
        default="SYSADM",
        description="Oracle schema owner used to qualify table names.",
    )

    # -- Résilience des extractions longues sur VPN --------------------------
    oracle_expire_time_minutes: int = Field(
        default=1,
        ge=0,
        description=(
            "Intervalle keepalive de détection des connexions mortes (minutes). "
            "0 désactive. Protège contre les coupures VPN sur sessions longues."
        ),
    )
    oracle_tcp_connect_timeout: float = Field(
        default=20.0,
        gt=0,
        description="Timeout (secondes) d'ouverture d'une connexion Oracle.",
    )
    oracle_query_max_attempts: int = Field(
        default=4,
        ge=1,
        description=(
            "Nombre maximum de tentatives d'une requête lecture Oracle lorsque "
            "la connexion tombe en cours d'exécution (retry niveau requête)."
        ),
    )

    # ------------------------------------------------------------------
    # MongoDB DDTMdbDemo (source)
    # ------------------------------------------------------------------

    mongo_uri: str = Field(
        default="mongodb://localhost:27017",
        description=(
            "MongoDB connection URI. "
            "Include credentials in the URI when authentication is required."
        ),
    )
    mongo_db_name: str = Field(
        default="DDTMdbDemo",
        description="MongoDB database name to connect to.",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    log_level: str = Field(
        default="INFO",
        description=(
            "Logging verbosity level. "
            "Allowed values: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        ),
    )

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    default_run_type: Literal["full", "incremental"] = Field(
        default="full",
        description="Default extraction strategy: 'full' (full reload) or 'incremental'.",
    )
    default_source_system: Literal["oracle", "mongo", "both"] = Field(
        default="oracle",
        description="Default source system to extract from when not specified at runtime.",
    )
    run_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description=(
            "Unique identifier for the current pipeline run. "
            "Auto-generated when not provided."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, value: object) -> str:
        """Normalise and validate ``log_level`` against allowed values.

        Args:
            value: Raw value from the environment.

        Returns:
            Upper-cased level string.

        Raises:
            ValueError: When ``value`` is not an allowed log level.
        """
        normalised = str(value).strip().upper()
        if normalised not in _LOG_LEVELS:
            raise ValueError(
                f"Invalid log_level '{value}'. "
                f"Allowed values: {sorted(_LOG_LEVELS)}"
            )
        return normalised

    @model_validator(mode="after")
    def validate_oracle_password_not_empty(self) -> "Settings":
        """Ensure Oracle password is not an empty string.

        Raises:
            ValueError: When ``oracle_password`` is blank.
        """
        if not self.oracle_password.strip():
            raise ValueError(
                "oracle_password must not be empty. "
                "Set ORACLE_PASSWORD in your .env file."
            )
        return self

    # ------------------------------------------------------------------
    # Utility properties
    # ------------------------------------------------------------------

    @property
    def postgresql_url(self) -> str:
        """Return a SQLAlchemy-compatible PostgreSQL connection URL.

        Uses the ``psycopg`` (v3) driver::

            postgresql+psycopg://user:password@host:port/db
        """
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def oracle_dsn(self) -> str:
        """Return an Oracle Easy Connect DSN string.

        Format: ``host:port/service_name``

        Compatible with ``oracledb.connect(dsn=settings.oracle_dsn, ...)``.
        """
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service_name}"

    @property
    def mongo_database_name(self) -> str:
        """Return the MongoDB target database name.

        Alias for ``mongo_db_name``, provided for consistency with the
        naming convention used in other utility properties.
        """
        return self.mongo_db_name


# ---------------------------------------------------------------------------
# Cached factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache the application settings once per process.

    Subsequent calls return the same ``Settings`` instance without
    reloading the ``.env`` file.

    Returns:
        The validated ``Settings`` singleton.

    Raises:
        RuntimeError: When pydantic validation fails (missing or invalid fields).
    """
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(
            f"Pipeline configuration is invalid. Check your .env file.\n{exc}"
        ) from exc


# ---------------------------------------------------------------------------
# .env example (reference)
# ---------------------------------------------------------------------------
#
# Copy this block to a file named `.env` at the project root and fill in
# the real secrets.  Never commit the real `.env` to source control.
#
# ---------------------------------------------------------------------------
# # ── App ────────────────────────────────────────────────────────────────
# APP_NAME=pfe-data-ia
# APP_ENV=dev
# DEBUG=true
#
# # ── PostgreSQL ──────────────────────────────────────────────────────────
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_DB=pfe_data_ia
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=change_me
#
# # ── Oracle PeopleSoft EP92U038 ──────────────────────────────────────────
# ORACLE_HOST=192.168.11.111
# ORACLE_PORT=1521
# ORACLE_SERVICE_NAME=EP92U038
# ORACLE_USER=SYSADM
# ORACLE_PASSWORD=change_me
# ORACLE_OWNER=SYSADM
#
# # ── MongoDB DDTMdbDemo ──────────────────────────────────────────────────
# MONGO_URI=mongodb://localhost:27017
# MONGO_DB_NAME=DDTMdbDemo
#
# # ── Logging ─────────────────────────────────────────────────────────────
# LOG_LEVEL=INFO
#
# # ── Pipeline ─────────────────────────────────────────────────────────────
# DEFAULT_RUN_TYPE=full
# DEFAULT_SOURCE_SYSTEM=oracle
# RUN_ID=                         # leave blank → auto-generated UUID
# ---------------------------------------------------------------------------
