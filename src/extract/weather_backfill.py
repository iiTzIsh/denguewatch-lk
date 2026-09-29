"""
Resumable weather BACKFILL: every district, one file per district per year.

Run:  python -m src.extract.weather_backfill                     (2006-01-01 -> latest available)
      python -m src.extract.weather_backfill --from-year 2015

Why chunk by year?  small requests, and if anything fails you only redo that chunk.
Why resumable?     a file that already exists is SKIPPED -> re-run the same command any time
                   (after a crash, or the next day if the free daily limit is reached).
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta

from src.config import WEATHER_BRONZE_DIR
from src.extract.weather import (
    ARCHIVE_LAG_DAYS,
    DISTRICTS,
    PAUSE_BETWEEN_CALLS_S,
    RateLimitError,
    WeatherAPIError,
    output_path,
    run_district,
)
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)


def year_chunks(from_year: int, last_day: date) -> list[tuple[str, str]]:
    """[(start, end)] per calendar year; the last chunk ends at last_day."""
    chunks = []
    for y in range(from_year, last_day.year + 1):
        start = date(y, 1, 1)
        end = min(date(y, 12, 31), last_day)
        chunks.append((start.isoformat(), end.isoformat()))
    return chunks


def plan(from_year: int, last_day: date) -> list[tuple[str, str, str]]:
    """Every (district, start, end) still missing on disk."""
    todo = []
    for start, end in year_chunks(from_year, last_day):
        for d in DISTRICTS:
            if not output_path(WEATHER_BRONZE_DIR, d, start, end).exists():
                todo.append((d, start, end))
    return todo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-year", type=int, default=2006)
    args = parser.parse_args()
    setup_logging()

    last_day = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    todo = plan(args.from_year, last_day)
    total = len(year_chunks(args.from_year, last_day)) * len(DISTRICTS)
    logger.info("Backfill %d -> %s: %d of %d chunks still to download", args.from_year, last_day, len(todo), total)

    failed = []
    for i, (district, start, end) in enumerate(todo, 1):
        try:
            run_district(district, start, end, WEATHER_BRONZE_DIR)
        except RateLimitError:
            logger.error("Daily limit reached after %d chunks. Re-run this command later to resume.", i - 1)
            raise SystemExit(3) from None
        except WeatherAPIError:
            logger.exception("Chunk failed: %s %s..%s (will retry on next run)", district, start, end)
            failed.append((district, start))
        if i % 25 == 0:
            logger.info("Progress: %d / %d", i, len(todo))
        time.sleep(PAUSE_BETWEEN_CALLS_S)

    logger.info("Backfill finished: %d ok, %d failed", len(todo) - len(failed), len(failed))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
