"""
Shared test fixtures. pytest loads this file automatically -
any test can ask for a fixture just by using its name as an argument.
"""
from __future__ import annotations

import copy

import pandas as pd
import pytest
import requests

from src.extract import weather

_SAMPLE_PAYLOAD = {
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
    """Returns queued responses in order; an Exception in the queue gets raised."""

    def __init__(self, responses: list):
        self.responses = responses
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def sample_payload() -> dict:
    """A fresh deep copy each test, so one test can't break another by editing it."""
    return copy.deepcopy(_SAMPLE_PAYLOAD)


@pytest.fixture
def weather_df(sample_payload) -> pd.DataFrame:
    """Fixtures can use other fixtures."""
    return weather.to_dataframe(sample_payload)


@pytest.fixture
def no_sleep(monkeypatch):
    """Make retries instant."""
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)
