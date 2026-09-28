"""
Fetch daily weather for one location from the Open-Meteo archive API -> CSV.

Run (from project root):
    python -m src.extract.weather --start 2024-01-01 --end 2024-12-31
    python -m src.extract.weather --start 2024-01-01 --end 2024-12-31 --city kandy
    python -m src.extract.weather --start 2024-01-01 --end 2024-12-31 --city all
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)  # "__main__" when run directly, "src.extract.weather" when imported

# ---- constants (no magic values buried in code) ----
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "precipitation_sum",       # rainfall, mm
    "temperature_2m_mean",     # deg C
    "temperature_2m_max",
    "temperature_2m_min",
]
# Approximate city-centre coordinates (NOT district centroids - we verify those in Phase 1)
CITIES: dict[str, tuple[float, float]] = {
    "colombo": (6.9271, 79.8612),
    "kandy": (7.2906, 80.6337),
    "galle": (6.0535, 80.2210),
    "jaffna": (9.6615, 80.0255),
    "kurunegala": (7.4863, 80.3647),
}
TIMEOUT_S = 30
PAUSE_BETWEEN_CALLS_S = 1.0  # be polite to the free API


class WeatherAPIError(Exception):
    """Raised when the API keeps failing or returns bad data."""


def build_params(lat: float, lon: float, start: str, end: str) -> dict[str, Any]:
    """Query-string params for the archive endpoint. Dates are 'YYYY-MM-DD'."""
    return {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": ",".join(DAILY_VARS),
        "timezone": "Asia/Colombo",
    }


def fetch_daily_weather(
    lat: float,
    lon: float,
    start: str,
    end: str,
    session: requests.Session | None = None,
    retries: int = 3,
    backoff_s: float = 2.0,
) -> dict[str, Any]:
    """
    Call the API and return the JSON payload.
    - Retries on network errors and 5xx (server) errors, waiting longer each time.
    - Does NOT retry 4xx (our request is wrong -> retrying won't help).
    """
    session = session or requests.Session()
    params = build_params(lat, lon, start, end)

    for attempt in range(1, retries + 1):
        try:
            logger.info("Request attempt %d/%d: %s -> %s", attempt, retries, start, end)
            resp = session.get(ARCHIVE_URL, params=params, timeout=TIMEOUT_S)
            if 400 <= resp.status_code < 500:
                raise WeatherAPIError(f"Client error {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()  # raises HTTPError on 5xx
            return resp.json()
        except WeatherAPIError:
            raise  # don't retry our own mistakes
        except requests.RequestException as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt == retries:
                raise WeatherAPIError(f"Gave up after {retries} attempts") from exc
            time.sleep(backoff_s * attempt)  # 2s, 4s, 6s ...

    raise WeatherAPIError("unreachable")  # keeps type checkers happy


def to_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    """Turn the API JSON into a tidy DataFrame (one row per day)."""
    daily = payload.get("daily")
    if not daily or "time" not in daily:
        raise WeatherAPIError("Payload has no 'daily' data")

    df = pd.DataFrame(daily).rename(columns={"time": "date", "precipitation_sum": "rainfall_mm"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["latitude"] = payload.get("latitude")
    df["longitude"] = payload.get("longitude")
    return df


def save_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write CSV, creating folders if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Saved %d rows -> %s", len(df), path)
    return path


def valid_date(text: str) -> str:
    """argparse 'type' function: reject bad dates BEFORE calling the API (fail fast)."""
    try:
        date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a valid date (use YYYY-MM-DD)")
    return text


def run_city(city: str, start: str, end: str, out_dir: Path) -> Path:
    """Fetch + convert + save for ONE city. Returns the CSV path."""
    lat, lon = CITIES[city]
    payload = fetch_daily_weather(lat, lon, start, end)
    df = to_dataframe(payload)
    df.insert(0, "city", city)  # first column = which city this row belongs to
    return save_csv(df, out_dir / f"{city}_daily_{start}_{end}.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Open-Meteo daily weather -> CSV")
    parser.add_argument("--start", required=True, type=valid_date, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=valid_date, help="YYYY-MM-DD")
    parser.add_argument("--city", default="colombo", choices=[*CITIES, "all"])
    parser.add_argument("--out-dir", default="data/bronze/weather")
    args = parser.parse_args()

    if args.start > args.end:  # 'YYYY-MM-DD' strings sort correctly as text
        parser.error("--start must be on or before --end")

    setup_logging()
    cities = list(CITIES) if args.city == "all" else [args.city]
    failed: list[str] = []

    for i, city in enumerate(cities):
        if i > 0:
            time.sleep(PAUSE_BETWEEN_CALLS_S)
        try:
            run_city(city, args.start, args.end, Path(args.out_dir))
        except WeatherAPIError:
            logger.exception("Failed for %s - continuing with the rest", city)
            failed.append(city)

    logger.info("Done: %d ok, %d failed", len(cities) - len(failed), len(failed))
    if failed:
        logger.error("Failed cities: %s", failed)
        raise SystemExit(1)


if __name__ == "__main__":
    main()