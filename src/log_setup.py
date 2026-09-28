"""One place to configure logging for every script (Day 3)."""
from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(level: int = logging.INFO, log_file: str | None = "logs/pipeline.log") -> None:
    """Log to console + a file. Call once at the start of main()."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,  # override any earlier config
    )
