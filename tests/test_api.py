"""API tests on a tiny hand-made warehouse file (TestClient = real HTTP calls, no server needed)."""
from __future__ import annotations

import duckdb
import pandas as pd
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.api import main  # noqa: E402
from src.reports import dashboard_data as dd  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA gold")
    con.execute("""CREATE TABLE gold.mart_ndcu_monitoring AS SELECT * FROM (VALUES
        ('colombo','Western','2026-W36',DATE '2026-08-31',222,NULL,false,50.0,40.0,30.0),
        ('colombo','Western','2026-W37',DATE '2026-09-07',207,-15,false,60.0,45.0,35.0),
        ('kandy','Central','2026-W37',DATE '2026-09-07',174,16,true,20.0,NULL,5.0)
      ) t(district, province, iso_week_key, week_start, cases, cases_change_vs_prev_week, any_restated,
          rainfall_mm_total, rain_lag2_mm, rain_lag4_mm)""")
    con.execute("ALTER TABLE gold.mart_ndcu_monitoring ADD COLUMN population BIGINT")
    con.execute("ALTER TABLE gold.mart_ndcu_monitoring ADD COLUMN cases_per_100k DOUBLE")
    con.execute("UPDATE gold.mart_ndcu_monitoring SET population = CASE district WHEN 'colombo' THEN 2000000 "
              "ELSE 1000000 END")
    con.execute("UPDATE gold.mart_ndcu_monitoring SET cases_per_100k = round(cases * 100000.0 / population, 1)")
    con.execute("""CREATE TABLE gold.dim_district AS SELECT * FROM (VALUES
        ('-1','unknown','Unknown','Unknown',NULL,NULL),
        ('a','colombo','Colombo','Western',6.87,80.02), ('b','kandy','Kandy','Central',7.27,80.71)
      ) t(district_sk, district, district_name, province, latitude, longitude)""")
    con.execute("CREATE TABLE gold.fact_dengue_ndcu_weekly AS SELECT DATE '2026-09-13' AS week_end")
    con.execute("CREATE TABLE main.weather_daily AS SELECT DATE '2026-09-23' AS date")
    con.close()
    monkeypatch.setattr(dd, "DB_PATH", db)
    monkeypatch.setattr(dd.connect, "__defaults__", (db,))
    return TestClient(main.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "dengue_data_until": "2026-09-13", "weather_data_until": "2026-09-23"}


def test_hotspots_default_latest_week(client):
    body = client.get("/hotspots").json()
    assert body["week"] == "2026-W37" and body["total_cases"] == 381
    assert [d["district"] for d in body["districts"]] == ["colombo", "kandy"]
    assert body["districts"][1]["rain_2wk_earlier_mm"] is None        # NaN -> null in JSON
    assert "not official health advice" in body["disclaimer"]


def test_hotspots_validation_and_404(client):
    assert client.get("/hotspots?week=2026-37").status_code == 422      # bad format
    assert client.get("/hotspots?top=0").status_code == 422             # out of range
    assert client.get("/hotspots?week=2020-W01").status_code == 404     # no data


def test_districts_and_trend(client):
    assert [d["district"] for d in client.get("/districts").json()] == ["colombo", "kandy"]
    trend = client.get("/districts/Colombo/trend").json()
    assert [p["week"] for p in trend] == ["2026-W36", "2026-W37"]
    assert client.get("/districts/atlantis/trend").status_code == 404


def test_forecast_404_before_scoring(client):
    assert client.get("/forecast").status_code == 404


def test_forecast_endpoint(client, tmp_path):
    from src.ml import predict
    r = pd.DataFrame({"rdhs": ["colombo"], "district": ["colombo"],
                      "week_start": pd.to_datetime(["2026-05-11"]), "week_end": pd.to_datetime(["2026-05-17"]),
                      "cases": [308], "target_threshold_h2": [400.0], "target_threshold_h4": [float("nan")]})
    fc = predict.to_long(r, pd.DataFrame({"pred_cases_h2": [410.0], "pred_cases_h4": [420.0]}), "7",
                         pd.Timestamp("2026-09-30").to_pydatetime())
    with duckdb.connect(str(tmp_path / "w.duckdb")) as con:
        predict.write(con, fc)
    body = client.get("/forecast?top=1").json()
    assert body["model_version"] == "7" and body["based_on_week_ending"] == "2026-05-17"
    region = body["regions"][0]
    assert region["risk_2w"] == "high" and region["risk_4w"] == "unknown" and region["outbreak_level_4w"] is None


def test_model_health_empty(client):
    body = client.get("/model/health").json()
    assert body == {"performance": [], "drift": None}


def test_hotspots_include_rate(client):
    body = client.get("/hotspots").json()
    assert body["districts"][0]["cases_per_100k"] == 10.4   # 207 per 2,000,000 = 10.35 -> rounded


def test_national_trend(client):
    r = client.get("/national/trend")
    assert r.status_code == 200
    assert r.json() == [{"week": "2026-W36", "week_start": "2026-08-31", "cases": 222},
                        {"week": "2026-W37", "week_start": "2026-09-07", "cases": 381}]


def test_forecast_vs_actual_empty_before_scoring(client):
    r = client.get("/model/forecast-vs-actual?horizon=4")
    assert r.status_code == 200 and r.json() == []
    assert client.get("/model/forecast-vs-actual?horizon=3").status_code == 422


def test_geo_districts(client):
    r = client.get("/geo/districts")
    assert r.status_code == 200
    geo = r.json()
    assert geo["type"] == "FeatureCollection" and len(geo["features"]) == 25
    assert all("district" in f["properties"] for f in geo["features"])
