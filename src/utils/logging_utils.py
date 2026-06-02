"""Centralized loguru configuration for the whole project.

This module provides a single entry point to configure console logging for
scripts and Prefect flows while avoiding duplicated handlers.
"""

from __future__ import annotations

import sys
from typing import Final

from loguru import logger

from src.config.settings import get_settings

_LOG_FORMAT: Final[str] = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "{name}:{function}:{line} - "
    "<level>{message}</level>"
)


def configure_logging() -> None:
    """Configure the global loguru logger for console output.

    The log level is read from ``Settings.log_level`` loaded via
    ``get_settings()``. Existing handlers are removed first to prevent
    duplicate logs when the function is called multiple times (common in
    interactive runs and Prefect task contexts).
    """
    settings = get_settings()

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=_LOG_FORMAT,
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
