"""Project settings, read from environment variables (and an optional .env) with local defaults.

Paths are absolute (built from PROJECT_ROOT) so scripts work from any working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Load KEY=value lines from .env; existing environment variables take precedence."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _path(env_var: str, default: Path) -> Path:
    value = os.getenv(env_var)
    return Path(value) if value else default


DATA_DIR = _path("DW_DATA_DIR", PROJECT_ROOT / "data")
LOG_DIR = _path("DW_LOG_DIR", PROJECT_ROOT / "logs")
DB_PATH = _path("DW_DB_PATH", DATA_DIR / "denguewatch.duckdb")

BRONZE_DIR = DATA_DIR / "bronze"
# Model is part of the bronze path so raw data from different models is never mixed.
# era5_seamless = ERA5 precipitation + ERA5-Land temperature, consistent across all years.
WEATHER_MODEL = os.getenv("DW_WEATHER_MODEL", "era5_seamless")
WEATHER_BRONZE_DIR = BRONZE_DIR / "weather_district" / WEATHER_MODEL
WER_BRONZE_DIR = BRONZE_DIR / "wer"

NDCU_BRONZE_DIR = BRONZE_DIR / "ndcu" / "weekly"
WER_HISTORY_BRONZE_DIR = BRONZE_DIR / "wer_history"  # denguedatahub .rda (WER-derived)
PARSED_DIR = DATA_DIR / "parsed"
QUARANTINE_DIR = DATA_DIR / "quarantine"  # files that failed parsing/validation

ALERTS_DIR = DATA_DIR / "alerts"  # records which weeks were already sent

REFERENCE_DIR = PROJECT_ROOT / "reference"  # small files, versioned in git

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MLFLOW_EXPERIMENT = os.getenv("DW_MLFLOW_EXPERIMENT", "denguewatch-forecast")
