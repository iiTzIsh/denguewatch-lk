"""
Read the ML feature table (gold.mart_ml_features, built by dbt) into pandas.

The SQL does the heavy lifting (lags, weather windows, targets). Here we only add the
seasonal-naive reference for the TARGET week, which needs a lookup across rows.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from src.config import DB_PATH

HORIZONS = (2, 4)
TARGETS = {h: f"target_cases_h{h}" for h in HORIZONS}
THRESHOLDS = {h: f"target_threshold_h{h}" for h in HORIZONS}

# Everything the model is allowed to see (all known at week_end)
FEATURES = [
    "cases", "cases_lag1", "cases_lag2", "cases_lag3", "cases_lag4",
    "cases_mean_4w", "cases_mean_8w", "cases_same_week_last_year",
    "endemic_mean_5y", "endemic_sd_5y",
    "rain_w0_mm", "rain_w1_mm", "rain_w2_mm", "rain_w3_mm",
    "rain_w4_7_mm", "rain_w8_11_mm", "rain_w12_15_mm",
    "rainy_days_4w", "temp_mean_4w_c", "temp_min_4w_c",
    "month", "rdhs",
]
CATEGORICAL = ["rdhs"]


def load_features(db_path: str | None = None) -> pd.DataFrame:
    with duckdb.connect(str(db_path or DB_PATH), read_only=True) as con:
        df = con.sql("select * from gold.mart_ml_features order by rdhs, week_start").df()
    df["week_start"] = pd.to_datetime(df["week_start"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    for h in HORIZONS:
        df[f"seasonal_naive_h{h}"] = seasonal_reference(df, h)
    return df


def seasonal_reference(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Cases in the same region one year before the TARGET week (target week_end - 364 days, +-3 days).

    For a row ending on day D, the target week ends on D + 7h, so we look up the week ending near D + 7h - 364.
    Everything looked up is in the past relative to D, so this is a legal (no-leakage) baseline.
    """
    lookup = df[["rdhs", "week_end", "cases"]].rename(columns={"week_end": "ref_end", "cases": "ref_cases"})
    want = df[["rdhs", "week_end"]].copy()
    want["ref_end"] = want["week_end"] + pd.Timedelta(days=7 * horizon - 364)
    want["_row"] = range(len(want))
    merged = pd.merge_asof(
        want.sort_values("ref_end"), lookup.sort_values("ref_end"),
        on="ref_end", by="rdhs", direction="nearest", tolerance=pd.Timedelta(days=3),
    )
    return merged.sort_values("_row")["ref_cases"].set_axis(df.index)
