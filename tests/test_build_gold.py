"""End-to-end: silver -> gold star schema -> all SQL data tests pass."""
from __future__ import annotations

import duckdb
import pandas as pd

from src.load.duckdb_load import build_weekly, load_reference, load_weather
from src.transform.build_gold import run_models, run_tests


def _silver(tmp_path) -> duckdb.DuckDBPyConnection:
    dates = pd.date_range("2024-01-01", "2024-03-31").strftime("%Y-%m-%d")
    for city in ["colombo", "kandy"]:
        pd.DataFrame({
            "city": city, "date": dates, "rainfall_mm": 3.3,
            "temperature_2m_mean": 28.0, "temperature_2m_max": 31.0, "temperature_2m_min": 25.0,
        }).to_csv(tmp_path / f"{city}_daily_x.csv", index=False)
    con = duckdb.connect()
    load_reference(con)
    load_weather(con, str(tmp_path / "*_daily_*.csv"))
    build_weekly(con)
    return con


def test_gold_builds_and_all_tests_pass(tmp_path):
    con = _silver(tmp_path)
    run_models(con)
    results = run_tests(con)
    assert results and all(n == 0 for n in results.values()), results


def test_epi_week_known_dates(tmp_path):
    con = _silver(tmp_path)
    run_models(con)
    got = con.execute(
        "SELECT epi_week_key, CAST(week_start AS VARCHAR), season FROM gold.dim_epi_week "
        "WHERE epi_week_key IN ('2024-W01', '2024-W18') ORDER BY 1"
    ).fetchall()
    assert got == [("2024-W01", "2023-12-30", "NE monsoon"), ("2024-W18", "2024-04-27", "First inter-monsoon")]


def test_unknown_city_is_caught(tmp_path):
    con = _silver(tmp_path)
    con.execute("UPDATE weather_weekly SET city = 'atlantis' WHERE city = 'kandy'")
    run_models(con)
    assert run_tests(con)["t06_fact_no_unknown_city"] > 0
