"""Loguru structured logging setup for the dlt ingestion showcase.

Additive helper — used only by ingestion/ scripts. Does not touch scripts/.
Call configure_logging() once at process start; import `logger` everywhere else.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path(__file__).resolve().parent / "logs"


def configure_logging(level: str = "INFO") -> "logger":
    """Reset loguru sinks: pretty console + JSON-lines file.

    Returns the configured logger so callers can `log = configure_logging()`.
    """
    LOG_DIR.mkdir(exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{extra}</cyan> | <level>{message}</level>"
        ),
    )
    logger.add(
        LOG_DIR / "ingestion.jsonl",
        level=level,
        serialize=True,          # one structured JSON object per line
        rotation="5 MB",
        retention=3,
    )
    return logger
