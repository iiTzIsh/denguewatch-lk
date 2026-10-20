"""Static export for the hosted dashboard, on the tiny warehouse from test_api.py."""

from __future__ import annotations

import json

import duckdb
import pytest

pytest.importorskip("fastapi")

from src import queries as q  # noqa: E402
from src.export_static import district_slug, export  # noqa: E402
from tests.test_api import client  # noqa: E402, F401  (fixture)


def test_district_slug_matches_web_rule():
    assert district_slug("nuwara eliya") == "nuwara-eliya"
    assert district_slug("Colombo") == "colombo"


def test_export_writes_endpoint_responses(client, tmp_path):  # noqa: F811
    with duckdb.connect(str(q.DB_PATH)) as con:  # the rain chart reads the weekly weather fact
        con.execute(
            "CREATE TABLE gold.fact_weather_iso_weekly AS SELECT 'a' AS district_sk, "
            "DATE '2026-08-03' AS week_start, 12.5 AS rainfall_mm_total"
        )
    out = tmp_path / "data"
    (out / "stale.json").parent.mkdir(parents=True)
    (out / "stale.json").write_text("{}")

    summary = export(out, client)

    assert summary["weeks"] == 2 and summary["districts"] == 2
    assert not (out / "stale.json").exists()  # old files are cleared
    assert json.loads((out / "weeks.json").read_text()) == client.get("/weeks").json()
    hot = json.loads((out / "hotspots" / "2026-W37.json").read_text())
    assert hot == client.get("/hotspots?top=25&week=2026-W37").json()
    assert (out / "districts" / "kandy" / "trend.json").exists()
    rain = json.loads((out / "districts" / "colombo" / "rain.json").read_text())
    assert rain == [{"week_start": "2026-08-03", "rain_mm": 12.5}]  # 6 weeks before the first case week
    assert (out / "districts.geojson").stat().st_size > 1000
