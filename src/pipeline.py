"""
Run the whole local pipeline in order - one command (Airflow runs the same steps as separate tasks).
Ends with batch forecasts from the @champion model if MLflow is running (skipped with a warning otherwise).

Run:  python -m src.pipeline                       (silver -> SCD2 -> dbt build, using existing bronze)
      python -m src.pipeline --fetch --start 2024-01-01 --end 2024-12-31   (also re-pull weather)
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time

from src.config import PROJECT_ROOT
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

DBT_BIN = os.getenv("DW_DBT_BIN", "dbt")   # Airflow image sets this to its dbt virtualenv
DBT_ARGS = ["--project-dir", str(PROJECT_ROOT / "dbt"), "--profiles-dir", str(PROJECT_ROOT / "dbt")]


def run_step(name: str, cmd: list[str]) -> None:
    """Run one step as its own process (like an Airflow task). Stop the pipeline on failure."""
    t0 = time.perf_counter()
    logger.info("STEP START %s", name)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    secs = time.perf_counter() - t0
    if result.returncode != 0:
        logger.error("STEP FAIL  %s (exit %d, %.1fs) - pipeline stopped", name, result.returncode, secs)
        raise SystemExit(result.returncode)
    logger.info("STEP OK    %s (%.1fs)", name, secs)


def py(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="re-download weather first")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-31")
    args = parser.parse_args()

    setup_logging()
    if args.fetch:
        run_step("extract weather",
                 py("src.extract.weather", "--start", args.start, "--end", args.end, "--district", "all"))
        run_step("extract NDCU PDFs", py("src.extract.ndcu"))
        run_step("extract WER history (pinned)", py("src.extract.wer_history"))
    run_step("parse NDCU PDFs", py("src.transform.ndcu_parse"))
    run_step("load silver", py("src.load.duckdb_load"))
    run_step("scd2 regions", py("src.transform.scd2"))
    run_step("dbt build (gold models + tests)", [DBT_BIN, "build", *DBT_ARGS])
    # --soft: if MLflow isn't running / no champion yet, warn and carry on (cases-only outputs still work)
    run_step("forecast with @champion model", py("src.ml.predict", "--soft"))
    logger.info("PIPELINE DONE")


if __name__ == "__main__":
    main()
