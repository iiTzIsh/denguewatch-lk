"""One-command setup: skip when already set up, stop on required failures, continue on optional ones."""

from __future__ import annotations

import duckdb
import pytest

from src import bootstrap


class Result:
    def __init__(self, code):
        self.returncode = code


def test_already_set_up(tmp_path, monkeypatch):
    db = tmp_path / "w.duckdb"
    monkeypatch.setattr(bootstrap, "DB_PATH", db)
    assert bootstrap.already_set_up() is False  # no file
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE SCHEMA ml; CREATE TABLE ml.forecast_weekly (rdhs VARCHAR)")
    assert bootstrap.already_set_up() is False  # table but no forecasts
    with duckdb.connect(str(db)) as con:
        con.execute("INSERT INTO ml.forecast_weekly VALUES ('colombo')")
    assert bootstrap.already_set_up() is True


def test_required_step_failure_stops(monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: Result(1))
    with pytest.raises(bootstrap.StepFailed):
        bootstrap.step("x", ["cmd"])


def test_optional_step_failure_continues(monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: Result(bootstrap.RATE_LIMITED))
    assert bootstrap.step("weather", ["cmd"], required=False) == bootstrap.RATE_LIMITED


def test_main_skips_when_set_up(monkeypatch):
    monkeypatch.setattr(bootstrap, "already_set_up", lambda: True)
    monkeypatch.setattr(bootstrap, "run", lambda: pytest.fail("should not run the steps"))
    monkeypatch.setattr("sys.argv", ["bootstrap"])
    assert bootstrap.main() == 0


def test_main_force_runs_and_reports_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "already_set_up", lambda: True)

    def fake_run():
        calls.append(1)
        raise bootstrap.StepFailed("train")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    monkeypatch.setattr("sys.argv", ["bootstrap", "--force"])
    assert bootstrap.main() == 1 and calls == [1]
