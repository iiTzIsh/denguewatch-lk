"""
Compare Open-Meteo reanalysis models for ONE district and ONE week: which ones return rainfall?
Run BEFORE a big backfill:  python -m src.extract.weather_model_check
"""
from __future__ import annotations

import requests

from src.extract.weather import ARCHIVE_URL, DAILY_VARS, DISTRICTS

MODELS = ["era5_seamless", "era5", "era5_land", "best_match"]


def main() -> None:
    lat, lon = DISTRICTS["colombo"]
    print(f"Colombo centroid {lat},{lon}  |  2024-05-01..2024-05-07\n")
    print(f"{'model':15} " + " ".join(f"{v:>22}" for v in DAILY_VARS))
    for model in MODELS:
        params: dict[str, str | float] = {
            "latitude": lat, "longitude": lon, "start_date": "2024-05-01", "end_date": "2024-05-07",
            "daily": ",".join(DAILY_VARS), "models": model, "timezone": "Asia/Colombo",
        }
        r = requests.get(ARCHIVE_URL, timeout=30, params=params)
        if r.status_code != 200:
            print(f"{model:15} HTTP {r.status_code}: {r.text[:120]}")
            continue
        daily = r.json()["daily"]
        cells = [f"{sum(x is not None for x in daily[v])}/7 non-empty" for v in DAILY_VARS]
        print(f"{model:15} " + " ".join(f"{c:>22}" for c in cells))


if __name__ == "__main__":
    main()
