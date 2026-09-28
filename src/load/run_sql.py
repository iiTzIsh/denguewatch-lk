"""
Run every query in a .sql file against the DuckDB warehouse and print the results.

Run:  python -m src.load.run_sql sql/day7_practice.sql
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

DB_PATH = Path("data/denguewatch.duckdb")


def split_queries(sql_text: str) -> list[str]:
    """Split on ';' and drop empty / comment-only chunks."""
    queries = []
    for chunk in sql_text.split(";"):
        code_lines = [ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        if code_lines:
            queries.append(chunk.strip())
    return queries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sql_file")
    args = parser.parse_args()

    queries = split_queries(Path(args.sql_file).read_text(encoding="utf-8"))
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        for i, q in enumerate(queries, 1):
            title = next((ln.strip("- ").strip() for ln in q.splitlines() if ln.strip().startswith("--")), "")
            print(f"\n=== Query {i}: {title} ===")
            print(con.sql(q).df().to_string(index=False))


if __name__ == "__main__":
    main()
