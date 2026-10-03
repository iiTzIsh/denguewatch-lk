"""Rebuild past weeks' forecasts as of each week (no hindsight) to seed forecast-accuracy history.

scored_at is base week_end + 1 day, so the live @champion batch stays the latest.
Run:  python -m src.ml.replay [--weeks 30]
"""

from __future__ import annotations

import argparse
import logging
import sys

import duckdb
import pandas as pd

from src.config import DB_PATH
from src.log_setup import setup_logging
from src.ml import predict
from src.ml.features import HORIZONS, TARGETS, load_features
from src.ml.models import LightGBMGrowth

logger = logging.getLogger(__name__)

MODEL_NAME, MODEL_VERSION = "asof-replay", "replay"


def replay_week(df: pd.DataFrame, base_start: pd.Timestamp) -> pd.DataFrame:
    rows = df[df["week_start"] == base_start].reset_index(drop=True)
    as_of = rows["week_end"].max()
    preds = {}
    for h in HORIZONS:
        train = df[df[TARGETS[h]].notna() & (df["week_end"] + pd.Timedelta(days=7 * h) <= as_of)]
        preds[f"pred_cases_h{h}"] = LightGBMGrowth().fit(train, h).predict(rows).clip(min=0).round(1)
    out = predict.to_long(rows, pd.DataFrame(preds), MODEL_VERSION, (as_of + pd.Timedelta(days=1)).to_pydatetime())
    out["model_name"] = MODEL_NAME
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=16, help="how many of the newest base weeks to replay")
    args = parser.parse_args()
    setup_logging()

    df = load_features()
    weeks = sorted(df["week_start"].unique())[-args.weeks :]
    parts = []
    for w in weeks:
        parts.append(replay_week(df, pd.Timestamp(w)))
        logger.info("replayed base week %s", pd.Timestamp(w).date())
    forecasts = pd.concat(parts, ignore_index=True)
    with duckdb.connect(str(DB_PATH)) as con:
        n = predict.write(con, forecasts)
    logger.info("Wrote %d as-of replay forecasts for %d base weeks", n, len(weeks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
