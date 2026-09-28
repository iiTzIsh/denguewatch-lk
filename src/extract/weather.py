"""
Fetch daily weather for one location from the Open-Meteo archive API -> CSV.

Run (from project root):
    python -m src.extract.weather --start 2024-01-01 --end 2024-12-31
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)  # "src.extract.weather" in log lines

# ---- constants (no magic values buried in code) ----
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "precipitation_sum",       # rainfall, mm
    "temperature_2m_mean",     # deg C
    "temperature_2m_max",
    "temperature_2m_min",
]
COLOMBO_LAT = 6.9271
COLOMBO_LON = 79.8612
TIMEOUT_S = 30


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Open-Meteo daily weather -> CSV")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--lat", type=float, default=COLOMBO_LAT)
    parser.add_argument("--lon", type=float, default=COLOMBO_LON)
    parser.add_argument("--out", default="data/bronze/weather/colombo_daily.csv")
    args = parser.parse_args()

    setup_logging()
    try:
        payload = fetch_daily_weather(args.lat, args.lon, args.start, args.end)
        df = to_dataframe(payload)
        save_csv(df, Path(args.out))
        logger.info("Total rainfall: %.1f mm over %d days", df["rainfall_mm"].sum(), len(df))
    except WeatherAPIError:
        logger.exception("Weather fetch failed")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
