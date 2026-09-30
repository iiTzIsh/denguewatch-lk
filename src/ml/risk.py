"""
Turn a case forecast into a risk level. Pure pandas (no ML libraries), so the backtest, the batch
scoring job and any consumer use the SAME rule.

outbreak level = endemic threshold for the target week (gold.mart_ml_features.target_threshold_h*):
                 exp(mean(log(cases+1)) + 2 SD) - 1 over the same +-2 weeks in the last 5 years, min 10 cases

    high   : forecast >= outbreak level
    watch  : forecast >= ALERT_RATIO x outbreak level   (the model under-predicts peaks, so we alert early)
    normal : below that
    unknown: no outbreak level (less than 10 past values for this region/time of year)

ALERT_RATIO = 0.8 was chosen on the 2014-2025 walk-forward backtest: best F1 at both horizons
(h=2: recall 0.70 / precision 0.73; h=4: 0.58 / 0.67). Chosen on the same period it is scored on,
so treat those numbers as slightly optimistic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ALERT_RATIO = 0.8
LEVELS = ("high", "watch", "normal", "unknown")


def risk_level(pred: pd.Series, outbreak_level: pd.Series, ratio: float = ALERT_RATIO) -> pd.Series:
    p = pred.to_numpy(dtype=float)
    t = outbreak_level.to_numpy(dtype=float)
    out = np.select(
        [np.isnan(t), p >= t, p >= ratio * t],
        ["unknown", "high", "watch"],
        default="normal",
    )
    return pd.Series(out, index=pred.index)


def is_alert(pred: pd.Series, outbreak_level: pd.Series, ratio: float = ALERT_RATIO) -> pd.Series:
    return risk_level(pred, outbreak_level, ratio).isin(["high", "watch"])
