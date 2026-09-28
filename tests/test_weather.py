"""
Day 4 tests. No real network calls: we pass a FAKE session into the function.
Run: pytest -v
"""
from __future__ import annotations

import pandas as pd
import pytest
import requests

from src.extract import weather

SAMPLE_PAYLOAD = {
    "latitude": 6.93,
    "longitude": 79.86,
    "daily": {
        "time": ["2024-05-01", "2024-05-02", "2024-05-03"],
        "precipitation_sum": [12.5, 0.0, 40.2],
        "temperature_2m_mean": [28.1, 28.9, 27.4],
        "temperature_2m_max": [31.0, 32.0, 30.1],
        "temperature_2m_min": [25.2, 25.9, 24.8],
    },
}


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 500:
            raise requests.HTTPError(f"{self.status_code} server error")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Returns the queued responses in order; an Exception in the queue gets raised."""

    def __init__(self, responses: list):
        self.responses = responses
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


# ---------- Test 1: parsing ----------
def test_to_dataframe_parses_payload():
    df = weather.to_dataframe(SAMPLE_PAYLOAD)
    assert len(df) == 3
    assert "rainfall_mm" in df.columns
    assert df["rainfall_mm"].sum() == pytest.approx(52.7)


# ---------- Test 2: bad data fails loudly ----------
def test_to_dataframe_raises_on_missing_daily():
    with pytest.raises(weather.WeatherAPIError):
        weather.to_dataframe({"latitude": 6.93})


# ---------- Test 3: retry logic ----------
def test_fetch_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)  # don't actually wait
    session = FakeSession([
        requests.ConnectionError("network down"),
        FakeResponse(503),
        FakeResponse(200, SAMPLE_PAYLOAD),
    ])
    payload = weather.fetch_daily_weather(6.93, 79.86, "2024-05-01", "2024-05-03", session=session)
    assert session.calls == 3
    assert payload["daily"]["time"][0] == "2024-05-01"


# ---------- Bonus: 4xx is NOT retried ----------
def test_fetch_does_not_retry_client_error():
    session = FakeSession([FakeResponse(400, {"reason": "bad date"})])
    with pytest.raises(weather.WeatherAPIError):
        weather.fetch_daily_weather(6.93, 79.86, "bad", "bad", session=session)
    assert session.calls == 1


# ---------- Bonus: save_csv creates folders ----------
def test_save_csv_creates_file(tmp_path):
    df = pd.DataFrame({"a": [1, 2]})
    out = weather.save_csv(df, tmp_path / "nested" / "x.csv")
    assert out.exists()
