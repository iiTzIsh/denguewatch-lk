"""One place to configure logging for every script."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import LOG_DIR

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO", log_file: str | Path | None = LOG_DIR / "pipeline.log") -> None:
    """Console + rotating file log. Call once at the start of main()."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        # max 1 MB per file, keep 3 old files -> logs never fill the disk
        handlers.append(RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, handlers=handlers, force=True)
    # 3rd-party libraries are noisy at DEBUG - keep them at WARNING
    logging.getLogger("urllib3").setLevel(logging.WARNING)
