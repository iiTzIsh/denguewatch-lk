"""Load reference data, weather and parsed case CSVs into the DuckDB silver layer.

Run:  python -m src.load.duckdb_load
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.config import DB_PATH, PARSED_DIR, REFERENCE_DIR, WEATHER_BRONZE_DIR
from src.log_setup import setup_logging
from src.ml.monitor import DDL as DRIFT_DDL
from src.ml.predict import DDL as FORECAST_DDL

logger = logging.getLogger(__name__)

WEATHER_GLOB = str(WEATHER_BRONZE_DIR / "*_daily_*.csv")
DISTRICTS_CSV = str(REFERENCE_DIR / "districts.csv")
RDHS_CSV = str(REFERENCE_DIR / "rdhs.csv")
NDCU_GLOB = str(PARSED_DIR / "ndcu_weekly" / "*.csv")
WER_GLOB = str(PARSED_DIR / "wer_history" / "*.csv")
NDCU_MOH_GLOB = str(PARSED_DIR / "ndcu_moh" / "*.csv")
NDCU_MOH_DDL = """
CREATE OR REPLACE TABLE ndcu_moh_weekly_cases (
    iso_year INTEGER, iso_week INTEGER, week_start DATE, week_end DATE, province VARCHAR, district VARCHAR,
    moh_area VARCHAR, moh_key VARCHAR, cases_prev_week INTEGER, cases_this_week INTEGER,
    source_file VARCHAR, parsed_at VARCHAR
)
"""


def load_ndcu_moh(con: duckdb.DuckDBPyConnection, csv_glob: str = NDCU_MOH_GLOB) -> int:
    """Load high-risk MOH areas per NDCU week; the newest parse wins."""
    con.execute(NDCU_MOH_DDL)
    if not list(Path(csv_glob).parent.glob(Path(csv_glob).name)):
        logger.info("ndcu_moh_weekly_cases: 0 rows (run python -m src.transform.ndcu_moh_parse)")
        return 0
    con.execute(
        """
        INSERT INTO ndcu_moh_weekly_cases
        SELECT iso_year, iso_week, week_start, week_end, province, district, moh_area, moh_key,
               cases_prev_week, cases_this_week, source_file, parsed_at
        FROM read_csv(?, header = true, union_by_name = true)
        QUALIFY row_number() OVER (PARTITION BY week_start, moh_key ORDER BY parsed_at DESC) = 1
        """,
        [csv_glob],
    )
    row = con.execute("SELECT count(*) FROM ndcu_moh_weekly_cases").fetchone()
    n = row[0] if row else 0
    logger.info("ndcu_moh_weekly_cases: %d rows", n)
    return n


POPULATION_CSV = REFERENCE_DIR / "population" / "district_population_2024.csv"

POPULATION_DDL = """
CREATE OR REPLACE TABLE district_population (
    district VARCHAR, population BIGINT, census_year INTEGER, source VARCHAR
)
"""


def load_population(con: duckdb.DuckDBPyConnection, csv_path: Path = POPULATION_CSV) -> int:
    """Load Census 2024 district population; the table stays empty (rates NULL) if the CSV is absent."""
    con.execute(POPULATION_DDL)
    if not csv_path.exists():
        logger.info("district_population: 0 rows (run python -m src.reference.build_population)")
        return 0
    con.execute(
        "INSERT INTO district_population SELECT district, population, census_year, source "
        "FROM read_csv(?, header = true)",
        [str(csv_path)],
    )
    row = con.execute("SELECT count(*) FROM district_population").fetchone()
    n = row[0] if row else 0
    logger.info("district_population: %d rows", n)
    return n


def load_reference(con: duckdb.DuckDBPyConnection, csv_path: str = DISTRICTS_CSV) -> int:
    """Load the district and RDHS lookup tables."""
    con.execute("CREATE OR REPLACE TABLE dim_district AS SELECT * FROM read_csv_auto(?)", [csv_path])
    con.execute("CREATE OR REPLACE TABLE dim_rdhs AS SELECT * FROM read_csv_auto(?)", [RDHS_CSV])
    row = con.execute("SELECT COUNT(*) FROM dim_district").fetchone()
    n = row[0] if row else 0
    logger.info("dim_district: %d rows", n)
    return n


def orphan_districts(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return weather districts with no match in dim_district."""
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
    """Rebuild weather_daily from every matching CSV; the newest fetched_at wins per district and day."""
    con.execute(
        "CREATE OR REPLACE TEMP TABLE raw_weather AS "
        "SELECT * FROM read_csv(?, header = true, union_by_name = true, filename = true, "
        # explicit types so an all-empty column is not detected as text
        "types = {'rainfall_mm': 'DOUBLE', 'temperature_2m_mean': 'DOUBLE', "
        "'temperature_2m_max': 'DOUBLE', 'temperature_2m_min': 'DOUBLE', 'date': 'DATE'})",
        [csv_glob],
    )
    cols = {r[0] for r in con.execute("DESCRIBE raw_weather").fetchall()}
    # files without fetched_at sort as oldest
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


