"""Weekly batch scoring: forecast each region's latest week with @champion into ml.forecast_weekly.

Run:  python -m src.ml.predict
      python -m src.ml.predict --soft   (exit 0 if the model is unavailable; used by the weekly pipeline)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

import duckdb
import pandas as pd
import requests

from src.config import DB_PATH, MLFLOW_TRACKING_URI
from src.log_setup import setup_logging
from src.ml.features import HORIZONS, THRESHOLDS, load_features, serving_frame
from src.ml.risk import risk_level

logger = logging.getLogger(__name__)

MODEL_NAME = "denguewatch-forecaster"  # duplicated from train.py to avoid importing mlflow
ALIAS = "champion"
MAX_STALENESS_DAYS = 14  # skip regions lagging the newest week by more

DDL = """
CREATE SCHEMA IF NOT EXISTS ml;
CREATE TABLE IF NOT EXISTS ml.forecast_weekly (
    rdhs             VARCHAR,
    district         VARCHAR,
    base_week_start  DATE,       -- last week with data; forecast is as of its end
    base_week_end    DATE,
    horizon_weeks    INTEGER,    -- 2 or 4
    target_week_end  DATE,       -- base_week_end + 7 x horizon
    cases_now        INTEGER,
    pred_cases       DOUBLE,
    outbreak_level   DOUBLE,     -- endemic threshold of the target week (NULL = not enough history)
    risk_level       VARCHAR,    -- high / watch / normal / unknown (src/ml/risk.py)
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
    """Reshape wide model output to one row per region and horizon."""
    parts = []
    for h in HORIZONS:
        level = rows[THRESHOLDS[h]].astype(float)
        p = pred[f"pred_cases_h{h}"].astype(float)
        parts.append(
            pd.DataFrame(
                {
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
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def write(con: duckdb.DuckDBPyConnection, forecasts: pd.DataFrame) -> int:
    """Replace rows for the same base week and model version, then insert."""
    con.execute(DDL)
    con.register("new_forecasts", forecasts)
    con.execute(
        """DELETE FROM ml.forecast_weekly f USING (SELECT DISTINCT base_week_start, model_version FROM new_forecasts) n
           WHERE f.base_week_start = n.base_week_start AND f.model_version = n.model_version"""
    )
    con.execute("INSERT INTO ml.forecast_weekly BY NAME SELECT * FROM new_forecasts")
    con.unregister("new_forecasts")
    return len(forecasts)


class MlflowUnreachable(Exception):
    pass


def check_server(uri: str | None = None, timeout_s: float = 3.0) -> None:
    """Fail fast if the tracking server is down; MLflow's client retries for about 5 minutes."""
    uri = uri or MLFLOW_TRACKING_URI
    if not uri.startswith(("http://", "https://")):
        return  # local store or Databricks: nothing to ping
    try:
        resp = requests.get(uri.rstrip("/") + "/health", timeout=timeout_s)
    except requests.RequestException as exc:
        raise MlflowUnreachable(f"no MLflow server at {uri} ({type(exc).__name__})") from exc
    if resp.status_code != 200:
        raise MlflowUnreachable(f"MLflow at {uri} answered HTTP {resp.status_code}")


def load_champion():  # noqa: ANN201 - mlflow types only exist when mlflow is installed
    check_server()
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
    except Exception as exc:  # no mlflow, server down, or no @champion yet
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
    logger.info(
        "Wrote %d forecasts (model v%s, base week ending %s). Risk counts: %s",
        n,
        version,
        forecasts["base_week_end"].max(),
        counts,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
