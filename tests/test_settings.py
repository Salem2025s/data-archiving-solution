"""Tests for Settings validation and connection-URL helpers."""

import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def test_log_level_is_normalized_uppercase():
    s = Settings(oracle_password="x", log_level="debug")
    assert s.log_level == "DEBUG"


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        Settings(oracle_password="x", log_level="LOUD")


def test_empty_oracle_password_rejected():
    with pytest.raises(ValidationError):
        Settings(oracle_password="   ")


def test_postgresql_url_format():
    s = Settings(
        oracle_password="x",
        postgres_user="u", postgres_password="p",
        postgres_host="h", postgres_port=1234, postgres_db="d",
    )
    assert s.postgresql_url == "postgresql+psycopg://u:p@h:1234/d"


def test_oracle_dsn_format():
    s = Settings(
        oracle_password="x",
        oracle_host="1.2.3.4", oracle_port=1521, oracle_service_name="SVC",
    )
    assert s.oracle_dsn == "1.2.3.4:1521/SVC"
