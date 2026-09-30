"""
Weekly DATA DRIFT check (Evidently): do the model's inputs this season look like what it learned on?

    current   = model features of the last CURRENT_WEEKS weeks (all regions)
    reference = the SAME calendar months in the previous REFERENCE_YEARS years
                (dengue + weather are seasonal: comparing June to the whole year would "drift" every June)

Per feature: normalised Wasserstein distance, drifted if >= 0.3 (Evidently's default 0.1 flagged 22/22
features even in a normal past year - dengue and weather genuinely differ year to year).

CALIBRATED ALARM: the same check run for every year 2014-2025 (last 8 weeks to mid-September vs the same
months of the 5 years before) gave drifted shares of 0.23-0.55 in normal years and 0.64 in the 2017
epidemic (90th percentile 0.59). So drift_detected = share >= DRIFT_SHARE (0.60).
Re-check with:  python -m src.ml.monitor --calibrate

If drift is detected, the weekly Airflow DAG triggers the retrain DAG (champion/challenger then decides
whether the new model is actually better).

Outputs
  ml.drift_runs                          one row per check (DuckDB) - dashboard + Airflow read it
  data/reports/drift/drift_<date>.html   full interactive Evidently report (latest KEEP_REPORTS kept)

Run:  python -m src.ml.monitor
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.config import DATA_DIR, DB_PATH
from src.log_setup import setup_logging
from src.ml.features import load_features, model_matrix

logger = logging.getLogger(__name__)

CURRENT_WEEKS = 8
REFERENCE_YEARS = 5
DRIFT_METHOD = "wasserstein"
DRIFT_THRESHOLD = 0.3        # per feature
DRIFT_SHARE = 0.60           # alarm level for the share of drifted features (calibrated, see docstring)
CALIBRATION_YEARS = range(2014, 2026)
REPORT_DIR = DATA_DIR / "reports" / "drift"
KEEP_REPORTS = 12
EXCLUDE = {"month"}          # identical by construction (same months) - not informative

DDL = """
CREATE SCHEMA IF NOT EXISTS ml;
CREATE TABLE IF NOT EXISTS ml.drift_runs (
    base_week_end     DATE,        -- newest week in the current window
    current_from      DATE,
    reference_from    DATE,
    reference_to      DATE,
    n_reference       INTEGER,
    n_current         INTEGER,
    n_features        INTEGER,
    n_drifted         INTEGER,
    drift_share       DOUBLE,
    drift_detected    BOOLEAN,
    drifted_features  VARCHAR,     -- JSON list
    report_path       VARCHAR,
    checked_at        TIMESTAMP
);
"""


def windows(df: pd.DataFrame, current_weeks: int = CURRENT_WEEKS,
            reference_years: int = REFERENCE_YEARS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the feature table into (reference, current) rows - see module docstring."""
    starts = sorted(df["week_start"].unique())
    current_from = pd.Timestamp(starts[-min(current_weeks, len(starts))])
    current = df[df["week_start"] >= current_from]
    months = set(current["month"].astype(int))
    reference = df[
        (df["week_start"] < current_from)
        & (df["week_start"] >= current_from - pd.DateOffset(years=reference_years))
        & (df["month"].astype(int).isin(months))
    ]
    return reference, current


def _column_drift(metric: dict[str, Any]) -> tuple[str, bool] | None:
    """Parse one Evidently ValueDrift result -> (column, drifted?)."""
    name = str(metric.get("metric_name") or "")
    m = re.match(r"ValueDrift\(column=(?P<col>[^,]+),method=(?P<method>[^,]+),threshold=(?P<thr>[0-9.eE-]+)\)", name)
    if not m or metric.get("value") is None:
        return None
    value, thr = float(metric["value"]), float(m.group("thr"))
    drifted = value < thr if "p_value" in m.group("method") else value >= thr   # p-value vs distance
    return m.group("col"), drifted


