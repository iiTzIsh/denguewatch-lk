"""Risk rule, batch scoring output + idempotent writes, and the forecast consumers (no MLflow needed)."""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest

from src import queries as q
from src.alerts import telegram as tg
from src.ml import predict
from src.ml.risk import is_alert, risk_level


def test_risk_levels():
    pred = pd.Series([120.0, 85.0, 50.0, 30.0])
    level = pd.Series([100.0, 100.0, 100.0, np.nan])
    assert risk_level(pred, level).tolist() == ["high", "watch", "normal", "unknown"]
    assert is_alert(pred, level).tolist() == [True, True, False, False]


def rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rdhs": ["colombo", "mannar", "kandy"],
            "district": ["colombo", "mannar", "kandy"],
            "week_start": pd.to_datetime(["2026-05-11", "2026-05-11", "2026-04-13"]),  # kandy is 4 weeks stale
            "week_end": pd.to_datetime(["2026-05-17", "2026-05-17", "2026-04-19"]),
            "cases": [308, 2, 90],
            "target_threshold_h2": [400.0, np.nan, 100.0],
            "target_threshold_h4": [350.0, 10.0, 100.0],
        }
    )


def test_latest_rows_skips_stale_regions():
    assert sorted(predict.latest_rows(rows())["rdhs"]) == ["colombo", "mannar"]


def model_output(r: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"pred_cases_h2": [360.0, 3.0][: len(r)], "pred_cases_h4": [420.0, 4.0][: len(r)]})


def test_to_long_and_idempotent_write():
    r = predict.latest_rows(rows())
    scored = pd.Timestamp("2026-09-30 08:00").to_pydatetime()
    fc = predict.to_long(r, model_output(r), "3", scored)
    assert len(fc) == 4  # 2 regions x 2 horizons
    col = fc.set_index(["rdhs", "horizon_weeks"])
    assert col.loc[("colombo", 4), "risk_level"] == "high"  # 420 >= 350
    assert col.loc[("colombo", 2), "risk_level"] == "watch"  # 360 >= 0.8 x 400
    assert col.loc[("mannar", 2), "risk_level"] == "unknown"  # no outbreak level
    assert str(col.loc[("colombo", 4), "target_week_end"]) == "2026-06-14"

    con = duckdb.connect()
    predict.write(con, fc)
    predict.write(con, fc)  # same week + model version -> replaced
    assert con.execute("SELECT count(*) FROM ml.forecast_weekly").fetchone()[0] == 4
    predict.write(con, fc.assign(model_version="4", scored_at=pd.Timestamp("2026-10-01").to_pydatetime()))
    assert con.execute("SELECT count(*) FROM ml.forecast_weekly").fetchone()[0] == 8  # history kept
    assert con.execute("SELECT DISTINCT model_version FROM ml.forecast_latest").fetchall() == [("4",)]

    wide = q.latest_forecast(con)
    assert wide["rdhs"].tolist() == ["colombo", "mannar"]  # riskiest first
    assert wide.loc[0, "risk_4w"] == "high" and wide.loc[0, "pred_4w"] == 420.0


def test_latest_forecast_empty_before_first_scoring():
    assert q.latest_forecast(duckdb.connect()).empty


def test_soft_mode_never_fails(monkeypatch):
    def boom():
        raise ConnectionError("MLflow down")

    monkeypatch.setattr(predict, "load_champion", boom)
    monkeypatch.setattr("sys.argv", ["predict", "--soft"])
    assert predict.main() == 0
    monkeypatch.setattr("sys.argv", ["predict"])
    assert predict.main() == 1


# ---------- alert text ----------
CASES = pd.DataFrame(
    {"district": ["colombo"], "cases": [207], "change": [-15], "week_start": pd.Timestamp("2026-05-25")}
)


def wide(risk_4w: str, pred_4w: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rdhs": ["colombo"],
            "district": ["colombo"],
            "base_week_end": [pd.Timestamp("2026-05-17")],
            "cases_now": [308],
            "model_version": ["3"],
            "pred_2w": [300.0],
            "level_2w": [900.0],
            "risk_2w": ["normal"],
            "pred_4w": [pred_4w],
            "level_4w": [500.0],
            "risk_4w": [risk_4w],
        }
    )


def test_alert_lists_flagged_regions():
    msg = tg.build_message("2026-W37", CASES, forecast=wide("watch", 420.0))
    assert "model v3" in msg and "case data to 17 May" in msg
    assert "⚠️ Colombo: ~420 cases in 4 wks (outbreak level 500) - watch" in msg


def test_alert_says_all_clear_and_closest():
    msg = tg.build_message("2026-W37", CASES, forecast=wide("normal", 250.0))
    assert "No region is forecast near its outbreak level" in msg
    assert "Closest: Colombo ~250 vs level 500 (50%)" in msg


@pytest.mark.parametrize("fc", [None, pd.DataFrame()])
def test_alert_without_forecast_is_cases_only(fc):
    msg = tg.build_message("2026-W37", CASES, forecast=fc)
    assert "Forecast" not in msg and "not official health advice" in msg


def test_alert_hides_stale_forecast():
    old_cases_week = CASES.assign(week_start=pd.Timestamp("2026-09-07"))  # forecast data ends 17 May
    msg = tg.build_message("2026-W37", old_cases_week, forecast=wide("high", 900.0))
    assert "Forecast is stale" in msg and "⚠️ Colombo" not in msg


def test_check_server_fails_fast(monkeypatch):
    import requests

    def refused(url, timeout):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(predict.requests, "get", refused)
    with pytest.raises(predict.MlflowUnreachable):
        predict.check_server("http://localhost:5000")
    predict.check_server("sqlite:///mlflow.db")  # non-HTTP stores are not pinged


def test_soft_mode_is_fast_when_mlflow_down(monkeypatch):
    import time

    import requests

    monkeypatch.setattr(
        predict.requests, "get", lambda url, timeout: (_ for _ in ()).throw(requests.ConnectionError("refused"))
    )
    monkeypatch.setattr(predict, "MLFLOW_TRACKING_URI", "http://localhost:5000")
    monkeypatch.setattr("sys.argv", ["predict", "--soft"])
    t0 = time.perf_counter()
    assert predict.main() == 0
    assert time.perf_counter() - t0 < 5
