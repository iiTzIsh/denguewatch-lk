"""Fetch daily weather per district centroid from the Open-Meteo archive API into bronze CSVs.

Run:  python -m src.extract.weather --start 2024-01-01 --end 2024-12-31 --district all
      python -m src.extract.weather --as-of 2026-09-28 --days-back 35 --district all   (Airflow)
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.config import REFERENCE_DIR, WEATHER_BRONZE_DIR, WEATHER_MODEL
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "precipitation_sum",  # rainfall, mm
    "temperature_2m_mean",  # deg C
    "temperature_2m_max",
    "temperature_2m_min",
]
# One reanalysis for all years: "best_match" switches to IFS from 2017, causing drift.
# Not era5_land: it has no precipitation.
MODEL = WEATHER_MODEL
DISTRICTS_CSV = REFERENCE_DIR / "districts.csv"
TIMEOUT_S = 30
ARCHIVE_LAG_DAYS = 6  # ERA5 lags ~5 days, so request only up to 6 days before the run date
PAUSE_BETWEEN_CALLS_S = 1.0


class WeatherAPIError(Exception):
    """Raised when the API keeps failing or returns bad data."""


class RateLimitError(WeatherAPIError):
    """HTTP 429: free-tier limit reached; stop and resume later."""


def load_districts(path: Path = DISTRICTS_CSV) -> dict[str, tuple[float, float]]:
    """Return {district_slug: (lat, lon)} from the reference file."""
    ref = pd.read_csv(path)
    return {
        str(d): (float(lat), float(lon))
        for d, lat, lon in zip(ref["district"], ref["latitude"], ref["longitude"], strict=True)
    }


DISTRICTS = load_districts()


def build_params(lat: float, lon: float, start: str, end: str) -> dict[str, Any]:
    """Query parameters for the archive endpoint; dates are 'YYYY-MM-DD'."""
    return {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": ",".join(DAILY_VARS),
        "models": MODEL,
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
    """Call the API and return the JSON payload.

    Retries network errors and 5xx responses with linear backoff; 4xx responses are not retried.
    """
    session = session or requests.Session()
    params = build_params(lat, lon, start, end)

    for attempt in range(1, retries + 1):
        try:
            logger.info("Request attempt %d/%d: %s -> %s", attempt, retries, start, end)
            logger.debug("GET %s params=%s", ARCHIVE_URL, params)
            resp = session.get(ARCHIVE_URL, params=params, timeout=TIMEOUT_S)
            logger.debug("Status %s", resp.status_code)
            if resp.status_code == 429:
                raise RateLimitError(f"Rate limit reached (429): {resp.text[:200]}")
            if 400 <= resp.status_code < 500:
                raise WeatherAPIError(f"Client error {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            return resp.json()
        except WeatherAPIError:
            raise
        except requests.RequestException as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt == retries:
                raise WeatherAPIError(f"Gave up after {retries} attempts") from exc
            time.sleep(backoff_s * attempt)

    raise WeatherAPIError("unreachable")  # for type checkers


def to_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert the API JSON into a DataFrame with one row per day."""
    daily = payload.get("daily")
    if not daily or "time" not in daily:
        raise WeatherAPIError("Payload has no 'daily' data")

    df = pd.DataFrame(daily).rename(columns={"time": "date", "precipitation_sum": "rainfall_mm"})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["latitude"] = payload.get("latitude")
    df["longitude"] = payload.get("longitude")
    # newest pull wins when files overlap at load time
    df["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


MAX_NULL_SHARE = 0.05  # reject the pull if any column is more than 5% missing
REQUIRED_COLS = ["date", "rainfall_mm", "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min"]


def validate_weather(df: pd.DataFrame) -> pd.DataFrame:
    """Raise on invalid data, warn on a small number of missing values."""
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        raise WeatherAPIError(f"Missing columns: {missing_cols}")

    if (df["rainfall_mm"] < 0).any():
        raise WeatherAPIError("Negative rainfall found")

    if (df["temperature_2m_min"] > df["temperature_2m_max"]).any():
        raise WeatherAPIError("temp_min > temp_max found")

    if df["date"].duplicated().any():
        raise WeatherAPIError("Duplicate dates found")

    null_share = df[REQUIRED_COLS].isna().mean()
    too_many = null_share[null_share > MAX_NULL_SHARE]
    if not too_many.empty:
        raise WeatherAPIError(f"Too many missing values: {too_many.round(3).to_dict()}")
    n_null = int(df[REQUIRED_COLS].isna().sum().sum())
    if n_null:
        logger.warning("%d missing values in weather data", n_null)

    logger.debug("Validation passed: %d rows, %s -> %s", len(df), df["date"].min(), df["date"].max())
    return df


def save_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write the CSV, creating parent folders if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Saved %d rows -> %s", len(df), path)
    return path


def valid_date(text: str) -> str:
    """argparse type that rejects invalid YYYY-MM-DD dates."""
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"'{text}' is not a valid date (use YYYY-MM-DD)") from exc
    return text


def window_from_as_of(as_of: str, days_back: int) -> tuple[str, str]:
    """Return a (start, end) window ending ARCHIVE_LAG_DAYS before as_of."""
    end = date.fromisoformat(as_of) - timedelta(days=ARCHIVE_LAG_DAYS)
    start = end - timedelta(days=days_back - 1)
    return start.isoformat(), end.isoformat()


def output_path(out_dir: Path, district: str, start: str, end: str) -> Path:
    return out_dir / f"{district}_daily_{start}_{end}.csv"


def run_district(district: str, start: str, end: str, out_dir: Path) -> Path:
    """Fetch, validate and save one district; return the CSV path."""
    lat, lon = DISTRICTS[district]
    payload = fetch_daily_weather(lat, lon, start, end)
    df = validate_weather(to_dataframe(payload))
    df.insert(0, "district", district)
    return save_csv(df, output_path(out_dir, district, start, end))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Open-Meteo daily weather -> CSV")
    parser.add_argument("--start", type=valid_date, help="YYYY-MM-DD")
    parser.add_argument("--end", type=valid_date, help="YYYY-MM-DD")
    parser.add_argument("--as-of", type=valid_date, help="YYYY-MM-DD run date (instead of --start/--end)")
    parser.add_argument("--days-back", type=int, default=35, help="window size used with --as-of")
    parser.add_argument("--district", default="colombo", choices=[*DISTRICTS, "all"])
    parser.add_argument("--out-dir", default=str(WEATHER_BRONZE_DIR))
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    if args.as_of:
        args.start, args.end = window_from_as_of(args.as_of, args.days_back)
    elif not (args.start and args.end):
        parser.error("give --start and --end, or --as-of")
    if args.start > args.end:  # 'YYYY-MM-DD' strings sort correctly as text
        parser.error("--start must be on or before --end")

    setup_logging(args.log_level)
    districts = list(DISTRICTS) if args.district == "all" else [args.district]
    failed: list[str] = []

    for i, district in enumerate(districts):
        if i > 0:
            time.sleep(PAUSE_BETWEEN_CALLS_S)
        try:
            run_district(district, args.start, args.end, Path(args.out_dir))
        except RateLimitError:
            logger.error("Rate limit hit at %s - stopping. Re-run later.", district)
            raise SystemExit(3) from None
        except WeatherAPIError:
            logger.exception("Failed for %s - continuing with the rest", district)
            failed.append(district)

    logger.info("Done: %d ok, %d failed", len(districts) - len(failed), len(failed))
    if failed:
        logger.error("Failed districts: %s", failed)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
