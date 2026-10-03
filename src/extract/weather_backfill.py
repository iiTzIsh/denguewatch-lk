"""Resumable weather backfill: one file per district per year; existing files are skipped.

Run:  python -m src.extract.weather_backfill [--from-year 2006]    (up to the latest available day)
Exit codes: 3 = daily rate limit reached, 4 = API unreachable; re-run later to resume.
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
    """Return (start, end) per calendar year; the last chunk ends at last_day."""
    chunks = []
    for y in range(from_year, last_day.year + 1):
        start = date(y, 1, 1)
        end = min(date(y, 12, 31), last_day)
        chunks.append((start.isoformat(), end.isoformat()))
    return chunks


def plan(from_year: int, last_day: date) -> list[tuple[str, str, str]]:
    """Return every (district, start, end) chunk not yet on disk."""
    todo = []
    for start, end in year_chunks(from_year, last_day):
        for d in DISTRICTS:
            if not output_path(WEATHER_BRONZE_DIR, d, start, end).exists():
                todo.append((d, start, end))
    return todo


MAX_CONSECUTIVE_FAILURES = 5  # treat this many failures in a row as "API unreachable"
UNREACHABLE = 4  # exit code


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
    in_a_row = 0
    for i, (district, start, end) in enumerate(todo, 1):
        try:
            run_district(district, start, end, WEATHER_BRONZE_DIR)
            in_a_row = 0
        except RateLimitError:
            logger.error("Daily limit reached after %d chunks. Re-run this command later to resume.", i - 1)
            raise SystemExit(3) from None
        except WeatherAPIError:
            logger.exception("Chunk failed: %s %s..%s (will retry on next run)", district, start, end)
            failed.append((district, start))
            in_a_row += 1
            if in_a_row >= MAX_CONSECUTIVE_FAILURES:
                logger.error("%d chunks failed in a row - Open-Meteo unreachable? Re-run later to resume.", in_a_row)
                raise SystemExit(UNREACHABLE) from None
        if i % 25 == 0:
            logger.info("Progress: %d / %d", i, len(todo))
        time.sleep(PAUSE_BETWEEN_CALLS_S)

    logger.info("Backfill finished: %d ok, %d failed", len(todo) - len(failed), len(failed))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
