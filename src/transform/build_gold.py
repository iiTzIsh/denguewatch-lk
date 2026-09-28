"""
Build the gold star schema, then run data tests - a mini version of `dbt build`.

Run:  python -m src.transform.build_gold
      (run python -m src.load.duckdb_load first so silver tables exist)

Models: sql/models/*.sql  run in file-name order (01_, 02_ ... = dependency order)
Tests:  sql/tests/*.sql   each query returns FAILING rows -> 0 rows = PASS
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

DB_PATH = Path("data/denguewatch.duckdb")
MODELS_DIR = Path("sql/models")
TESTS_DIR = Path("sql/tests")


def run_models(con: duckdb.DuckDBPyConnection, models_dir: Path = MODELS_DIR) -> list[str]:
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    done = []
    for f in sorted(models_dir.glob("*.sql")):
        con.execute(f.read_text(encoding="utf-8"))
        logger.info("MODEL OK   %s", f.name)
        done.append(f.name)
    return done


def run_tests(con: duckdb.DuckDBPyConnection, tests_dir: Path = TESTS_DIR) -> dict[str, int]:
    """Returns {test_name: failing_row_count}."""
    results: dict[str, int] = {}
    for f in sorted(tests_dir.glob("*.sql")):
        rows = con.execute(f.read_text(encoding="utf-8")).fetchall()
        results[f.stem] = len(rows)
        if rows:
            logger.error("TEST FAIL  %s  (%d failing rows, e.g. %s)", f.stem, len(rows), rows[:3])
        else:
            logger.info("TEST PASS  %s", f.stem)
    return results


def main() -> None:
    setup_logging()
    with duckdb.connect(str(DB_PATH)) as con:
        run_models(con)
        results = run_tests(con)
        for table in ["gold.dim_epi_week", "gold.dim_city", "gold.fact_weather_weekly"]:
            row = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            logger.info("%-26s %6d rows", table, row[0] if row else 0)

    failed = [name for name, n in results.items() if n]
    logger.info("Done. PASS=%d FAIL=%d", len(results) - len(failed), len(failed))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
