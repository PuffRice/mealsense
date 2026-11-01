"""Logging configuration for the Facebook Group Image Scraper."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_file: Path, console_level: int = logging.WARNING) -> logging.Logger:
    """Configure application-wide file and console logging.

    Detailed INFO/DEBUG events are written to `<output_dir>/logs/scraper.log`,
    while console logging is kept quiet during live dashboard rendering.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("fb_group_scraper")
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return root_logger
