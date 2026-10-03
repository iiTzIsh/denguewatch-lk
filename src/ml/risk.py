"""Map a case forecast to a risk level against the target week's outbreak level (endemic threshold).

high: >= outbreak level; watch: >= ALERT_RATIO x level; normal: below; unknown: no level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Best F1 at both horizons on the 2014-2025 backtest (in-sample, so slightly optimistic).
# Below 1 because the model under-predicts peaks.
ALERT_RATIO = 0.8


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
