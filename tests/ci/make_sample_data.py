"""
Build a SMALL, deterministic bronze layer for CI (no internet needed):
  - synthetic daily weather for all 25 districts (fixed random seed)
  - the 3 real NDCU PDFs from tests/fixtures
Then CI runs the real pipeline on it:  parse -> silver -> SCD2 -> dbt build.

Run:  DW_DATA_DIR=ci_data python -m tests.ci.make_sample_data
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import NDCU_BRONZE_DIR, REFERENCE_DIR, WEATHER_BRONZE_DIR

FIXTURES = Path(__file__).parents[1] / "fixtures"
START, END = "2026-04-01", "2026-09-20"


def main() -> None:
    rng = np.random.default_rng(42)                     # same data on every run
    WEATHER_BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(START, END)
    for district in pd.read_csv(REFERENCE_DIR / "districts.csv")["district"]:
        pd.DataFrame({
            "district": district,
            "date": days.strftime("%Y-%m-%d"),
            "rainfall_mm": rng.gamma(1.0, 6.0, len(days)).round(1),
            "temperature_2m_mean": rng.normal(27.5, 1.0, len(days)).round(1),
            "temperature_2m_max": 31.0,
            "temperature_2m_min": 23.0,
            "latitude": 0.0,
            "longitude": 0.0,
            "fetched_at": "2026-01-01T00:00:00Z",
        }).to_csv(WEATHER_BRONZE_DIR / f"{district}_daily_{START}_{END}.csv", index=False)

    NDCU_BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    for pdf in FIXTURES.glob("*.pdf"):
        shutil.copy2(pdf, NDCU_BRONZE_DIR / pdf.name)
    print(f"Sample bronze ready: {len(days)} days x 25 districts, {len(list(FIXTURES.glob('*.pdf')))} NDCU PDFs")


if __name__ == "__main__":
    main()
