"""
Train -> evaluate -> register -> promote (champion / challenger).

1. Backtest the challenger config (walk-forward 2014-2025) for every horizon.
2. Fit the final model on ALL labelled weeks.
3. Log it to MLflow as a pyfunc and register a new version of `denguewatch-forecaster`.
4. Promote it to alias @champion ONLY if
     a) it beats the naive "same as this week" baseline at every horizon  (skill_vs_naive > 0), and
     b) it is not worse than the current champion by more than 1% MAE at any horizon.
   Otherwise the version stays registered but is tagged "rejected" with the reason.
   The old champion keeps alias @previous_champion -> one-command rollback.

Consumers load:  mlflow.pyfunc.load_model("models:/denguewatch-forecaster@champion")

Run:  python -m src.ml.train            (Airflow runs it monthly: dags/retrain_monthly.py)
"""
from __future__ import annotations

import logging
import sys

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from mlflow.models import infer_signature

from src.config import MLFLOW_EXPERIMENT, MLFLOW_TRACKING_URI, PROJECT_ROOT
from src.log_setup import setup_logging
from src.ml import backtest
from src.ml.features import HORIZONS, TARGETS, load_features, serving_frame
from src.ml.models import LightGBMGrowth
from src.ml.serving_model import DengueForecastModel

logger = logging.getLogger(__name__)

MODEL_NAME = "denguewatch-forecaster"
CHAMPION, PREVIOUS = "champion", "previous_champion"
MAX_WORSE_THAN_CHAMPION = 0.01      # 1% MAE tolerance (noise between retrains)
MIN_LABELLED_ROWS = 10_000          # data sanity gate: refuse to train on a broken/partial warehouse


def evaluate(df: pd.DataFrame) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for h in HORIZONS:
        pred = backtest.walk_forward(df, LightGBMGrowth(), h, backtest.TEST_YEARS)
        s = backtest.score(pred)
        metrics[f"mae_h{h}"] = s["mae"]
        metrics[f"rmse_h{h}"] = s["rmse"]
        metrics[f"outbreak_recall_h{h}"] = s["outbreak_recall"]
        metrics[f"outbreak_precision_h{h}"] = s["outbreak_precision"]
        metrics[f"alert_recall_h{h}"] = s["alert_recall"]
        metrics[f"alert_precision_h{h}"] = s["alert_precision"]
        metrics[f"skill_vs_naive_h{h}"] = backtest.skill_vs_naive(pred, df, h, backtest.TEST_YEARS)
    return metrics


def fit_final(df: pd.DataFrame) -> dict[int, LightGBMGrowth]:
    return {h: LightGBMGrowth().fit(df[df[TARGETS[h]].notna()], h) for h in HORIZONS}


def decide(new: dict[str, float], champion: dict[str, float] | None) -> tuple[bool, str]:
    """Pure function (easy to unit test): should the new version become champion?"""
    for h in HORIZONS:
        if new[f"skill_vs_naive_h{h}"] <= 0:
            return False, f"does not beat naive baseline at h={h} (skill {new[f'skill_vs_naive_h{h}']:+.3f})"
    if champion is None:
        return True, "first model that beats the naive baseline"
    for h in HORIZONS:
        limit = champion[f"mae_h{h}"] * (1 + MAX_WORSE_THAN_CHAMPION)
        if new[f"mae_h{h}"] > limit:
            return False, f"worse than champion at h={h}: MAE {new[f'mae_h{h}']:.2f} > {limit:.2f}"
    return True, "beats naive and matches/beats the current champion"


def champion_metrics(client: MlflowClient) -> tuple[str | None, dict[str, float] | None]:
    try:
        mv = client.get_model_version_by_alias(MODEL_NAME, CHAMPION)
    except MlflowException:
        return None, None                                   # no model / no champion yet
    if mv.run_id is None:
        return str(mv.version), None
    return str(mv.version), client.get_run(mv.run_id).data.metrics


def main() -> int:
    setup_logging()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    client = MlflowClient()

    df = load_features()
    labelled = int(df[TARGETS[max(HORIZONS)]].notna().sum())
    if labelled < MIN_LABELLED_ROWS:
        logger.error("Only %d labelled rows (< %d) - refusing to train. Run the pipeline first.",
                     labelled, MIN_LABELLED_ROWS)
        return 2

    metrics = evaluate(df)
    models = fit_final(df)
    sample = serving_frame(df.tail(5))
    wrapper = DengueForecastModel(models)

    with mlflow.start_run(run_name="train_forecaster") as run:
        mlflow.set_tags({"model_family": "ml", "stage": "candidate", "validation": "walk_forward_yearly"})
        mlflow.log_params({f"lgbm_{k}": v for k, v in models[HORIZONS[0]].params.items()})
        mlflow.log_params({"horizons": ",".join(map(str, HORIZONS)), "train_rows": labelled,
                           "data_last_week": str(df["week_start"].max().date()),
                           "test_years": f"{backtest.TEST_YEARS[0]}-{backtest.TEST_YEARS[-1]}"})
        mlflow.log_metrics(metrics)
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=wrapper,
            code_paths=[str(PROJECT_ROOT / "src")],          # the model carries its own feature code
            input_example=sample,
            signature=infer_signature(sample, wrapper.predict(None, sample)),
            pip_requirements=str(PROJECT_ROOT / "requirements-ml.txt"),
            registered_model_name=MODEL_NAME,
        )
        new_version = str(info.registered_model_version)

    old_version, old_metrics = champion_metrics(client)
    promote, reason = decide(metrics, old_metrics)
    client.set_model_version_tag(MODEL_NAME, new_version, "decision", "promoted" if promote else "rejected")
    client.set_model_version_tag(MODEL_NAME, new_version, "reason", reason)
    if promote:
        if old_version:
            client.set_registered_model_alias(MODEL_NAME, PREVIOUS, old_version)
        client.set_registered_model_alias(MODEL_NAME, CHAMPION, new_version)
    logger.info("%s v%s: %s (%s). run=%s", MODEL_NAME, new_version,
                "PROMOTED to @champion" if promote else "NOT promoted", reason, run.info.run_id)
    for h in HORIZONS:
        logger.info("  h=%d  MAE %.2f  skill vs naive %+.1f%%", h, metrics[f"mae_h{h}"],
                    100 * metrics[f"skill_vs_naive_h{h}"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
