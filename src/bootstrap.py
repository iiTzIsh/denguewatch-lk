"""
ONE-COMMAND SETUP: fresh clone -> working system (data, gold tables, trained model, forecasts, monitoring).

Runs automatically as the `init` service of `docker compose up -d`, or by hand:
    python -m src.bootstrap              (skips everything if the system is already set up)
    python -m src.bootstrap --force      (run all steps again)

Steps (each one is idempotent - safe to repeat):
  1. WER history 2006->2026 (pinned denguedatahub commit)             required
  2. NDCU weekly PDFs                                                  site down -> continue with what we have
  3. Weather 2006->now (Open-Meteo, resumable)                         daily limit -> continue, finish tomorrow
  4. Pipeline: parse -> silver -> SCD2 -> dbt build (all data tests)   required
  5. Train + register the model in MLflow (@champion)                  required
  6. Forecasts, as-of replay, accuracy table, drift check              required
  7. Print the Telegram message (dry run - never sends from here)

Exit codes: 0 = ready (maybe with warnings) · 1 = a required step failed
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

import duckdb

from src.config import DB_PATH, PROJECT_ROOT, WEATHER_BRONZE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

DBT_BIN = os.getenv("DW_DBT_BIN", "dbt")
DBT_ARGS = ["--project-dir", str(PROJECT_ROOT / "dbt"), "--profiles-dir", str(PROJECT_ROOT / "dbt")]
RATE_LIMITED, UNREACHABLE = 3, 4       # exit codes of src.extract.weather_backfill


class StepFailed(Exception):
    pass


def py(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def step(name: str, cmd: list[str], required: bool = True, ok_codes: tuple[int, ...] = (0,)) -> int:
    t0 = time.perf_counter()
    logger.info("==> %s", name)
    code = subprocess.run(cmd, cwd=PROJECT_ROOT).returncode
    secs = time.perf_counter() - t0
    if code in ok_codes:
        logger.info("    ok (%.0fs)", secs)
    elif required:
        logger.error("    FAILED (exit %d) - setup stopped. Fix the error above, then run it again.", code)
        raise StepFailed(name)
    else:
        logger.warning("    did not finish (exit %d, %.0fs) - continuing with the data we have", code, secs)
    return code


def already_set_up() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            row = con.execute("SELECT count(*) FROM ml.forecast_weekly").fetchone()
    except duckdb.Error:
        return False
    return bool(row and row[0] > 0)


def run() -> None:
    step("1/7 WER dengue history (2006 -> 2026)", py("src.extract.wer_history"))
    step("2/7 NDCU weekly PDFs", py("src.extract.ndcu"), required=False)

    code = step("3/7 Weather 2006 -> now (Open-Meteo, resumable)", py("src.extract.weather_backfill"),
                required=False, ok_codes=(0,))
    if code == RATE_LIMITED:
        logger.warning("    Open-Meteo daily limit reached. Older years will be filled in by re-running "
                       "`docker compose run --rm init --force` tomorrow (it continues where it stopped).")
    elif code == UNREACHABLE:
        logger.warning("    Open-Meteo unreachable - continuing with the weather files already on disk.")
    if not list(WEATHER_BRONZE_DIR.glob("*.csv")):
        logger.error("    No weather files at all - check the internet connection, then run setup again.")
        raise StepFailed("weather")

    step("4/7 Pipeline: parse -> silver -> SCD2 -> dbt build + data tests", py("src.pipeline"))
    step("5/7 Train model -> MLflow registry (@champion if it beats the baseline)", py("src.ml.train"))
    step("6/7 Forecasts + as-of replay + accuracy table + drift check", py("src.ml.predict"))
    step("    as-of replay (honest forecast history)", py("src.ml.replay"))
    step("    forecast vs actual table", [DBT_BIN, "build", "--select", "mart_forecast_accuracy", *DBT_ARGS])
    step("    drift check (Evidently)", py("src.ml.monitor"))
    step("7/7 Telegram message preview (not sent)", py("src.alerts.telegram", "--dry-run"), required=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="run all steps even if already set up")
    args = parser.parse_args()
    setup_logging()

    if already_set_up() and not args.force:
        logger.info("Already set up (forecasts exist in %s) - nothing to do. Use --force to rebuild.", DB_PATH)
        return 0
    t0 = time.perf_counter()
    try:
        run()
    except StepFailed:
        return 1
    logger.info("")
    logger.info("DengueWatch LK is ready (%.0f min).", (time.perf_counter() - t0) / 60)
    logger.info("  Dashboard  http://localhost:8501")
    logger.info("  API        http://localhost:8000/docs")
    logger.info("  MLflow     http://localhost:5000")
    logger.info("  Airflow (weekly automation):  docker compose -f docker-compose.airflow.yml up -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
