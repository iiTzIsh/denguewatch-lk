"""Compare 2024 total rainfall across cities."""
from pathlib import Path

import pandas as pd

files = sorted(Path("data/bronze/weather").glob("*_daily_2024-01-01_2024-12-31.csv"))
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)  # stack all cities into one table

summary = (
    df.groupby("city")["rainfall_mm"]
    .agg(total_mm="sum", rainy_days=lambda s: (s > 1).sum())   # rainy day = more than 1 mm
    .sort_values("total_mm", ascending=False)
    .round(1)
)
print(summary)