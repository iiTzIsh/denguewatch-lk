"""
DengueWatch LK - monitoring dashboard (NDCU weekly cases + weather).

Run from the project root:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import altair as alt
import branca.colormap as cm
import duckdb
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so "src" imports work when Streamlit runs this file

from src.config import DB_PATH, REFERENCE_DIR  # noqa: E402
from src.reports import dashboard_data as dd  # noqa: E402

# ---- design tokens (dataviz reference palette) ----
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # sequential, light->dark
SERIES_CASES = "#2a78d6"   # categorical slot 1 (blue)
SERIES_RAIN = "#1baf7a"    # categorical slot 3 (aqua) - separate chart, never a second axis
NO_DATA = "#e0dfdb"
DATE_AXIS = alt.Axis(format="%d %b", labelAngle=0, tickCount="week", labelOverlap="greedy")  # e.g. "07 Sep"

st.set_page_config(page_title="DengueWatch LK", page_icon="🦟", layout="wide")


# ---------- data (cached) ----------
@st.cache_data(ttl=600)
def load(week: str | None = None) -> dict:
    with dd.connect() as con:
        weeks = dd.available_weeks(con)
        chosen = week or (weeks[0] if weeks else None)
        return {
            "weeks": weeks,
            "week": chosen,
            "snapshot": dd.week_snapshot(con, chosen) if chosen else pd.DataFrame(),
            "national": dd.national_totals(con),
            "fresh": dd.freshness(con),
        }


@st.cache_data(ttl=600)
def load_district(district: str, since: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    with dd.connect() as con:
        return dd.district_trend(con, district), dd.district_rain(con, district, since)


@st.cache_data(ttl=600)
def load_forecast() -> pd.DataFrame:
    with dd.connect() as con:
        return dd.latest_forecast(con)


@st.cache_data
def load_geojson() -> dict:
    return json.loads((REFERENCE_DIR / "geo" / "lka_districts.geojson").read_text(encoding="utf-8"))


def fmt(v: object, suffix: str = "") -> str:
    return "-" if v is None or pd.isna(v) else f"{v:,.0f}{suffix}"


# ---------- header ----------
st.title("🦟 DengueWatch LK")
st.warning("**Portfolio project, not official health advice.** "
           "Official information: [National Dengue Control Unit](https://www.dengue.health.gov.lk/).")

if not DB_PATH.exists():
    st.error(f"No warehouse found at `{DB_PATH}`. Run `python -m src.pipeline` first.")
    st.stop()

try:
    base = load()
except duckdb.CatalogException:
    st.error("The warehouse has no gold tables yet. Run `python -m src.pipeline` first, then refresh this page.")
    st.stop()
if not base["weeks"]:
    st.info("No NDCU weekly data yet. Run `python -m src.extract.ndcu` and `python -m src.pipeline`.")
    st.stop()

# ---------- filters (one row, above the charts) ----------
f1, f2 = st.columns([1, 3])
week = f1.selectbox("ISO week (Mon-Sun)", base["weeks"], index=0)
data = load(week)
snap: pd.DataFrame = data["snapshot"]
national: pd.DataFrame = data["national"]
fresh = data["fresh"]
f2.caption(
    f"Dengue data up to **{fresh['ndcu_until']}** (NDCU weekly updates) · "
    f"weather up to **{fresh['weather_until']}** (Open-Meteo, ERA5). "
    "NDCU did not publish every week, so some weeks are missing."
)

# ---------- KPI tiles ----------
this_total = int(snap["cases"].sum())
nat = national.set_index("iso_week_key")
prev_idx = list(nat.index).index(week) - 1
prev_week_total = None
if prev_idx >= 0:
    prev_key = nat.index[prev_idx]
    if (pd.Timestamp(nat.loc[week, "week_start"]) - pd.Timestamp(nat.loc[prev_key, "week_start"])).days == 7:
        prev_week_total = int(nat.loc[prev_key, "cases"])
rising = int((snap["change_vs_prev_week"] > 0).sum())
top = snap.iloc[0]

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Cases this week (all districts)", f"{this_total:,}",
    delta=None if prev_week_total is None else f"{this_total - prev_week_total:+,} vs last week",
    delta_color="inverse",   # more cases = bad
)
k2.metric("Districts rising vs last week", f"{rising} / 25")
k3.metric("Most cases", f"{top['district'].replace('_', ' ').title()} ({int(top['cases']):,})")
k4.metric("Regions with revised numbers", "yes" if snap["any_restated"].any() else "no",
          help="NDCU revises last week's count in the next report (delayed reports / duplicates).")

# ---------- map + top table ----------
left, right = st.columns([3, 2])
with left:
    st.subheader(f"Cases by district - {week}")
    geo = copy.deepcopy(load_geojson())
    by_d = snap.set_index("district")
    vmax = max(float(snap["cases"].max()), 1.0)
    colormap = cm.StepColormap(
        BLUE_RAMP, vmin=0, vmax=vmax,
        index=[vmax * i / len(BLUE_RAMP) for i in range(len(BLUE_RAMP) + 1)],
        caption="Cases this week",
    )
    for feat in geo["features"]:
        d = feat["properties"]["district"]
        row = by_d.loc[d] if d in by_d.index else None
        p = feat["properties"]
        p["cases"] = None if row is None else int(row["cases"])
        p["cases_txt"] = fmt(p["cases"])
        p["change_txt"] = "-" if row is None else fmt(row["change_vs_prev_week"])
        p["rain_txt"] = "-" if row is None else fmt(row["rain_lag2_mm"], " mm")

    m = folium.Map(location=[7.85, 80.7], zoom_start=7, tiles="OpenStreetMap", control_scale=True)
    folium.GeoJson(
        geo,
        style_function=lambda f: {
            "fillColor": NO_DATA if f["properties"]["cases"] is None else colormap(f["properties"]["cases"]),
            "color": "#ffffff", "weight": 1.5, "fillOpacity": 0.85,
        },
        highlight_function=lambda f: {"weight": 3, "color": "#0b0b0b"},
        tooltip=folium.GeoJsonTooltip(
            fields=["district_name", "cases_txt", "change_txt", "rain_txt"],
            aliases=["District", "Cases this week", "Change vs last week", "Rain 2 weeks earlier"],
        ),
    ).add_to(m)
    colormap.add_to(m)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

with right:
    st.subheader("Top 10 districts")
    top10 = snap.head(10)[["district", "province", "cases", "change_vs_prev_week", "rain_lag2_mm"]].copy()
    top10["district"] = top10["district"].str.replace("_", " ").str.title()
    st.dataframe(
        top10, hide_index=True, width="stretch",
        column_config={
            "district": "District", "province": "Province",
            "cases": st.column_config.NumberColumn("Cases", format="%d"),
            "change_vs_prev_week": st.column_config.NumberColumn("vs last week", format="%+d"),
            "rain_lag2_mm": st.column_config.NumberColumn("Rain 2 wk earlier (mm)", format="%.0f"),
        },
    )
    st.caption("Rain 2 weeks earlier: mosquitoes need standing water and ~1-3 weeks to breed.")

# ---------- national trend ----------
st.subheader("National weekly cases")
nat_chart = (
    alt.Chart(national)
    .mark_line(color=SERIES_CASES, strokeWidth=2, point=alt.OverlayMarkDef(size=64, color=SERIES_CASES))
    .encode(
        x=alt.X("week_start:T", title="Week starting (Monday)", axis=DATE_AXIS),
        y=alt.Y("cases:Q", title="Cases"),
        tooltip=[alt.Tooltip("iso_week_key:N", title="Week"), alt.Tooltip("cases:Q", title="Cases", format=",")],
    )
    .properties(height=260)
)
st.altair_chart(nat_chart, width="stretch")

# ---------- district drill-down: cases and rain as TWO charts (never a dual axis) ----------
st.subheader("District trend")
names = sorted(snap["district"])
district = st.selectbox("District", names, index=names.index(top["district"]),
                        format_func=lambda d: d.replace("_", " ").title())
since = pd.Timestamp(national["week_start"].min()) - pd.Timedelta(weeks=6)
until = pd.Timestamp(national["week_start"].max()) + pd.Timedelta(days=7)
trend, rain = load_district(district, str(since.date()))
# same time window on both charts so they line up when read side by side
x_shared = alt.X("week_start:T", title="Week starting", axis=DATE_AXIS,
                 scale=alt.Scale(domain=[since.isoformat(), until.isoformat()]))
c1, c2 = st.columns(2)
with c1:
    st.altair_chart(
        alt.Chart(trend).mark_line(color=SERIES_CASES, strokeWidth=2,
                                   point=alt.OverlayMarkDef(size=64, color=SERIES_CASES))
        .encode(x=x_shared, y=alt.Y("cases:Q", title="Cases"),
                tooltip=[alt.Tooltip("iso_week_key:N", title="Week"), alt.Tooltip("cases:Q", title="Cases")])
        .properties(title="Dengue cases per week", height=240),
        width="stretch",
    )
with c2:
    if rain.empty or rain["rain_mm"].isna().all():
        st.info(f"No weather data for this period yet (weather available up to {fresh['weather_until']}). "
                "Finish the backfill: `python -m src.extract.weather_backfill`, then `python -m src.pipeline`.")
    else:
        st.altair_chart(
            alt.Chart(rain).mark_bar(color=SERIES_RAIN, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(x=x_shared, y=alt.Y("rain_mm:Q", title="Rainfall (mm)"),
                    tooltip=[alt.Tooltip("week_start:T", title="Week of"),
                             alt.Tooltip("rain_mm:Q", title="Rain (mm)", format=".0f")])
            .properties(title="Weekly rainfall (includes 6 weeks before the first case week)", height=240),
            width="stretch",
        )

# ---------- forecast (batch-scored by src.ml.predict with the MLflow @champion model) ----------
st.subheader("Forecast - next 2 and 4 weeks")
fc = load_forecast()
if fc.empty:
    st.info("No forecasts yet. Start MLflow (`docker compose up -d mlflow`), train once (`python -m src.ml.train`), "
            "then run `python -m src.ml.predict`.")
else:
    RISK_LABEL = {"high": "🔴 High", "watch": "🟠 Watch", "normal": "Normal", "unknown": "Not enough history"}
    view = pd.DataFrame({
        "Region": fc["rdhs"].str.replace("_", " ").str.title(),
        "Cases now": fc["cases_now"],
        "In 2 weeks": fc["pred_2w"].round(0),
        "Risk (2 wk)": fc["risk_2w"].map(RISK_LABEL),
        "In 4 weeks": fc["pred_4w"].round(0),
        "Outbreak level (4 wk)": fc["level_4w"].round(0),
        "% of outbreak level (4 wk)": (fc["pred_4w"] / fc["level_4w"]).clip(upper=1.5),
        "Risk (4 wk)": fc["risk_4w"].map(RISK_LABEL),
    })
    st.dataframe(
        view, hide_index=True, width="stretch",
        column_config={
            "Cases now": st.column_config.NumberColumn(format="%d"),
            "In 2 weeks": st.column_config.NumberColumn(format="%d"),
            "In 4 weeks": st.column_config.NumberColumn(format="%d"),
            "Outbreak level (4 wk)": st.column_config.NumberColumn(format="%d"),
            "% of outbreak level (4 wk)": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1.5),
        },
    )
    st.caption(
        f"Model v{fc['model_version'].iloc[0]} (LightGBM, MLflow @champion), based on WER data up to "
        f"**{pd.Timestamp(fc['base_week_end'].iloc[0]):%d %b %Y}**. Per region (26 health regions, WER). "
        "Outbreak level = the usual level for that region and time of year (last 5 years). "
        "**Watch** = forecast at 80% of it or more. Backtest 2014-2025: 12% lower error than 'same as this week' "
        "at 4 weeks; catches ~58-70% of outbreak weeks. Forecasts are uncertain - not official health advice."
    )

# ---------- full table view (accessibility + exact numbers) ----------
with st.expander(f"All 25 districts - {week} (table)"):
    st.dataframe(snap, hide_index=True, width="stretch")

st.caption(
    "Sources: dengue cases - National Dengue Control Unit weekly updates (parsed + validated against printed totals) · "
    "weather - Open-Meteo (ERA5 reanalysis, CC BY 4.0) · boundaries - geoBoundaries / OpenStreetMap (ODbL). "
    "Code: github.com/iiTzIsh/denguewatch-lk"
)
