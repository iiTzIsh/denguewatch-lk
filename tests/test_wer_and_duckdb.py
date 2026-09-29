"""DuckDB load: idempotent + Saturday->Friday epi weeks."""
from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd

from src.load.duckdb_load import build_weekly, load_weather
from src.load.run_sql import split_queries


def _write_csv(folder, district, dates, rain):
    pd.DataFrame({
        "district": district,
        "date": dates,
        "rainfall_mm": rain,
        "temperature_2m_mean": 28.0,
        "temperature_2m_max": 31.0,
        "temperature_2m_min": 25.0,
    }).to_csv(folder / f"{district}_daily_x.csv", index=False)


def test_load_weather_is_idempotent(tmp_path):
    _write_csv(tmp_path, "colombo", ["2024-05-03", "2024-05-04", "2024-05-05"], [1.0, 2.0, 3.0])
    con = duckdb.connect()
    load_weather(con, str(tmp_path / "*_daily_*.csv"))
    assert load_weather(con, str(tmp_path / "*_daily_*.csv")) == 3  # still 3, not 6


def test_weekly_uses_saturday_to_friday(tmp_path):
    # Fri 2024-05-03 | Sat 05-04 ... Fri 05-10 | Sat 05-11
    dates = pd.date_range("2024-05-03", "2024-05-11").strftime("%Y-%m-%d").tolist()
    _write_csv(tmp_path, "colombo", dates, [1.0] * len(dates))
    con = duckdb.connect()
    load_weather(con, str(tmp_path / "*_daily_*.csv"))
    build_weekly(con)
    weeks = con.sql("SELECT epi_week_start, days_in_week FROM weather_weekly ORDER BY 1").fetchall()
    assert weeks == [
        (date(2024, 4, 27), 1),   # Friday 05-03 belongs to the week starting Sat 04-27
        (date(2024, 5, 4), 7),    # full Sat->Fri week
        (date(2024, 5, 11), 1),
    ]


def test_split_queries_skips_comments():
    sql = "-- title\nSELECT 1;\n-- only a comment;\nSELECT 2;"
    assert split_queries(sql) == ["-- title\nSELECT 1", "SELECT 2"]


# ---------- Week 2 Day 1 ----------
def test_districts_reference_is_complete():
    """Real reference file: 25 unique districts, 9 provinces, coordinates inside Sri Lanka's bounding box."""
    from src.extract.weather import DISTRICTS

    ref = pd.read_csv("reference/districts.csv")
    assert len(ref) == 25 and ref["district"].is_unique
    assert ref["province"].nunique() == 9
    assert ref["latitude"].between(5.9, 9.9).all() and ref["longitude"].between(79.5, 81.95).all()
    assert set(DISTRICTS) == set(ref["district"])


def test_orphan_districts_detected(tmp_path):
    from src.load.duckdb_load import load_reference, orphan_districts

    _write_csv(tmp_path, "colombo", ["2024-05-04"], [1.0])
    _write_csv(tmp_path, "atlantis", ["2024-05-04"], [1.0])
    con = duckdb.connect()
    load_reference(con)
    load_weather(con, str(tmp_path / "*_daily_*.csv"))
    assert orphan_districts(con) == ["atlantis"]


def test_overlapping_pulls_newest_wins(tmp_path):
    old = pd.DataFrame({"district": "colombo", "date": ["2026-09-01", "2026-09-02"], "rainfall_mm": [1.0, 2.0],
                        "temperature_2m_mean": 28.0, "temperature_2m_max": 31.0, "temperature_2m_min": 25.0,
                        "fetched_at": "2026-09-05T00:00:00Z"})
    new = old.assign(rainfall_mm=[1.5, 2.5], fetched_at="2026-09-10T00:00:00Z")
    old.to_csv(tmp_path / "colombo_daily_a.csv", index=False)
    new.to_csv(tmp_path / "colombo_daily_b.csv", index=False)
    con = duckdb.connect()
    assert load_weather(con, str(tmp_path / "*_daily_*.csv")) == 2     # not 4
    assert con.sql("SELECT sum(rainfall_mm) FROM weather_daily").fetchone()[0] == 4.0  # newest values
