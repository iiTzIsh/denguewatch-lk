"""
Silver load: ALL district weather CSVs -> DuckDB + a weekly table (Sat->Fri epi weeks).

Run:  python -m src.load.duckdb_load
Out:  data/denguewatch.duckdb  with tables  dim_district, dim_rdhs, weather_daily, weather_weekly,
      ndcu_weekly_cases
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.config import DB_PATH, PARSED_DIR, REFERENCE_DIR, WEATHER_BRONZE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

WEATHER_GLOB = str(WEATHER_BRONZE_DIR / "*_daily_*.csv")
DISTRICTS_CSV = str(REFERENCE_DIR / "districts.csv")
RDHS_CSV = str(REFERENCE_DIR / "rdhs.csv")
NDCU_GLOB = str(PARSED_DIR / "ndcu_weekly" / "*.csv")


def load_reference(con: duckdb.DuckDBPyConnection, csv_path: str = DISTRICTS_CSV) -> int:
    """Reference (lookup) table: one row per district. Small, versioned in git."""
    con.execute("CREATE OR REPLACE TABLE dim_district AS SELECT * FROM read_csv_auto(?)", [csv_path])
    con.execute("CREATE OR REPLACE TABLE dim_rdhs AS SELECT * FROM read_csv_auto(?)", [RDHS_CSV])
    row = con.execute("SELECT COUNT(*) FROM dim_district").fetchone()
    n = row[0] if row else 0
    logger.info("dim_district: %d rows", n)
    return n


def orphan_districts(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Districts in the weather data with NO match in dim_district (anti-join). Should be empty."""
    rows = con.execute(
        """
        SELECT DISTINCT w.district
        FROM weather_daily w
        LEFT JOIN dim_district d ON w.district = d.district
        WHERE d.district IS NULL
        """
    ).fetchall()
    return [r[0] for r in rows]


def load_weather(con: duckdb.DuckDBPyConnection, csv_glob: str) -> int:
    """
    Load every matching CSV into weather_daily.
    Idempotent: CREATE OR REPLACE rebuilds the table, so re-running never duplicates rows.
    Overlapping files (weekly Airflow pulls overlap on purpose) -> newest fetched_at wins per district+day.
    """
    con.execute(
        "CREATE OR REPLACE TEMP TABLE raw_weather AS "
        "SELECT * FROM read_csv(?, header = true, union_by_name = true, filename = true, "
        # explicit schema: an all-empty column can't be mis-detected as text any more
        "types = {'rainfall_mm': 'DOUBLE', 'temperature_2m_mean': 'DOUBLE', "
        "'temperature_2m_max': 'DOUBLE', 'temperature_2m_min': 'DOUBLE', 'date': 'DATE'})",
        [csv_glob],
    )
    cols = {r[0] for r in con.execute("DESCRIBE raw_weather").fetchall()}
    # older files were saved before we added fetched_at -> treat as "oldest"
    fetched = "fetched_at" if "fetched_at" in cols else "CAST(NULL AS VARCHAR)"
    con.execute(
        f"""
        CREATE OR REPLACE TABLE weather_daily AS
        SELECT
            district,
            CAST(date AS DATE)          AS date,
            rainfall_mm,
            temperature_2m_mean         AS temp_mean_c,
            temperature_2m_max          AS temp_max_c,
            temperature_2m_min          AS temp_min_c
        FROM raw_weather
        -- keep ONE row per district + day: the newest fetch wins
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY district, CAST(date AS DATE)
            ORDER BY {fetched} DESC NULLS LAST, filename DESC
        ) = 1
        """
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
    district,
    date - CAST((dayofweek(date) + 1) % 7 AS INTEGER)     AS epi_week_start,   -- a Saturday
    date - CAST((dayofweek(date) + 1) % 7 AS INTEGER) + 6 AS epi_week_end,     -- the Friday
    ROUND(SUM(rainfall_mm), 1)  AS rainfall_mm_total,
    ROUND(AVG(temp_mean_c), 1)  AS temp_mean_c,
    MAX(temp_max_c)             AS temp_max_c,
    MIN(temp_min_c)             AS temp_min_c,
    COUNT(*)                    AS days_in_week                                -- < 7 = partial week
FROM weather_daily
GROUP BY ALL
ORDER BY district, epi_week_start
"""


def build_weekly(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(WEEKLY_SQL)
    row = con.execute("SELECT COUNT(*) FROM weather_weekly").fetchone()
    n = row[0] if row else 0
    logger.info("weather_weekly: %d rows", n)
    return n


NDCU_DDL = """
CREATE OR REPLACE TABLE ndcu_weekly_cases (
    year INTEGER, iso_week INTEGER, week_start DATE, week_end DATE, rdhs VARCHAR,
    cases_prev_year_prev_week INTEGER, cases_prev_year_this_week INTEGER,
    cases_prev_week INTEGER, cases_this_week INTEGER, cum_prev_year INTEGER, cum_this_year INTEGER,
    has_revised_value BOOLEAN, total_check VARCHAR, source_file VARCHAR, parsed_at VARCHAR
)
"""


def load_ndcu(con: duckdb.DuckDBPyConnection, csv_glob: str = NDCU_GLOB) -> int:
    """Parsed NDCU weeks -> silver. Table always exists (empty if nothing parsed yet) so dbt never breaks.
    One row per year + ISO week + RDHS: if a week was parsed twice, the newest parse wins."""
    con.execute(NDCU_DDL)
    if not list(Path(csv_glob).parent.glob(Path(csv_glob).name)):
        logger.info("ndcu_weekly_cases: 0 rows (no parsed NDCU files yet)")
        return 0
    con.execute(
        "CREATE OR REPLACE TEMP TABLE raw_ndcu AS SELECT * FROM read_csv(?, header = true, union_by_name = true)",
        [csv_glob],
    )
    cols = {r[0] for r in con.execute("DESCRIBE raw_ndcu").fetchall()}
    total_check = "total_check" if "total_check" in cols else "CAST(NULL AS VARCHAR)"  # files parsed before v2
    con.execute(
        f"""
        INSERT INTO ndcu_weekly_cases
        SELECT year, iso_week, week_start, week_end, rdhs,
               cases_prev_year_prev_week, cases_prev_year_this_week, cases_prev_week, cases_this_week,
               cum_prev_year, cum_this_year, has_revised_value, {total_check}, source_file, parsed_at
        FROM raw_ndcu
        QUALIFY ROW_NUMBER() OVER (PARTITION BY year, iso_week, rdhs ORDER BY parsed_at DESC) = 1
        """
    )
    row = con.execute("SELECT COUNT(*) FROM ndcu_weekly_cases").fetchone()
    n = row[0] if row else 0
    logger.info("ndcu_weekly_cases: %d rows", n)
    return n


def main() -> None:
    setup_logging()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        load_reference(con)
        load_weather(con, WEATHER_GLOB)
        build_weekly(con)
        load_ndcu(con)
        orphans = orphan_districts(con)
        if orphans:
            raise SystemExit(f"Weather districts missing from {DISTRICTS_CSV}: {orphans}")
        print(con.sql("SELECT * FROM weather_weekly WHERE district = 'colombo' LIMIT 6").df().to_string())


if __name__ == "__main__":
    main()
