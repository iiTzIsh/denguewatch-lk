"""
Day 7: load ALL city weather CSVs into DuckDB and build a weekly table (Sat->Fri epi weeks).

Run:  python -m src.load.duckdb_load
Out:  data/denguewatch.duckdb  with tables  weather_daily, weather_weekly
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

DB_PATH = Path("data/denguewatch.duckdb")
WEATHER_GLOB = "data/bronze/weather/*_daily_*.csv"   # skips the old colombo_daily.csv (no city column)


def load_weather(con: duckdb.DuckDBPyConnection, csv_glob: str) -> int:
    """
    Load every matching CSV into weather_daily.
    Idempotent: CREATE OR REPLACE rebuilds the table, so re-running never duplicates rows.
    DISTINCT drops exact duplicate rows if two files overlap (e.g. 2024 + Jan-2024 pulls).
    """
    con.execute(
        """
        CREATE OR REPLACE TABLE weather_daily AS
        SELECT DISTINCT
            city,
            CAST(date AS DATE)          AS date,
            rainfall_mm,
            temperature_2m_mean         AS temp_mean_c,
            temperature_2m_max          AS temp_max_c,
            temperature_2m_min          AS temp_min_c
        FROM read_csv_auto(?, union_by_name = true)
        """,
        [csv_glob],
    )
    row = con.execute("SELECT COUNT(*) FROM weather_daily").fetchone()
    n = row[0] if row else 0
    logger.info("weather_daily: %d rows", n)
    return n


# Sri Lanka epi weeks run Saturday -> Friday.
# DuckDB dayofweek(): Sunday=0 ... Saturday=6  ->  days since last Saturday = (dayofweek + 1) % 7
WEEKLY_SQL = """
CREATE OR REPLACE TABLE weather_weekly AS
SELECT
    city,
    date - CAST((dayofweek(date) + 1) % 7 AS INTEGER)     AS epi_week_start,   -- a Saturday
    date - CAST((dayofweek(date) + 1) % 7 AS INTEGER) + 6 AS epi_week_end,     -- the Friday
    ROUND(SUM(rainfall_mm), 1)  AS rainfall_mm_total,
    ROUND(AVG(temp_mean_c), 1)  AS temp_mean_c,
    MAX(temp_max_c)             AS temp_max_c,
    MIN(temp_min_c)             AS temp_min_c,
    COUNT(*)                    AS days_in_week                                -- < 7 = partial week
FROM weather_daily
GROUP BY ALL
ORDER BY city, epi_week_start
"""


def build_weekly(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(WEEKLY_SQL)
    row = con.execute("SELECT COUNT(*) FROM weather_weekly").fetchone()
    n = row[0] if row else 0
    logger.info("weather_weekly: %d rows", n)
    return n


def main() -> None:
    setup_logging()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        load_weather(con, WEATHER_GLOB)
        build_weekly(con)
        print(con.sql("SELECT * FROM weather_weekly WHERE city = 'colombo' LIMIT 6").df().to_string())


if __name__ == "__main__":
    main()
