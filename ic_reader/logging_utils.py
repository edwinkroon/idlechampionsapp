"""Logging setup for area reader CLI and library."""

from __future__ import annotations

import logging
from pathlib import Path

DEFAULT_LOG_PATH = Path("logs") / "area_reader.log"


def setup_logging(
    *,
    log_path: Path | None = None,
    level: int = logging.INFO,
    debug: bool = False,
) -> logging.Logger:
    """Configure file + console logging; return package logger."""
    if debug:
        level = logging.DEBUG

    log_path = log_path or DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ic_reader")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
