"""
Tests for src/extract/weather.py
Run: pytest -v           (fast tests only)
     pytest -m network   (the real-API test)
"""

from __future__ import annotations

import argparse

import pandas as pd
import pytest
import requests

from src.extract import weather
from tests.conftest import FakeResponse, FakeSession


# ---------- parsing ----------
def test_to_dataframe_parses_payload(weather_df):
    assert len(weather_df) == 3
    assert "rainfall_mm" in weather_df.columns
    assert weather_df["rainfall_mm"].sum() == pytest.approx(52.7)


def test_to_dataframe_raises_on_missing_daily():
    with pytest.raises(weather.WeatherAPIError):
        weather.to_dataframe({"latitude": 6.93})


def test_build_params_dates_and_vars():
    p = weather.build_params(7.29, 80.63, "2024-01-01", "2024-01-31")
    assert (p["start_date"], p["end_date"]) == ("2024-01-01", "2024-01-31")
    assert p["daily"].startswith("precipitation_sum")


# ---------- retries ----------
def test_fetch_retries_then_succeeds(no_sleep, sample_payload):
    session = FakeSession(
        [
            requests.ConnectionError("network down"),
            FakeResponse(503),
            FakeResponse(200, sample_payload),
        ]
    )
    payload = weather.fetch_daily_weather(6.93, 79.86, "2024-05-01", "2024-05-03", session=session)
    assert session.calls == 3
    assert payload["daily"]["time"][0] == "2024-05-01"


def test_fetch_gives_up_after_3_failures(no_sleep):
    session = FakeSession([requests.Timeout("slow")] * 3)
    with pytest.raises(weather.WeatherAPIError, match="Gave up after 3"):
        weather.fetch_daily_weather(6.93, 79.86, "2024-05-01", "2024-05-03", session=session)
    assert session.calls == 3


@pytest.mark.parametrize("status", [400, 404, 422])
def test_fetch_does_not_retry_client_errors(status):
    session = FakeSession([FakeResponse(status, {"reason": "bad"})])
    with pytest.raises(weather.WeatherAPIError, match=f"Client error {status}"):
        weather.fetch_daily_weather(6.93, 79.86, "x", "y", session=session)
    assert session.calls == 1


# ---------- CLI date check ----------
@pytest.mark.parametrize("bad", ["2024-13-01", "2024-02-30", "01/05/2024", "abc", ""])
def test_valid_date_rejects(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        weather.valid_date(bad)


def test_valid_date_accepts():
    assert weather.valid_date("2024-12-31") == "2024-12-31"


# ---------- validation (one test function, 4 bad-data cases) ----------
def test_validate_weather_passes_good_data(weather_df):
    assert weather.validate_weather(weather_df) is weather_df


@pytest.mark.parametrize(
    "column, row, value, error",
    [
        ("rainfall_mm", 0, -5.0, "Negative rainfall"),
        ("temperature_2m_min", 1, 40.0, "temp_min > temp_max"),
        ("date", 2, pd.Timestamp("2024-05-01").date(), "Duplicate dates"),
    ],
)
def test_validate_weather_rejects_bad_data(weather_df, column, row, value, error):
    weather_df.loc[row, column] = value
    with pytest.raises(weather.WeatherAPIError, match=error):
        weather.validate_weather(weather_df)


def test_validate_weather_rejects_missing_column(weather_df):
    with pytest.raises(weather.WeatherAPIError, match="Missing columns"):
        weather.validate_weather(weather_df.drop(columns=["rainfall_mm"]))


def test_validate_weather_rejects_mostly_empty_column(weather_df):
    weather_df["rainfall_mm"] = None  # what ERA5-Land gave us for rainfall
    with pytest.raises(weather.WeatherAPIError, match="Too many missing"):
        weather.validate_weather(weather_df)


def test_validate_weather_warns_on_few_nulls(caplog):
    dates = pd.date_range("2024-01-01", periods=40).date
    df = pd.DataFrame(
        {
            "date": dates,
            "rainfall_mm": 1.0,
            "temperature_2m_mean": 28.0,
            "temperature_2m_max": 31.0,
            "temperature_2m_min": 25.0,
        }
    )
    df.loc[0, "rainfall_mm"] = None  # 1 of 40 = 2.5% -> below the 5% limit
    weather.validate_weather(df)
    assert "1 missing values" in caplog.text  # caplog captures log output


# ---------- file output ----------
def test_run_district_adds_district_and_saves(tmp_path, monkeypatch, sample_payload):
    monkeypatch.setattr(weather, "fetch_daily_weather", lambda *a, **k: sample_payload)
    out = weather.run_district("kandy", "2024-05-01", "2024-05-03", tmp_path)
    df = pd.read_csv(out)
    assert out.name == "kandy_daily_2024-05-01_2024-05-03.csv"
    assert (df["district"] == "kandy").all()
    assert len(df) == 3


def test_rate_limit_stops_immediately():
    session = FakeSession([FakeResponse(429, {"reason": "Daily API request limit exceeded"})])
    with pytest.raises(weather.RateLimitError):
        weather.fetch_daily_weather(6.93, 79.86, "2024-01-01", "2024-01-31", session=session)
    assert session.calls == 1


def test_params_pin_one_model():
    assert weather.build_params(7.0, 80.0, "2024-01-01", "2024-01-02")["models"] == "era5_seamless"


def test_save_csv_creates_folders(tmp_path):
    out = weather.save_csv(pd.DataFrame({"a": [1, 2]}), tmp_path / "nested" / "x.csv")
    assert out.exists()


# ---------- integration: real API (skipped by default) ----------
@pytest.mark.network
def test_real_api_colombo_one_week():
    payload = weather.fetch_daily_weather(6.9271, 79.8612, "2024-05-01", "2024-05-07")
    df = weather.validate_weather(weather.to_dataframe(payload))
    assert len(df) == 7


# ---------- --as-of window ----------
def test_window_from_as_of():
    assert weather.window_from_as_of("2026-09-28", 35) == ("2026-08-19", "2026-09-22")  # 6-day ERA5-Land lag
