"""
Day 7: load the weather CSV into DuckDB + a weekly aggregation (the "Done when" skill).

Run:  python -m src.load.duckdb_load
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

DB_PATH = Path("data/denguewatch.duckdb")
CSV_PATH = Path("data/bronze/weather/colombo_daily.csv")


def load_weather(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """Idempotent: CREATE OR REPLACE means re-running never duplicates rows."""
    con.execute(
        "CREATE OR REPLACE TABLE weather_daily AS SELECT * FROM read_csv_auto(?)",
        [str(csv_path)],
    )
    n = con.execute("SELECT COUNT(*) FROM weather_daily").fetchone()[0]
    logger.info("Loaded %d rows into weather_daily", n)
    return n


WEEKLY_SQL = """
SELECT
    date_trunc('week', date)           AS week_start,   -- ISO weeks start Monday
    ROUND(SUM(rainfall_mm), 1)         AS rainfall_mm_total,
    ROUND(AVG(temperature_2m_mean), 1) AS temp_mean_c,
    COUNT(*)                           AS days_in_week
FROM weather_daily
GROUP BY 1
ORDER BY 1
"""


def main() -> None:
    setup_logging()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        load_weather(con, CSV_PATH)
        print(con.sql(WEEKLY_SQL).df().head(10).to_string())


if __name__ == "__main__":
    main()
