"""Logging configuration."""

from __future__ import annotations

import logging


def configure_logging(level_name: str) -> None:
    """Configure application logging with a compact, readable format."""

    level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    root_logger.setLevel(level)
