"""
Forecasting models behind ONE small interface, so the backtest treats baselines and ML the same way:

    model.fit(train_df, horizon)  ->  model
    model.predict(test_df)        ->  np.ndarray of predicted cases

Baselines need no training, but they still get fit() so they plug into the same walk-forward loop.
A real ML model is only worth deploying if it beats these.
"""
from __future__ import annotations

from typing import Any, Protocol

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.ml.features import base_level, model_matrix


class Forecaster(Protocol):
    name: str

    def fit(self, train: pd.DataFrame, horizon: int) -> Forecaster: ...

    def predict(self, test: pd.DataFrame) -> np.ndarray: ...


class LastValue:
    """Persistence: cases in h weeks = cases this week."""

    name = "naive_last_value"

    def fit(self, train: pd.DataFrame, horizon: int) -> LastValue:
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return test["cases"].to_numpy(dtype=float)


class Mean4w:
    """Average of the last 4 weeks (smoother than persistence)."""

    name = "naive_mean_4w"

    def fit(self, train: pd.DataFrame, horizon: int) -> Mean4w:
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return test["cases_mean_4w"].fillna(test["cases"]).to_numpy(dtype=float)


class SeasonalNaive:
    """Same week last year (falls back to last value when last year is missing)."""

    name = "seasonal_naive"

    def __init__(self) -> None:
        self.horizon = 2

    def fit(self, train: pd.DataFrame, horizon: int) -> SeasonalNaive:
        self.horizon = horizon
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return test[f"seasonal_naive_h{self.horizon}"].fillna(test["cases"]).to_numpy(dtype=float)


BASELINES: dict[str, type] = {m.name: m for m in (LastValue, Mean4w, SeasonalNaive)}


LGBM_PARAMS: dict[str, Any] = {
    "objective": "l2",
    "n_estimators": 400,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 100,     # small trees + big leaves: 26 regions x 20 years is not much data
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 5.0,
    "random_state": 42,
    "verbose": -1,
}


class LightGBMGrowth:
    """LightGBM that predicts GROWTH: log(cases in h weeks + 1) - log(recent 4-week level + 1).

    Why growth instead of raw counts:
      - one model works for big and small regions (scale-free)
      - trees cannot predict above the highest value seen in training; a growth rate on top of the
        current level can, which matters in record years like 2017
    """

    def __init__(self, use_weather: bool = True, params: dict[str, Any] | None = None) -> None:
        self.use_weather = use_weather
        self.params = {**LGBM_PARAMS, **(params or {})}
        self.name = "lgbm_growth" if use_weather else "lgbm_growth_noweather"
        self.model: lgb.LGBMRegressor | None = None

    def fit(self, train: pd.DataFrame, horizon: int) -> LightGBMGrowth:
        y = np.log1p(train[f"target_cases_h{horizon}"].astype(float)) - np.log1p(base_level(train))
        self.model = lgb.LGBMRegressor(**self.params).fit(model_matrix(train, self.use_weather), y)
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("call fit() first")
        growth = self.model.predict(model_matrix(test, self.use_weather))
        return np.expm1(np.asarray(growth) + np.log1p(base_level(test).to_numpy()))

    def feature_importance(self) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("call fit() first")
        booster = self.model.booster_
        return (pd.DataFrame({"feature": booster.feature_name(),
                              "gain": booster.feature_importance(importance_type="gain")})
                .sort_values("gain", ascending=False, ignore_index=True))


MODELS: dict[str, Any] = {
    **BASELINES,
    "lgbm_growth": lambda: LightGBMGrowth(use_weather=True),
    "lgbm_growth_noweather": lambda: LightGBMGrowth(use_weather=False),   # ablation: what does weather add?
}
