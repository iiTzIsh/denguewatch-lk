"""
DengueWatch LK - read-only REST API over the gold layer.

Run:   uvicorn src.api.main:app --reload            ->  http://localhost:8000/docs  (interactive docs)
Endpoints:
  GET /health                          warehouse reachable + data freshness
  GET /weeks                           ISO weeks with NDCU data (newest first)
  GET /hotspots?week=2026-W37&top=5    districts ranked by cases for a week (default: latest)
  GET /districts                       the 25 districts
  GET /districts/{district}/trend      weekly cases (+ rainfall) for one district
  GET /forecast?top=5                  2- and 4-week case forecasts per region with risk level (@champion model)
  GET /moh/hotspots?week=2026-W37&top=10   high-risk MOH areas NDCU listed that week (page 2 of the PDF)
  GET /model/health                    forecast vs actual (vs naive) per model + latest data-drift check
  GET /national/trend                  national weekly cases (all districts)
  GET /districts/{district}/rain?since=2026-03-01   weekly rainfall, continuous (no gaps)
  GET /model/forecast-vs-actual?horizon=4   national actual vs forecast vs naive per target week
  GET /geo/districts                   district boundaries (GeoJSON, geoBoundaries / OSM, ODbL) for maps
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime
from typing import Annotated

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.config import REFERENCE_DIR
from src.reports import dashboard_data as dd

DISCLAIMER = "Portfolio project - not official health advice. Source: NDCU weekly updates, Open-Meteo (CC BY 4.0)."

app = FastAPI(
    title="DengueWatch LK API",
    version="0.1.0",
    description=f"Weekly dengue cases and weather per Sri Lankan district. {DISCLAIMER}",
)


# ---------- response models (shape of the JSON = the API contract) ----------
class Health(BaseModel):
    status: str
    dengue_data_until: date | None
    weather_data_until: date | None


class Hotspot(BaseModel):
    rank: int
    district: str
    province: str
    cases: int
    cases_per_100k: float | None          # Census 2024 population; null until loaded
    change_vs_prev_week: int | None
    rain_2wk_earlier_mm: float | None


class HotspotsResponse(BaseModel):
    week: str
    week_start: date
    total_cases: int
    districts: list[Hotspot]
    disclaimer: str = DISCLAIMER


class District(BaseModel):
    district: str
    district_name: str
    province: str
    latitude: float
    longitude: float


class TrendPoint(BaseModel):
    week: str
    week_start: date
    cases: int
    rain_mm: float | None


class ForecastRegion(BaseModel):
    rdhs: str
    district: str
    cases_now: int
    pred_cases_2w: float
    outbreak_level_2w: float | None
    risk_2w: str
    pred_cases_4w: float
    outbreak_level_4w: float | None
    risk_4w: str


class ForecastResponse(BaseModel):
    model_version: str
    based_on_week_ending: date
    regions: list[ForecastRegion]
    risk_levels: str = ("high: forecast >= outbreak level | watch: >= 80% of it | normal | "
                        "unknown: not enough history. Outbreak level = usual level for that region and time of year.")
    disclaimer: str = DISCLAIMER


class MOHHotspot(BaseModel):
    rank: int
    moh_area: str
    district: str
    cases: int
    change_vs_prev_week: int
    split_from: str | None          # parent MOH area (lk_dengue mapping, unverified)


class MOHHotspotsResponse(BaseModel):
    week: str
    listed: int
    moh_areas: list[MOHHotspot]
    note: str = "NDCU lists only high-risk MOH areas; an area not listed was not high-risk, not zero cases."
    disclaimer: str = DISCLAIMER


class ModelPerformance(BaseModel):
    model_name: str
    horizon_weeks: int
    forecasts: int
    first_target_week: date
    last_target_week: date
    mae: float
    naive_mae: float
    skill_vs_naive: float | None
    outbreak_weeks: int
    alerts: int
    correct_alerts: int


class DriftStatus(BaseModel):
    base_week_end: date
    drift_detected: bool
    n_drifted: int
    n_features: int
    drift_share: float
    drifted_features: list[str]
    checked_at: datetime


class NationalPoint(BaseModel):
    week: str
    week_start: date
    cases: int


class RainPoint(BaseModel):
    week_start: date
    rain_mm: float | None


class AccuracyPoint(BaseModel):
    target_week_end: date
    actual: int
    forecast: float
    naive: float
    regions: int


class ModelHealth(BaseModel):
    performance: list[ModelPerformance]
    drift: DriftStatus | None


# ---------- one read-only connection per request ----------
def get_con() -> Iterator[duckdb.DuckDBPyConnection]:
    try:
        con = dd.connect()
    except duckdb.Error as exc:   # file missing, or the pipeline is writing right now
        raise HTTPException(503, f"Warehouse not available: {exc}") from exc
    try:
        yield con
    finally:
        con.close()


Con = Annotated[duckdb.DuckDBPyConnection, Depends(get_con)]


def _none_if_nan(v: object) -> float | None:
    return None if v is None or v != v else float(v)  # type: ignore[arg-type]


# ---------- endpoints ----------
@app.get("/health", response_model=Health)
def health(con: Con) -> Health:
    f = dd.freshness(con)
    return Health(status="ok", dengue_data_until=f["ndcu_until"], weather_data_until=f["weather_until"])


@app.get("/weeks", response_model=list[str])
def weeks(con: Con) -> list[str]:
    return dd.available_weeks(con)


@app.get("/hotspots", response_model=HotspotsResponse)
def hotspots(
    con: Con,
    week: Annotated[str | None, Query(pattern=r"^\d{4}-W\d{2}$", examples=["2026-W37"])] = None,
    top: Annotated[int, Query(ge=1, le=25)] = 5,
) -> HotspotsResponse:
    available = dd.available_weeks(con)
    if not available:
        raise HTTPException(404, "No NDCU data loaded yet")
    week = week or available[0]
    if week not in available:
        raise HTTPException(404, f"No data for week {week}. See /weeks")
    snap = dd.week_snapshot(con, week)
    rows = [
        Hotspot(
            rank=i,
            district=str(r["district"]),
            province=str(r["province"]),
            cases=int(r["cases"]),
            cases_per_100k=_none_if_nan(r["cases_per_100k"]),
            change_vs_prev_week=None if _none_if_nan(r["change_vs_prev_week"]) is None
            else int(r["change_vs_prev_week"]),
            rain_2wk_earlier_mm=_none_if_nan(r["rain_lag2_mm"]),
        )
        for i, r in enumerate(snap.head(top).to_dict("records"), 1)
    ]
    return HotspotsResponse(week=week, week_start=snap["week_start"].iloc[0].date(),
                            total_cases=int(snap["cases"].sum()), districts=rows)


@app.get("/districts", response_model=list[District])
def districts(con: Con) -> list[District]:
    df = con.execute(
        "SELECT district, district_name, province, latitude, longitude FROM gold.dim_district "
        "WHERE district <> 'unknown' ORDER BY district"
    ).df()
    return [District(**{str(k): v for k, v in r.items()}) for r in df.to_dict("records")]


@app.get("/districts/{district}/trend", response_model=list[TrendPoint])
def district_trend(con: Con, district: str) -> list[TrendPoint]:
    df = dd.district_trend(con, district.lower())
    if df.empty:
        raise HTTPException(404, f"Unknown district or no data: {district}. See /districts")
    return [
        TrendPoint(week=str(r["iso_week_key"]), week_start=r["week_start"].date(),
                   cases=int(r["cases"]), rain_mm=_none_if_nan(r["rain_mm"]))
        for r in df.to_dict("records")
    ]


@app.get("/forecast", response_model=ForecastResponse)
def forecast(con: Con, top: Annotated[int, Query(ge=1, le=26)] = 26) -> ForecastResponse:
    df = dd.latest_forecast(con)
    if df.empty:
        raise HTTPException(404, "No forecasts yet - run: python -m src.ml.predict")
    regions = [
        ForecastRegion(
            rdhs=str(r["rdhs"]), district=str(r["district"]), cases_now=int(r["cases_now"]),
            pred_cases_2w=float(r["pred_2w"]), outbreak_level_2w=_none_if_nan(r["level_2w"]), risk_2w=str(r["risk_2w"]),
            pred_cases_4w=float(r["pred_4w"]), outbreak_level_4w=_none_if_nan(r["level_4w"]), risk_4w=str(r["risk_4w"]),
        )
        for r in df.head(top).to_dict("records")
    ]
    return ForecastResponse(model_version=str(df["model_version"].iloc[0]),
                            based_on_week_ending=df["base_week_end"].iloc[0], regions=regions)


@app.get("/model/health", response_model=ModelHealth)
def model_health(con: Con) -> ModelHealth:
    perf = dd.model_performance(con)
    d = dd.latest_drift(con)
    drift = None
    if d:
        drift = DriftStatus(base_week_end=d["base_week_end"], drift_detected=bool(d["drift_detected"]),
                            n_drifted=int(d["n_drifted"]), n_features=int(d["n_features"]),
                            drift_share=float(d["drift_share"]), drifted_features=json.loads(d["drifted_features"]),
                            checked_at=d["checked_at"])
    return ModelHealth(
        performance=[ModelPerformance(**{**r, "skill_vs_naive": _none_if_nan(r["skill_vs_naive"])})
                     for r in ({str(k): v for k, v in rec.items()} for rec in perf.to_dict("records"))],
        drift=drift,
    )


@app.get("/moh/hotspots", response_model=MOHHotspotsResponse)
def moh_hotspots(
    con: Con,
    week: Annotated[str | None, Query(pattern=r"^\d{4}-W\d{2}$", examples=["2026-W37"])] = None,
    top: Annotated[int, Query(ge=1, le=200)] = 10,
) -> MOHHotspotsResponse:
    available = dd.available_weeks(con)
    if not available:
        raise HTTPException(404, "No NDCU data loaded yet")
    week = week or available[0]
    df = dd.moh_hotspots(con, week)
    if df.empty:
        raise HTTPException(404, f"No MOH-level data for week {week}")
    rows = [
        MOHHotspot(rank=i, moh_area=str(r["moh_area"]), district=str(r["district"]), cases=int(r["cases_this_week"]),
                   change_vs_prev_week=int(r["change_vs_prev_week"]),
                   split_from=None if r["parent_moh_area"] is None or r["parent_moh_area"] != r["parent_moh_area"]
                   else str(r["parent_moh_area"]))
        for i, r in enumerate(df.head(top).to_dict("records"), 1)
    ]
    return MOHHotspotsResponse(week=week, listed=len(df), moh_areas=rows)


@app.get("/national/trend", response_model=list[NationalPoint])
def national_trend(con: Con) -> list[NationalPoint]:
    df = dd.national_totals(con)
    return [NationalPoint(week=str(r["iso_week_key"]), week_start=r["week_start"].date(), cases=int(r["cases"]))
            for r in df.to_dict("records")]


@app.get("/districts/{district}/rain", response_model=list[RainPoint])
def district_rain(con: Con, district: str, since: date) -> list[RainPoint]:
    df = dd.district_rain(con, district.lower(), since.isoformat())
    if df.empty:
        raise HTTPException(404, f"Unknown district or no weather since {since}: {district}")
    return [RainPoint(week_start=r["week_start"].date(), rain_mm=_none_if_nan(r["rain_mm"]))
            for r in df.to_dict("records")]


@app.get("/model/forecast-vs-actual", response_model=list[AccuracyPoint])
def forecast_vs_actual(con: Con, horizon: Annotated[int, Query(ge=2, le=4, multiple_of=2)] = 4) -> list[AccuracyPoint]:
    df = dd.forecast_vs_actual(con, horizon=horizon)
    return [AccuracyPoint(target_week_end=r["target_week_end"], actual=int(r["actual"]), forecast=float(r["forecast"]),
                          naive=float(r["naive"]), regions=int(r["regions"]))
            for r in df.to_dict("records")]


@app.get("/geo/districts", response_class=FileResponse)
def geo_districts() -> FileResponse:
    """District boundaries for maps: geoBoundaries gbOpen LKA ADM2 (OpenStreetMap, ODbL 1.0), `district` = slug."""
    return FileResponse(REFERENCE_DIR / "geo" / "lka_districts.geojson", media_type="application/geo+json",
                        headers={"Cache-Control": "public, max-age=86400"})
