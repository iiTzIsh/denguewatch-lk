"""
Auto-check your SQL exercises against the solutions (compares RESULTS, not query text).

Run:  python -m src.load.check_exercises          (all)
      python -m src.load.check_exercises ex03     (one)
Don't open sql/exercises/solutions/ until you've tried!
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import duckdb
import pandas as pd

from src.config import DB_PATH, SQL_DIR

EX_DIR = SQL_DIR / "exercises"
SOL_DIR = EX_DIR / "solutions"


def has_query(sql: str) -> bool:
    code = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    return bool(re.search(r"\b(select|with)\b", code, re.IGNORECASE))


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Order of rows/columns shouldn't matter; tiny float differences shouldn't either."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df[sorted(df.columns)]
    for c in df.select_dtypes("number").columns:
        df[c] = df[c].astype(float).round(1)
    df = df.astype(str)
    return df.sort_values(list(df.columns)).reset_index(drop=True)


def check(con: duckdb.DuckDBPyConnection, ex_file: Path) -> str:
    mine = ex_file.read_text(encoding="utf-8").strip().rstrip(";")
    if not has_query(mine):
        return "TODO"
    try:
        got = normalise(con.sql(mine).df())
    except duckdb.Error as exc:
        return f"SQL ERROR: {str(exc).splitlines()[0]}"
    want = normalise(con.sql((SOL_DIR / ex_file.name).read_text(encoding="utf-8")).df())
    if list(got.columns) != list(want.columns):
        return f"FAIL: columns {list(got.columns)} - expected {list(want.columns)}"
    if len(got) != len(want):
        return f"FAIL: {len(got)} rows - expected {len(want)}"
    if not got.equals(want):
        return "FAIL: right shape, different values"
    return "PASS"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("only", nargs="?", help="e.g. ex03")
    args = parser.parse_args()
    files = sorted(EX_DIR.glob("ex*.sql"))
    if args.only:
        files = [f for f in files if f.name.startswith(args.only)]
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        results = {f.stem: check(con, f) for f in files}
    for name, res in results.items():
        print(f"{name:28} {res}")
    print(f"\nScore: {sum(r == 'PASS' for r in results.values())}/{len(results)}")


if __name__ == "__main__":
    main()
