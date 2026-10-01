from __future__ import annotations

from datetime import date

import pytest

from src.extract import weather_backfill as bf


def test_year_chunks_cut_last_year():
    assert bf.year_chunks(2025, date(2026, 3, 10)) == [
        ("2025-01-01", "2025-12-31"),
        ("2026-01-01", "2026-03-10"),
    ]


def test_plan_skips_files_that_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "WEATHER_BRONZE_DIR", tmp_path)
    all_chunks = bf.plan(2025, date(2025, 12, 31))
    assert len(all_chunks) == 25                       # 1 year x 25 districts
    (tmp_path / "colombo_daily_2025-01-01_2025-12-31.csv").write_text("x")
    assert len(bf.plan(2025, date(2025, 12, 31))) == 24  # resumable: done chunk skipped


def test_stops_after_consecutive_failures(tmp_path, monkeypatch):
    """No internet -> stop after 5 failures instead of grinding through ~500 calls."""
    monkeypatch.setattr(bf, "WEATHER_BRONZE_DIR", tmp_path)
    monkeypatch.setattr(bf.time, "sleep", lambda s: None)
    calls = []

    def fail(district, start, end, out_dir):
        calls.append(district)
        raise bf.WeatherAPIError("unreachable")

    monkeypatch.setattr(bf, "run_district", fail)
    monkeypatch.setattr("sys.argv", ["weather_backfill", "--from-year", "2025"])
    with pytest.raises(SystemExit) as exc:
        bf.main()
    assert exc.value.code == bf.UNREACHABLE
    assert len(calls) == bf.MAX_CONSECUTIVE_FAILURES
