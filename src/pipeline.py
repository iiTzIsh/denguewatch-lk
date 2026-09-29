"""
Run the whole local pipeline in order - one command (this is what Airflow will orchestrate in Week 3).

Run:  python -m src.pipeline                       (silver -> SCD2 -> gold, using existing bronze)
      python -m src.pipeline --fetch --start 2024-01-01 --end 2024-12-31   (also re-pull weather)
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)


def run_step(name: str, module: str, *args: str) -> None:
    """Run one step as its own process - same as Airflow running a task. Stop on failure."""
    t0 = time.perf_counter()
    logger.info("STEP START %s", name)
    result = subprocess.run([sys.executable, "-m", module, *args])
    secs = time.perf_counter() - t0
    if result.returncode != 0:
        logger.error("STEP FAIL  %s (exit %d, %.1fs) - pipeline stopped", name, result.returncode, secs)
        raise SystemExit(result.returncode)
    logger.info("STEP OK    %s (%.1fs)", name, secs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="re-download weather first")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-31")
    args = parser.parse_args()

    setup_logging()
    if args.fetch:
        run_step("extract weather", "src.extract.weather", "--start", args.start, "--end", args.end, "--city", "all")
    run_step("load silver", "src.load.duckdb_load")
    run_step("scd2 regions", "src.transform.scd2")
    run_step("build gold + tests", "src.transform.build_gold")
    logger.info("PIPELINE DONE")


if __name__ == "__main__":
    main()
