"""Yearly walk-forward backtest of each model and horizon, logged as one MLflow run each.

skill_vs_naive = 1 - MAE(model) / MAE(last value); > 0 means the model beats persistence.
Run:  python -m src.ml.backtest
      python -m src.ml.backtest --models lgbm_growth --horizons 4
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from src.config import MLFLOW_EXPERIMENT, MLFLOW_TRACKING_URI
from src.log_setup import setup_logging
from src.ml.features import HORIZONS, TARGETS, THRESHOLDS, load_features
from src.ml.models import BASELINES, MODELS, Forecaster, LastValue, LightGBMGrowth
from src.ml.risk import is_alert

logger = logging.getLogger(__name__)

TEST_YEARS = list(range(2014, 2026))  # 2014 leaves enough history; 2017 is the epidemic year


def walk_forward(df: pd.DataFrame, model: Forecaster, horizon: int, test_years: list[int]) -> pd.DataFrame:
    """One row per region-week in the test years with y_true, y_pred and threshold."""
    target, thr = TARGETS[horizon], THRESHOLDS[horizon]
    labelled = df[df[target].notna()]
    out = []
    for year in test_years:
        test = labelled[labelled["year"] == year]
        if test.empty:
            continue
        cutoff = test["week_start"].min()
        # purge rows whose target week ends inside the test year
        train = labelled[labelled["week_end"] + pd.Timedelta(days=7 * horizon) < cutoff]
        model.fit(train, horizon)
        out.append(
            pd.DataFrame(
                {
                    "rdhs": test["rdhs"].to_numpy(),
                    "year": year,
                    "week_start": test["week_start"].to_numpy(),
                    "y_true": test[target].to_numpy(dtype=float),
                    "y_pred": np.clip(model.predict(test), 0, None),
                    "threshold": test[thr].to_numpy(dtype=float),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def score(pred: pd.DataFrame) -> dict[str, float]:
    err = pred["y_pred"] - pred["y_true"]
    m = {
        "mae": float(err.abs().mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "n_rows": float(len(pred)),
    }
    # outbreak = cases above that week's endemic threshold (src/ml/risk.py)
    lab = pred[pred["threshold"].notna()]
    actual = lab["y_true"] > lab["threshold"]
    called = lab["y_pred"] > lab["threshold"]
    tp = float((actual & called).sum())
    m["outbreak_weeks"] = float(actual.sum())
    m["outbreak_recall"] = tp / actual.sum() if actual.sum() else float("nan")
    m["outbreak_precision"] = tp / called.sum() if called.sum() else float("nan")
    # alert = "watch" or "high", i.e. forecast >= ALERT_RATIO x outbreak level
    alert = is_alert(lab["y_pred"], lab["threshold"])
    tp_a = float((actual & alert).sum())
    m["alert_recall"] = tp_a / actual.sum() if actual.sum() else float("nan")
    m["alert_precision"] = tp_a / alert.sum() if alert.sum() else float("nan")
    return m


def by_year(pred: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"year": y, **score(g)} for y, g in pred.groupby("year")])


def skill_vs_naive(pred: pd.DataFrame, df: pd.DataFrame, horizon: int, test_years: list[int]) -> float:
    naive = walk_forward(df, LastValue(), horizon, test_years)
    return 1 - float((pred["y_pred"] - pred["y_true"]).abs().mean()) / float(
        (naive["y_pred"] - naive["y_true"]).abs().mean()
    )


def log_run(pred: pd.DataFrame, model: Forecaster, horizon: int, df: pd.DataFrame, test_years: list[int]) -> dict:
    overall = score(pred)
    overall["skill_vs_naive"] = skill_vs_naive(pred, df, horizon, test_years)
    yearly = by_year(pred)
    with mlflow.start_run(run_name=f"{model.name}_h{horizon}"):
        mlflow.set_tags(
            {
                "model_family": "baseline" if model.name in BASELINES else "ml",
                "horizon_weeks": horizon,
                "validation": "walk_forward_yearly",
            }
        )
        mlflow.log_params(
            {
                "model": model.name,
                "horizon": horizon,
                "test_years": f"{test_years[0]}-{test_years[-1]}",
                "data_rows": len(df),
                "data_last_week": str(df["week_start"].max().date()),
            }
        )
        if isinstance(model, LightGBMGrowth):
            mlflow.log_params({f"lgbm_{k}": v for k, v in model.params.items()})
            mlflow.log_param("use_weather", model.use_weather)
        mlflow.log_metrics(overall)
        y2017 = yearly.loc[yearly["year"] == 2017]
        if not y2017.empty:
            mlflow.log_metrics(
                {
                    "mae_2017": float(y2017["mae"].iloc[0]),
                    "outbreak_recall_2017": float(y2017["outbreak_recall"].iloc[0]),
                }
            )
        for _, r in yearly.iterrows():
            mlflow.log_metric("mae_by_year", float(r["mae"]), step=int(r["year"]))
        with tempfile.TemporaryDirectory() as tmp:
            pred.to_csv(Path(tmp) / "backtest_predictions.csv", index=False)
            yearly.to_csv(Path(tmp) / "backtest_by_year.csv", index=False)
            if isinstance(model, LightGBMGrowth):  # last fold, trained on the most data
                model.feature_importance().to_csv(Path(tmp) / "feature_importance_last_fold.csv", index=False)
            mlflow.log_artifacts(tmp, artifact_path="backtest")
    return overall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default=",".join(MODELS), help=f"comma list from {list(MODELS)}")
    parser.add_argument("--horizons", default=",".join(map(str, HORIZONS)))
    args = parser.parse_args()

    setup_logging()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    df = load_features()
    logger.info("Features: %d rows, %s -> %s", len(df), df["week_start"].min().date(), df["week_start"].max().date())

    rows = []
    for h in map(int, args.horizons.split(",")):
        for name in args.models.split(","):
            model = MODELS[name]()
            pred = walk_forward(df, model, h, TEST_YEARS)
            m = log_run(pred, model, h, df, TEST_YEARS)
            rows.append({"model": name, "h": h, **{k: round(v, 3) for k, v in m.items()}})
            logger.info(
                "%s h=%d  MAE=%.2f  skill vs naive=%+.1f%%  outbreak recall=%.2f",
                name,
                h,
                m["mae"],
                100 * m["skill_vs_naive"],
                m["outbreak_recall"],
            )
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\nOpen {MLFLOW_TRACKING_URI} -> experiment '{MLFLOW_EXPERIMENT}' to compare runs.")


if __name__ == "__main__":
    main()
