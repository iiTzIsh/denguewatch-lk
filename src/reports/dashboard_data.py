"""Read-only queries behind the dashboard (kept separate from the UI so they can be unit-tested)."""
from __future__ import annotations

from datetime import date
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
        SELECT district, province, iso_week_key, week_start, cases, population, cases_per_100k,
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


def freshness(con: duckdb.DuckDBPyConnection) -> dict[str, date | None]:
    row = con.execute(
        """
        SELECT (SELECT max(week_end) FROM gold.fact_dengue_ndcu_weekly),
               (SELECT max(date) FROM main.weather_daily)
        """
    ).fetchone()
    return {"ndcu_until": row[0] if row else None, "weather_until": row[1] if row else None}


FORECAST_SQL = """
SELECT
    rdhs, district, base_week_end, cases_now, model_version,
    max(pred_cases)     FILTER (WHERE horizon_weeks = 2) AS pred_2w,
    max(outbreak_level) FILTER (WHERE horizon_weeks = 2) AS level_2w,
    max(risk_level)     FILTER (WHERE horizon_weeks = 2) AS risk_2w,
    max(pred_cases)     FILTER (WHERE horizon_weeks = 4) AS pred_4w,
    max(outbreak_level) FILTER (WHERE horizon_weeks = 4) AS level_4w,
    max(risk_level)     FILTER (WHERE horizon_weeks = 4) AS risk_4w
FROM ml.forecast_latest
GROUP BY ALL
ORDER BY
    least(CASE max(risk_level) FILTER (WHERE horizon_weeks = 2) WHEN 'high' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END,
          CASE max(risk_level) FILTER (WHERE horizon_weeks = 4) WHEN 'high' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END),
    max(pred_cases / outbreak_level) FILTER (WHERE horizon_weeks = 4) DESC NULLS LAST
"""


def latest_forecast(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Newest batch of forecasts, one row per region, riskiest first. Empty if none scored yet."""
    try:
        return con.execute(FORECAST_SQL).df()
    except duckdb.CatalogException:        # ml.forecast_latest not created yet (python -m src.ml.predict)
        return pd.DataFrame()


# ---------------- model health (forecast vs actual + data drift) ----------------
PERFORMANCE_SQL = """
SELECT
    model_name, horizon_weeks,
    count(*)                                               AS forecasts,
    min(target_week_end)                                   AS first_target_week,
    max(target_week_end)                                   AS last_target_week,
    avg(abs_error)                                         AS mae,
    avg(naive_abs_error)                                   AS naive_mae,
    1 - avg(abs_error) / nullif(avg(naive_abs_error), 0)   AS skill_vs_naive,
    count(*) FILTER (WHERE outbreak_happened)              AS outbreak_weeks,
    count(*) FILTER (WHERE alerted)                        AS alerts,
    count(*) FILTER (WHERE alerted AND outbreak_happened)  AS correct_alerts
FROM gold.mart_forecast_accuracy
GROUP BY ALL
ORDER BY model_name, horizon_weeks
"""


def model_performance(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Forecast vs actual per model and horizon. Empty until forecasts have matured."""
    try:
        return con.execute(PERFORMANCE_SQL).df()
    except duckdb.CatalogException:
        return pd.DataFrame()


def forecast_vs_actual(con: duckdb.DuckDBPyConnection, horizon: int = 4) -> pd.DataFrame:
    """National totals per target week: actual, model forecast, naive. One forecast per region and
    target week (the live champion if it exists, otherwise the as-of replay)."""
    try:
        return con.execute(
            """
            WITH one AS (
                SELECT * FROM gold.mart_forecast_accuracy
                WHERE horizon_weeks = ?
                QUALIFY row_number() OVER (PARTITION BY rdhs, target_week_end
                                           ORDER BY model_name = 'asof-replay', scored_at DESC) = 1
            )
            SELECT target_week_end, sum(actual_cases) AS actual, sum(pred_cases) AS forecast,
                   sum(naive_pred_cases) AS naive, count(*) AS regions
            FROM one GROUP BY 1 ORDER BY 1
            """,
            [horizon],
        ).df()
    except duckdb.CatalogException:
        return pd.DataFrame()


def latest_drift(con: duckdb.DuckDBPyConnection) -> dict | None:
    try:
        df = con.execute("SELECT * FROM ml.drift_runs ORDER BY checked_at DESC LIMIT 1").df()
    except duckdb.CatalogException:
        return None
    return None if df.empty else {str(k): v for k, v in df.iloc[0].to_dict().items()}
