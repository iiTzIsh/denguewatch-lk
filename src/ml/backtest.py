"""
Walk-forward backtest + MLflow tracking.

For each test year Y (default 2014 -> 2025):
    train on weeks whose TARGET is already known before Y starts   (no peeking into Y)
    predict every week of Y
Then score all years together, per year, and the 2017 epidemic on its own.

Every model x horizon becomes one MLflow run: params, metrics, per-year MAE chart, and the
predictions file as an artifact, so any number in the README can be traced back to a run.

Run:  docker compose up -d mlflow           (once; UI at http://localhost:5000)
      python -m src.ml.backtest             (all baselines, h = 2 and 4)
      python -m src.ml.backtest --models seasonal_naive --horizons 2
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
from src.ml.models import BASELINES, Forecaster

logger = logging.getLogger(__name__)

TEST_YEARS = list(range(2014, 2026))   # 2014: enough history before it; 2017 = the big epidemic


def walk_forward(df: pd.DataFrame, model: Forecaster, horizon: int, test_years: list[int]) -> pd.DataFrame:
    """Return one row per (region, week) in the test years with y_true / y_pred / threshold."""
    target, thr = TARGETS[horizon], THRESHOLDS[horizon]
    labelled = df[df[target].notna()]
    out = []
    for year in test_years:
        test = labelled[labelled["year"] == year]
        if test.empty:
            continue
        cutoff = test["week_start"].min()
        # purge: a training row is usable only if its target week ended before the test year starts
        train = labelled[labelled["week_end"] + pd.Timedelta(days=7 * horizon) < cutoff]
        model.fit(train, horizon)
        out.append(pd.DataFrame({
            "rdhs": test["rdhs"].to_numpy(),
            "year": year,
            "week_start": test["week_start"].to_numpy(),
            "y_true": test[target].to_numpy(dtype=float),
            "y_pred": np.clip(model.predict(test), 0, None),
            "threshold": test[thr].to_numpy(dtype=float),
        }))
    return pd.concat(out, ignore_index=True)


def score(pred: pd.DataFrame) -> dict[str, float]:
    err = pred["y_pred"] - pred["y_true"]
    m = {
        "mae": float(err.abs().mean()),
        "rmse": float(np.sqrt((err**2).mean())),
        "n_rows": float(len(pred)),
    }
    # outbreak = cases above the endemic threshold (mean + 2 SD of the same week in the last 5 years)
    lab = pred[pred["threshold"].notna()]
    actual = lab["y_true"] > lab["threshold"]
    called = lab["y_pred"] > lab["threshold"]
    tp = float((actual & called).sum())
    m["outbreak_weeks"] = float(actual.sum())
    m["outbreak_recall"] = tp / actual.sum() if actual.sum() else float("nan")
    m["outbreak_precision"] = tp / called.sum() if called.sum() else float("nan")
    return m


def by_year(pred: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"year": y, **score(g)} for y, g in pred.groupby("year")])


def log_run(pred: pd.DataFrame, model: Forecaster, horizon: int, df: pd.DataFrame, test_years: list[int]) -> dict:
    overall = score(pred)
    yearly = by_year(pred)
    with mlflow.start_run(run_name=f"{model.name}_h{horizon}"):
        mlflow.set_tags({"model_family": "baseline" if model.name in BASELINES else "ml",
                         "horizon_weeks": horizon, "validation": "walk_forward_yearly"})
        mlflow.log_params({
            "model": model.name, "horizon": horizon,
            "test_years": f"{test_years[0]}-{test_years[-1]}",
            "data_rows": len(df), "data_last_week": str(df["week_start"].max().date()),
        })
        mlflow.log_metrics(overall)
        y2017 = yearly.loc[yearly["year"] == 2017]
        if not y2017.empty:
            mlflow.log_metrics({"mae_2017": float(y2017["mae"].iloc[0]),
                                "outbreak_recall_2017": float(y2017["outbreak_recall"].iloc[0])})
        for _, r in yearly.iterrows():                     # "mae_by_year" chart in the MLflow UI
            mlflow.log_metric("mae_by_year", float(r["mae"]), step=int(r["year"]))
        with tempfile.TemporaryDirectory() as tmp:
            pred.to_csv(Path(tmp) / "backtest_predictions.csv", index=False)
            yearly.to_csv(Path(tmp) / "backtest_by_year.csv", index=False)
            mlflow.log_artifacts(tmp, artifact_path="backtest")
    return overall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default=",".join(BASELINES), help=f"comma list from {list(BASELINES)}")
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
            model = BASELINES[name]()
            pred = walk_forward(df, model, h, TEST_YEARS)
            m = log_run(pred, model, h, df, TEST_YEARS)
            rows.append({"model": name, "h": h, **{k: round(v, 3) for k, v in m.items()}})
            logger.info("%s h=%d  MAE=%.2f  outbreak recall=%.2f", name, h, m["mae"], m["outbreak_recall"])
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\nOpen {MLFLOW_TRACKING_URI} -> experiment '{MLFLOW_EXPERIMENT}' to compare runs.")


if __name__ == "__main__":
    main()
