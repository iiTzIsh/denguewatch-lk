"""
Forecasting models behind ONE small interface, so the backtest treats baselines and ML the same way:

    model.fit(train_df, horizon)  ->  model
    model.predict(test_df)        ->  np.ndarray of predicted cases

Baselines need no training, but they still get fit() so they plug into the same walk-forward loop.
A real ML model is only worth deploying if it beats these.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd


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
