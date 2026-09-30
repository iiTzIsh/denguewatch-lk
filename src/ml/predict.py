"""
Weekly BATCH SCORING: load the @champion model from the MLflow registry, forecast the latest week of
every region, and write the result to the warehouse (DuckDB  ml.forecast_weekly).

Consumers (dashboard, API, Telegram alert) read the TABLE - they never load the model, so they stay
light and keep working even if MLflow is down. Every forecast is kept (history), which later lets us
score forecasts against what really happened.

Run:  python -m src.ml.predict            (fails loudly if MLflow / the champion is missing)
      python -m src.ml.predict --soft     (warn and exit 0 instead - used inside the weekly pipeline,
                                           so a missing model never blocks the cases-only alert)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

import duckdb
import pandas as pd

from src.config import DB_PATH, MLFLOW_TRACKING_URI
from src.log_setup import setup_logging
from src.ml.features import HORIZONS, THRESHOLDS, load_features, serving_frame
from src.ml.risk import risk_level

logger = logging.getLogger(__name__)

MODEL_NAME = "denguewatch-forecaster"      # same name as src/ml/train.py (kept here to avoid importing mlflow early)
ALIAS = "champion"
MAX_STALENESS_DAYS = 14                    # a region whose last week is >2 weeks behind the newest is skipped

DDL = """
CREATE SCHEMA IF NOT EXISTS ml;
CREATE TABLE IF NOT EXISTS ml.forecast_weekly (
    rdhs             VARCHAR,
    district         VARCHAR,
    base_week_start  DATE,       -- last week with data (the forecast is made "as of" its end)
    base_week_end    DATE,
    horizon_weeks    INTEGER,    -- 2 or 4
    target_week_end  DATE,       -- base_week_end + 7 x horizon
    cases_now        INTEGER,
    pred_cases       DOUBLE,
    outbreak_level   DOUBLE,     -- endemic threshold of the target week (NULL = not enough history)
    risk_level       VARCHAR,    -- high / watch / normal / unknown  (src/ml/risk.py)
    model_name       VARCHAR,
    model_version    VARCHAR,
    scored_at        TIMESTAMP
);
CREATE OR REPLACE VIEW ml.forecast_latest AS
SELECT * FROM ml.forecast_weekly WHERE scored_at = (SELECT max(scored_at) FROM ml.forecast_weekly);
"""


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Each region's newest week, if it is not stale."""
    newest = df.groupby("rdhs")["week_start"].transform("max")
    rows = df[df["week_start"] == newest]
    cutoff = df["week_start"].max() - pd.Timedelta(days=MAX_STALENESS_DAYS)
    stale = rows[rows["week_start"] < cutoff]
    if not stale.empty:
        logger.warning("Skipping stale regions: %s", ", ".join(sorted(stale["rdhs"])))
    return rows[rows["week_start"] >= cutoff].reset_index(drop=True)


def to_long(rows: pd.DataFrame, pred: pd.DataFrame, version: str, scored_at: datetime) -> pd.DataFrame:
    """Wide model output (pred_cases_h2, pred_cases_h4) -> one row per region x horizon."""
    parts = []
    for h in HORIZONS:
        level = rows[THRESHOLDS[h]].astype(float)
        p = pred[f"pred_cases_h{h}"].astype(float)
        parts.append(pd.DataFrame({
            "rdhs": rows["rdhs"],
            "district": rows["district"],
            "base_week_start": rows["week_start"].dt.date,
            "base_week_end": rows["week_end"].dt.date,
            "horizon_weeks": h,
            "target_week_end": (rows["week_end"] + pd.Timedelta(days=7 * h)).dt.date,
            "cases_now": rows["cases"].astype(int),
            "pred_cases": p,
            "outbreak_level": level.round(1),
            "risk_level": risk_level(p, level),
            "model_name": MODEL_NAME,
            "model_version": version,
            "scored_at": scored_at,
        }))
    return pd.concat(parts, ignore_index=True)


def write(con: duckdb.DuckDBPyConnection, forecasts: pd.DataFrame) -> int:
    """Idempotent: re-scoring the same base week with the same model version replaces those rows."""
    con.execute(DDL)
    con.register("new_forecasts", forecasts)
    con.execute(
        """DELETE FROM ml.forecast_weekly f USING (SELECT DISTINCT base_week_start, model_version FROM new_forecasts) n
           WHERE f.base_week_start = n.base_week_start AND f.model_version = n.model_version"""
    )
    con.execute("INSERT INTO ml.forecast_weekly BY NAME SELECT * FROM new_forecasts")
    con.unregister("new_forecasts")
    return len(forecasts)


def load_champion():  # noqa: ANN201 - mlflow types only exist when mlflow is installed
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    version = str(MlflowClient().get_model_version_by_alias(MODEL_NAME, ALIAS).version)
    return mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@{ALIAS}"), version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soft", action="store_true", help="warn + exit 0 if MLflow or the champion is missing")
    args = parser.parse_args()
    setup_logging()

    try:
        model, version = load_champion()
    except Exception as exc:  # ImportError (no mlflow), connection refused, no @champion yet ...
        msg = f"Cannot load {MODEL_NAME}@{ALIAS} from {MLFLOW_TRACKING_URI}: {type(exc).__name__}: {exc}"
        if args.soft:
            logger.warning("%s - skipping forecasts (--soft)", msg)
            return 0
        logger.error(msg)
        return 1

    rows = latest_rows(load_features())
    pred = model.predict(serving_frame(rows))
    forecasts = to_long(rows, pred, version, datetime.now(UTC).replace(tzinfo=None))
    with duckdb.connect(str(DB_PATH)) as con:
        n = write(con, forecasts)
    counts = forecasts.groupby(["horizon_weeks", "risk_level"]).size().to_dict()
    logger.info("Wrote %d forecasts (model v%s, base week ending %s). Risk counts: %s",
                n, version, forecasts["base_week_end"].max(), counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
