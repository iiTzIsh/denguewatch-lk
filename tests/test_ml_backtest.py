"""Walk-forward backtest: no leakage, correct seasonal lookup, correct scores, and a real MLflow run."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

mlflow = pytest.importorskip("mlflow")

from src.ml import backtest  # noqa: E402
from src.ml.features import seasonal_reference  # noqa: E402
from src.ml.models import BASELINES, LastValue, SeasonalNaive  # noqa: E402


def make_features(years=(2010, 2015), regions=("colombo", "kandy")) -> pd.DataFrame:
    """Weekly Sat->Fri rows; cases = week number + 100*region index (easy to check by hand)."""
    rows = []
    for i, r in enumerate(regions):
        for start in pd.date_range(f"{min(years)}-01-02", f"{max(years)}-12-31", freq="7D"):
            rows.append({"rdhs": r, "week_start": start, "week_end": start + pd.Timedelta(days=6),
                         "year": start.year, "cases": float(start.isocalendar().week + 100 * i)})
    df = pd.DataFrame(rows)
    df["cases_mean_4w"] = df.groupby("rdhs")["cases"].transform(lambda s: s.rolling(4).mean())
    for h in (2, 4):
        df[f"target_cases_h{h}"] = df.groupby("rdhs")["cases"].shift(-h)
        df[f"target_threshold_h{h}"] = 30.0
        df[f"seasonal_naive_h{h}"] = seasonal_reference(df, h)
    return df


def test_seasonal_reference_points_one_year_before_target():
    df = make_features()
    row = df[(df.rdhs == "colombo") & (df.year == 2012)].iloc[10]
    ref = row["week_end"] + pd.Timedelta(days=14 - 364)           # h=2
    expected = df[(df.rdhs == "colombo") & ((df.week_end - ref).abs() <= pd.Timedelta(days=3))]["cases"].iloc[0]
    assert row["seasonal_naive_h2"] == expected


def test_seasonal_reference_is_nan_without_history():
    df = make_features()
    first_weeks = df[df.week_start < pd.Timestamp("2010-06-01")]      # nothing a year earlier exists
    assert first_weeks["seasonal_naive_h2"].isna().all()


class SpyModel(LastValue):
    """Records the training data it was given, so we can check the purge."""

    name = "spy"

    def __init__(self):
        self.seen: list[pd.DataFrame] = []

    def fit(self, train, horizon):
        self.seen.append(train)
        return self


@pytest.mark.parametrize("horizon", [2, 4])
def test_walk_forward_never_trains_on_test_year_targets(horizon):
    df = make_features()
    spy = SpyModel()
    backtest.walk_forward(df, spy, horizon, [2013, 2014])
    for train, year in zip(spy.seen, [2013, 2014], strict=True):
        cutoff = df[df.year == year]["week_start"].min()
        target_end = train["week_end"] + pd.Timedelta(days=7 * horizon)
        assert (target_end < cutoff).all()
        assert not train.empty


def test_walk_forward_output_shape_and_no_negative_predictions():
    df = make_features()
    pred = backtest.walk_forward(df, SeasonalNaive(), 2, [2013, 2014])
    assert set(pred["year"]) == {2013, 2014}
    assert (pred["y_pred"] >= 0).all()
    assert pred["y_true"].notna().all()


def test_score_by_hand():
    pred = pd.DataFrame({"y_true": [10.0, 50.0, 40.0, 5.0], "y_pred": [12.0, 20.0, 45.0, 5.0],
                         "threshold": [30.0, 30.0, 30.0, np.nan]})
    m = backtest.score(pred)
    assert m["mae"] == pytest.approx((2 + 30 + 5 + 0) / 4)
    assert m["outbreak_weeks"] == 2            # 50 and 40 (the NaN-threshold row is ignored)
    assert m["outbreak_recall"] == pytest.approx(0.5)      # caught 40, missed 50
    assert m["outbreak_precision"] == pytest.approx(1.0)   # only called 45 -> correct


def test_log_run_writes_mlflow_run(tmp_path):
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path / 'mlflow.db'}")
    mlflow.set_experiment("test")
    df = make_features()
    model = BASELINES["naive_last_value"]()
    pred = backtest.walk_forward(df, model, 2, [2013, 2014])
    backtest.log_run(pred, model, 2, df, [2013, 2014])
    runs = mlflow.search_runs(experiment_names=["test"])
    assert len(runs) == 1
    assert runs.loc[0, "params.model"] == "naive_last_value"
    assert runs.loc[0, "metrics.mae"] >= 0


# ---------------- LightGBM ----------------
from src.ml.features import WEATHER_COLS, model_matrix  # noqa: E402
from src.ml.models import MODELS, LightGBMGrowth  # noqa: E402


def full_features() -> pd.DataFrame:
    """make_features() + every column the ML model reads (random but deterministic)."""
    df = make_features()
    rng = np.random.default_rng(0)
    g = df.groupby("rdhs")["cases"]
    for k in (1, 2, 3, 4):
        df[f"cases_lag{k}"] = g.shift(k)
    df["cases_mean_8w"] = g.transform(lambda s: s.rolling(8).mean())
    df["cases_same_week_last_year"] = g.shift(52)
    df["endemic_mean_5y"] = df["cases"] * 0.9
    df["endemic_sd_5y"] = 3.0
    df["month"] = df["week_end"].dt.month
    for c in WEATHER_COLS:
        df[c] = rng.gamma(2.0, 10.0, len(df))
    return df


def test_model_matrix_has_no_target_columns():
    cols = model_matrix(full_features()).columns
    assert not [c for c in cols if "target" in c]


def test_model_matrix_without_weather_drops_weather():
    cols = set(model_matrix(full_features(), use_weather=False).columns)
    assert cols.isdisjoint(WEATHER_COLS)


@pytest.mark.parametrize("use_weather", [True, False])
def test_lightgbm_fits_and_predicts_positive_counts(use_weather):
    df = full_features()
    df = df[df["target_cases_h2"].notna()]
    model = LightGBMGrowth(use_weather=use_weather, params={"n_estimators": 20}).fit(df[df.year < 2014], 2)
    pred = model.predict(df[df.year == 2014])
    assert len(pred) == (df.year == 2014).sum()
    assert np.isfinite(pred).all() and (pred >= -1).all()
    assert not model.feature_importance().empty


def test_all_registered_models_run_in_backtest():
    df = full_features()
    for name, factory in MODELS.items():
        model = factory()
        if isinstance(model, LightGBMGrowth):
            model.params["n_estimators"] = 10
        pred = backtest.walk_forward(df, model, 2, [2014])
        assert len(pred) > 0, name
