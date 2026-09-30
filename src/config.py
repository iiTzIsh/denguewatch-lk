"""
All settings in ONE place. Values come from environment variables, with local defaults.

Local:   nothing to set - defaults point inside the project folder.
Docker:  docker-compose.yml sets DW_DATA_DIR=/app/data etc.
Cloud:   later, the same variables point at cloud storage - code doesn't change.

Paths are ABSOLUTE (built from PROJECT_ROOT), so scripts work from any working directory
(Airflow does NOT run your code from the project folder).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Tiny .env reader (KEY=value lines). Real environment variables always win. .env is gitignored."""
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
# Weather model is part of the bronze path: raw data from different models is NEVER mixed or overwritten.
# era5_seamless = ERA5 precipitation + ERA5-Land temperature, one consistent reanalysis for all years.
WEATHER_MODEL = os.getenv("DW_WEATHER_MODEL", "era5_seamless")
WEATHER_BRONZE_DIR = BRONZE_DIR / "weather_district" / WEATHER_MODEL
WER_BRONZE_DIR = BRONZE_DIR / "wer"

NDCU_BRONZE_DIR = BRONZE_DIR / "ndcu" / "weekly"             # raw weekly update PDFs
WER_HISTORY_BRONZE_DIR = BRONZE_DIR / "wer_history"            # denguedatahub .rda (WER-derived history)
PARSED_DIR = DATA_DIR / "parsed"                               # tables extracted from PDFs (-> silver)
QUARANTINE_DIR = DATA_DIR / "quarantine"                       # files that failed parsing/validation

ALERTS_DIR = DATA_DIR / "alerts"                               # remembers which weeks were already sent

REFERENCE_DIR = PROJECT_ROOT / "reference"   # small files, versioned in git
SQL_DIR = PROJECT_ROOT / "sql"
