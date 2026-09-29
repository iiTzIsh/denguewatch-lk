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


def _path(env_var: str, default: Path) -> Path:
    value = os.getenv(env_var)
    return Path(value) if value else default


DATA_DIR = _path("DW_DATA_DIR", PROJECT_ROOT / "data")
LOG_DIR = _path("DW_LOG_DIR", PROJECT_ROOT / "logs")
DB_PATH = _path("DW_DB_PATH", DATA_DIR / "denguewatch.duckdb")

BRONZE_DIR = DATA_DIR / "bronze"
WEATHER_BRONZE_DIR = BRONZE_DIR / "weather_district"   # old city-level pulls stay in bronze/weather (unused)
WER_BRONZE_DIR = BRONZE_DIR / "wer"

REFERENCE_DIR = PROJECT_ROOT / "reference"   # small files, versioned in git
SQL_DIR = PROJECT_ROOT / "sql"
