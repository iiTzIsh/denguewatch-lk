"""Read-only queries behind the dashboard (kept separate from the UI so they can be unit-tested)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.config import DB_PATH


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def available_weeks(con: duckdb.DuckDBPyConnection) -> list[str]:
    """ISO week keys that have NDCU data, newest first."""
    rows = con.execute(
        "SELECT DISTINCT iso_week_key FROM gold.mart_ndcu_monitoring ORDER BY iso_week_key DESC"
    ).fetchall()
    return [r[0] for r in rows]


def week_snapshot(con: duckdb.DuckDBPyConnection, week: str) -> pd.DataFrame:
    """One row per district for the chosen week."""
    return con.execute(
        """
        SELECT district, province, iso_week_key, week_start, cases,
               cases_change_vs_prev_week AS change_vs_prev_week, any_restated,
               rainfall_mm_total AS rain_mm, rain_lag2_mm, rain_lag4_mm
        FROM gold.mart_ndcu_monitoring
        WHERE iso_week_key = ?
        ORDER BY cases DESC
        """,
        [week],
    ).df()


def national_totals(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Cases per reported week, all districts."""
    return con.execute(
        """
        SELECT iso_week_key, min(week_start) AS week_start, sum(cases) AS cases
        FROM gold.mart_ndcu_monitoring GROUP BY 1 ORDER BY 2
        """
    ).df()


def district_trend(con: duckdb.DuckDBPyConnection, district: str) -> pd.DataFrame:
    return con.execute(
        """
        SELECT iso_week_key, week_start, cases, rainfall_mm_total AS rain_mm
        FROM gold.mart_ndcu_monitoring WHERE district = ? ORDER BY week_start
        """,
        [district],
    ).df()


def district_rain(con: duckdb.DuckDBPyConnection, district: str, since: str) -> pd.DataFrame:
    """Weekly rainfall (ISO weeks) for one district from a start date - continuous, no gaps."""
    return con.execute(
        """
        SELECT f.week_start, f.rainfall_mm_total AS rain_mm
        FROM gold.fact_weather_iso_weekly f
        JOIN gold.dim_district d USING (district_sk)
        WHERE d.district = ? AND f.week_start >= CAST(? AS DATE)
        ORDER BY f.week_start
        """,
        [district, since],
    ).df()


def freshness(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    row = con.execute(
        """
        SELECT (SELECT max(week_end) FROM gold.fact_dengue_ndcu_weekly),
               (SELECT max(date) FROM main.weather_daily)
        """
    ).fetchone()
    return {"ndcu_until": row[0] if row else None, "weather_until": row[1] if row else None}