# Sri Lanka epi weeks run Saturday to Friday. DuckDB dayofweek() is Sunday=0 .. Saturday=6,
# so days since the last Saturday = (dayofweek + 1) % 7.
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
    """Load parsed NDCU weeks; one row per year, ISO week and RDHS, newest parse wins.

    The table is always created, even when empty, so dbt sources exist.
    """
    con.execute(NDCU_DDL)
    if not list(Path(csv_glob).parent.glob(Path(csv_glob).name)):
        logger.info("ndcu_weekly_cases: 0 rows (no parsed NDCU files yet)")
        return 0
    con.execute(
        "CREATE OR REPLACE TEMP TABLE raw_ndcu AS SELECT * FROM read_csv(?, header = true, union_by_name = true)",
        [csv_glob],
    )
    cols = {r[0] for r in con.execute("DESCRIBE raw_ndcu").fetchall()}
    total_check = "total_check" if "total_check" in cols else "CAST(NULL AS VARCHAR)"  # older parses
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


WER_DDL = """
CREATE OR REPLACE TABLE wer_weekly_cases (
    year INTEGER, week INTEGER, week_start DATE, week_end DATE, rdhs VARCHAR, cases INTEGER,
    week_days INTEGER, week_start_day VARCHAR, source VARCHAR, loaded_at VARCHAR
)
"""


def load_wer_history(con: duckdb.DuckDBPyConnection, csv_glob: str = WER_GLOB) -> int:
    """Load WER history (empty table if not downloaded); the newest load wins per week and region."""
    con.execute(WER_DDL)
    if not list(Path(csv_glob).parent.glob(Path(csv_glob).name)):
        logger.info("wer_weekly_cases: 0 rows (run python -m src.extract.wer_history)")
        return 0
    con.execute(
        """
        INSERT INTO wer_weekly_cases
        SELECT year, week, week_start, week_end, rdhs, cases, week_days, week_start_day, source, loaded_at
        FROM read_csv(?, header = true, union_by_name = true)
        QUALIFY ROW_NUMBER() OVER (PARTITION BY week_start, rdhs ORDER BY loaded_at DESC) = 1
        """,
        [csv_glob],
    )
    row = con.execute("SELECT COUNT(*) FROM wer_weekly_cases").fetchone()
    n = row[0] if row else 0
    logger.info("wer_weekly_cases: %d rows", n)
    return n


def main() -> None:
    setup_logging()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        load_reference(con)
        load_weather(con, WEATHER_GLOB)
        build_weekly(con)
        load_ndcu(con)
        load_wer_history(con)
        load_population(con)
        load_ndcu_moh(con)
        # create empty ML tables so dbt sources and dashboard queries always resolve
        con.execute(FORECAST_DDL)
        con.execute(DRIFT_DDL)
        orphans = orphan_districts(con)
        if orphans:
            raise SystemExit(f"Weather districts missing from {DISTRICTS_CSV}: {orphans}")
        print(con.sql("SELECT * FROM weather_weekly WHERE district = 'colombo' LIMIT 6").df().to_string())


if __name__ == "__main__":
    main()
