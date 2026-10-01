"""Dashboard queries against a tiny hand-made warehouse."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from src.reports import dashboard_data as dd


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA gold")
    c.execute("""
        CREATE TABLE gold.mart_ndcu_monitoring AS SELECT * FROM (VALUES
          ('colombo','Western','2026-W36',DATE '2026-08-31',222,NULL,false,50.0,40.0,30.0),
          ('colombo','Western','2026-W37',DATE '2026-09-07',207,-15,false,60.0,45.0,35.0),
          ('kandy','Central','2026-W37',DATE '2026-09-07',174,16,true,20.0,10.0,5.0)
        ) t(district, province, iso_week_key, week_start, cases, cases_change_vs_prev_week, any_restated,
            rainfall_mm_total, rain_lag2_mm, rain_lag4_mm)""")
    c.execute("ALTER TABLE gold.mart_ndcu_monitoring ADD COLUMN population BIGINT")
    c.execute("ALTER TABLE gold.mart_ndcu_monitoring ADD COLUMN cases_per_100k DOUBLE")
    c.execute("UPDATE gold.mart_ndcu_monitoring SET population = CASE district WHEN 'colombo' THEN 2000000 "
              "ELSE 1000000 END")
    c.execute("UPDATE gold.mart_ndcu_monitoring SET cases_per_100k = round(cases * 100000.0 / population, 1)")
    return c


def test_available_weeks_newest_first(con):
    assert dd.available_weeks(con) == ["2026-W37", "2026-W36"]


def test_week_snapshot_sorted_by_cases(con):
    snap = dd.week_snapshot(con, "2026-W37")
    assert snap["district"].tolist() == ["colombo", "kandy"]
    assert snap["change_vs_prev_week"].tolist() == [-15, 16]


def test_national_totals(con):
    nat = dd.national_totals(con)
    assert nat["cases"].tolist() == [222, 381]
    assert nat["week_start"].iloc[0].date() == date(2026, 8, 31)


def test_week_snapshot_has_rate(con):
    snap = dd.week_snapshot(con, "2026-W37").set_index("district")
    assert snap.loc["colombo", "cases_per_100k"] == 10.4          # 207 per 2,000,000 = 10.35 -> rounded
    assert snap.loc["kandy", "population"] == 1000000
