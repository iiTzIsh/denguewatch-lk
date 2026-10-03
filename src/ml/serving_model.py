"""MLflow pyfunc that forecasts all horizons from feature rows.

Bundling feature building with the boosters avoids training/serving skew.
Output columns: rdhs, week_start, week_end, pred_cases_h2, pred_cases_h4.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from mlflow.pyfunc import PythonModel

from src.ml.features import serving_frame
from src.ml.models import LightGBMGrowth


class DengueForecastModel(PythonModel):
    def __init__(self, models: dict[int, LightGBMGrowth]) -> None:
        self.models = models

    def predict(self, context: Any, model_input: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        x = serving_frame(model_input)
        out = x[["rdhs", "week_start", "week_end"]].copy()
        for h, m in sorted(self.models.items()):
            out[f"pred_cases_h{h}"] = np.clip(m.predict(x), 0, None).round(1)
        return out