def run_drift(reference: pd.DataFrame, current: pd.DataFrame) -> tuple[dict[str, Any], Any]:
    from evidently import Report  # heavy import: only when the check actually runs
    from evidently.presets import DataDriftPreset

    ref_x = model_matrix(reference).drop(columns=list(EXCLUDE))
    cur_x = model_matrix(current).drop(columns=list(EXCLUDE))
    snapshot = Report([DataDriftPreset(method=DRIFT_METHOD, threshold=DRIFT_THRESHOLD)]).run(cur_x, ref_x)
    parsed = [c for c in (_column_drift(m) for m in snapshot.dict()["metrics"]) if c is not None]
    drifted = sorted(col for col, is_drifted in parsed if is_drifted)
    n = len(parsed)
    share = len(drifted) / n if n else 0.0
    summary = {
        "base_week_end": current["week_end"].max().date(),
        "current_from": current["week_start"].min().date(),
        "reference_from": reference["week_start"].min().date(),
        "reference_to": reference["week_start"].max().date(),
        "n_reference": len(reference),
        "n_current": len(current),
        "n_features": n,
        "n_drifted": len(drifted),
        "drift_share": round(share, 3),
        "drift_detected": share >= DRIFT_SHARE,
        "drifted_features": json.dumps(drifted),
    }
    return summary, snapshot


def save_report(snapshot: Any, base_week_end: object, report_dir: Path = REPORT_DIR) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"drift_{base_week_end}.html"
    snapshot.save_html(str(path))
    for old in sorted(report_dir.glob("drift_*.html"))[:-KEEP_REPORTS]:
        old.unlink()
    return path


def write(con: duckdb.DuckDBPyConnection, summary: dict[str, Any]) -> None:
    """Idempotent per base week: re-running the check replaces that week's row."""
    con.execute(DDL)
    con.execute("DELETE FROM ml.drift_runs WHERE base_week_end = ?", [summary["base_week_end"]])
    row = pd.DataFrame([summary])
    con.register("new_drift", row)
    con.execute("INSERT INTO ml.drift_runs BY NAME SELECT * FROM new_drift")
    con.unregister("new_drift")


def latest_drift_detected(db_path: Path = DB_PATH) -> bool:
    """Used by the Airflow DAG to decide whether to trigger a retrain. No ML libraries needed."""
    try:
        with duckdb.connect(str(db_path), read_only=True) as con:
            row = con.execute(
                "SELECT drift_detected FROM ml.drift_runs ORDER BY checked_at DESC LIMIT 1").fetchone()
    except duckdb.Error:
        return False
    return bool(row and row[0])


def calibrate(df: pd.DataFrame, years: range = CALIBRATION_YEARS, month_day: str = "09-14") -> pd.DataFrame:
    """Drift share of each past year (same construction as the live check) -> what is 'normal'."""
    rows = []
    for y in years:
        reference, current = windows(df[df["week_start"] < pd.Timestamp(f"{y}-{month_day}")])
        summary, _ = run_drift(reference, current)
        rows.append({"year": y, "drift_share": summary["drift_share"], "n_drifted": summary["n_drifted"]})
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly data drift check (Evidently)")
    parser.add_argument("--calibrate", action="store_true", help="print the drift share of every past year")
    args = parser.parse_args()
    setup_logging()
    df = load_features()
    if args.calibrate:
        cal = calibrate(df)
        print(cal.to_string(index=False))
        print(f"\n90th percentile: {cal['drift_share'].quantile(0.9):.2f}   current alarm level: {DRIFT_SHARE}")
        return 0
    reference, current = windows(df)
    if len(reference) < 100 or len(current) < 26:
        logger.warning("Not enough rows for a drift check (reference %d, current %d) - skipped",
                       len(reference), len(current))
        return 0
    summary, snapshot = run_drift(reference, current)
    summary["report_path"] = str(save_report(snapshot, summary["base_week_end"]))
    summary["checked_at"] = datetime.now(UTC).replace(tzinfo=None)
    with duckdb.connect(str(DB_PATH)) as con:
        write(con, summary)
    level = logging.WARNING if summary["drift_detected"] else logging.INFO
    logger.log(level, "Drift %s: %d/%d features drifted (%.0f%%) - current %s..%s vs same months %s..%s. %s",
               "DETECTED" if summary["drift_detected"] else "ok", summary["n_drifted"], summary["n_features"],
               100 * summary["drift_share"], summary["current_from"], summary["base_week_end"],
               summary["reference_from"], summary["reference_to"], summary["drifted_features"])
    logger.info("Report: %s", summary["report_path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
