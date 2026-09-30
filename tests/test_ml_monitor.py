"""Drift windows + parsing + detection, as-of replay (no hindsight), and the model-health queries."""
from __future__ import annotations

import json
from datetime import datetime

import duckdb
import pandas as pd
import pytest

from src.ml import monitor, replay
from src.reports import dashboard_data as dd
from tests.test_ml_backtest import full_features


def test_windows_use_same_months_in_the_past():
    df = full_features()
    df["month"] = df["week_end"].dt.month
    ref, cur = monitor.windows(df, current_weeks=8, reference_years=3)
    assert cur["week_start"].nunique() == 8
    assert ref["week_start"].max() < cur["week_start"].min()                      # strictly the past
    assert set(ref["month"]) <= set(cur["month"])                                   # same season only
    assert ref["week_start"].min() >= cur["week_start"].min() - pd.DateOffset(years=3)


@pytest.mark.parametrize(
    ("name", "value", "drifted"),
    [
        ("ValueDrift(column=rain_w0_mm,method=Wasserstein distance (normed),threshold=0.3)", 0.45, True),
        ("ValueDrift(column=rain_w0_mm,method=Wasserstein distance (normed),threshold=0.3)", 0.10, False),
        ("ValueDrift(column=cases,method=K-S p_value,threshold=0.05)", 0.001, True),   # small p = drift
        ("ValueDrift(column=cases,method=K-S p_value,threshold=0.05)", 0.40, False),
    ],
)
def test_column_drift_parsing(name, value, drifted):
    assert monitor._column_drift({"metric_name": name, "value": value})[1] is drifted


def test_column_drift_ignores_other_metrics():
    assert monitor._column_drift({"metric_name": "DriftedColumnsCount(drift_share=0.5)", "value": {}}) is None


def test_run_drift_detects_a_real_shift():
    pytest.importorskip("evidently")
    df = full_features()
    df["month"] = df["week_end"].dt.month
    ref, cur = monitor.windows(df, current_weeks=26, reference_years=4)
    same, _ = monitor.run_drift(ref, cur)
    shifted_cur = cur.copy()
    for c in ("rain_w0_mm", "rain_w1_mm", "rain_w2_mm", "rain_w3_mm", "rain_w4_7_mm", "rain_w8_11_mm",
              "rain_w12_15_mm", "rainy_days_4w", "temp_mean_4w_c", "temp_min_4w_c"):
        shifted_cur[c] = shifted_cur[c] * 5 + 100                                     # a very different season
    shifted, _ = monitor.run_drift(ref, shifted_cur)
    assert shifted["n_drifted"] > same["n_drifted"]
    assert set(json.loads(shifted["drifted_features"])) >= {"rain_w0_mm", "temp_mean_4w_c"}


def summary(week: str, detected: bool) -> dict:
    return {"base_week_end": pd.Timestamp(week).date(), "current_from": pd.Timestamp(week).date(),
            "reference_from": pd.Timestamp("2021-01-01").date(), "reference_to": pd.Timestamp("2025-12-31").date(),
            "n_reference": 500, "n_current": 208, "n_features": 22, "n_drifted": 16 if detected else 3,
            "drift_share": 0.73 if detected else 0.14, "drift_detected": detected,
            "drifted_features": json.dumps(["rain_w0_mm"]), "report_path": "x.html",
            "checked_at": datetime(2026, 9, 30, 8, 0)}


def test_write_is_idempotent_and_latest_flag(tmp_path):
    db = tmp_path / "w.duckdb"
    assert monitor.latest_drift_detected(db) is False                   # no table yet -> never trigger
    with duckdb.connect(str(db)) as con:
        monitor.write(con, summary("2026-09-13", True))
        monitor.write(con, summary("2026-09-13", True))                 # same week -> replaced
        assert con.execute("SELECT count(*) FROM ml.drift_runs").fetchone()[0] == 1
    assert monitor.latest_drift_detected(db) is True
    with duckdb.connect(str(db)) as con:
        monitor.write(con, {**summary("2026-09-20", False), "checked_at": datetime(2026, 10, 1)})
        assert dd.latest_drift(con)["n_drifted"] == 3
    assert monitor.latest_drift_detected(db) is False


# ---------- as-of replay ----------
def test_replay_trains_only_on_the_past(monkeypatch):
    df = full_features()
    df["district"] = df["rdhs"]
    base = df["week_start"].sort_values().unique()[-10]
    as_of = df.loc[df["week_start"] == base, "week_end"].max()
    seen = []
    real_fit = replay.LightGBMGrowth.fit

    def spy(self, train, horizon):
        seen.append((train, horizon))
        self.params["n_estimators"] = 10
        return real_fit(self, train, horizon)

    monkeypatch.setattr(replay.LightGBMGrowth, "fit", spy)
    out = replay.replay_week(df, pd.Timestamp(base))
    for train, h in seen:
        assert (train["week_end"] + pd.Timedelta(days=7 * h) <= as_of).all()   # every target known by then
    assert set(out["model_name"]) == {"asof-replay"} and len(out) == 2 * df["rdhs"].nunique()
    assert (out["scored_at"] == as_of + pd.Timedelta(days=1)).all()


# ---------- model-health queries ----------
@pytest.fixture
def con_acc():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA gold")
    c.execute("""CREATE TABLE gold.mart_forecast_accuracy AS SELECT * FROM (VALUES
        ('colombo','asof-replay','replay',4,DATE '2026-06-14',100.0,80.0,120.0,false,true, TIMESTAMP '2026-05-18'),
        ('colombo','denguewatch-forecaster','2',4,DATE '2026-06-14',110.0,80.0,120.0,true,true, TIMESTAMP '2026-05-20'),
        ('kandy','asof-replay','replay',4,DATE '2026-06-14',50.0,40.0,45.0,false,false, TIMESTAMP '2026-05-18')
      ) t(rdhs, model_name, model_version, horizon_weeks, target_week_end, pred_cases, naive_pred_cases,
          actual_cases, alerted, outbreak_happened, scored_at)""")
    c.execute("ALTER TABLE gold.mart_forecast_accuracy ADD COLUMN abs_error DOUBLE")
    c.execute("ALTER TABLE gold.mart_forecast_accuracy ADD COLUMN naive_abs_error DOUBLE")
    c.execute("UPDATE gold.mart_forecast_accuracy SET abs_error = abs(pred_cases - actual_cases), "
              "naive_abs_error = abs(naive_pred_cases - actual_cases)")
    return c


def test_model_performance(con_acc):
    perf = dd.model_performance(con_acc).set_index("model_name")
    replay_row = perf.loc["asof-replay"]
    assert replay_row["forecasts"] == 2
    assert replay_row["mae"] == pytest.approx((20 + 5) / 2) and replay_row["naive_mae"] == pytest.approx((40 + 5) / 2)
    assert replay_row["skill_vs_naive"] == pytest.approx(1 - 12.5 / 22.5)
    assert perf.loc["denguewatch-forecaster", "correct_alerts"] == 1


def test_forecast_vs_actual_prefers_live_model(con_acc):
    fva = dd.forecast_vs_actual(con_acc, horizon=4)
    assert fva.loc[0, "forecast"] == pytest.approx(110.0 + 50.0)     # colombo from the live model, kandy replay
    assert fva.loc[0, "actual"] == pytest.approx(165.0) and fva.loc[0, "regions"] == 2


def test_health_queries_empty_before_anything_exists():
    c = duckdb.connect()
    assert dd.model_performance(c).empty and dd.forecast_vs_actual(c).empty and dd.latest_drift(c) is None
