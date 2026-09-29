"""
Print the dengue hotspots for one ISO week (default: the latest week NDCU reported).

Run:  python -m src.reports.hotspots
      python -m src.reports.hotspots --week 2026-W30 --top 15
"""
from __future__ import annotations

import argparse

import duckdb

from src.config import DB_PATH

SQL = """
SELECT district, province, cases, cases_change_vs_prev_week AS change,
       rainfall_mm_total AS rain_this_week, rain_lag2_mm AS rain_2wk_ago
FROM gold.mart_ndcu_monitoring
WHERE iso_week_key = ?
ORDER BY cases DESC
LIMIT ?
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", help="ISO week key, e.g. 2026-W37 (default: latest)")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        row = con.execute("SELECT max(iso_week_key) FROM gold.mart_ndcu_monitoring").fetchone()
        week = args.week or (row[0] if row else None)
        if week is None:
            raise SystemExit("No NDCU data yet - run the pipeline first.")
        df = con.execute(SQL, [week, args.top]).df()
    print(f"\nTop {args.top} districts - {week}  (portfolio project, not official health advice)\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
