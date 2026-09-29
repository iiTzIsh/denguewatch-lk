"""
SCD Type 2 region dimension from dated reference snapshots.

Run:  python -m src.transform.scd2
      (applies every reference/moh_snapshots/moh_YYYY-MM-DD.csv in date order)

Idea: the dimension KEEPS HISTORY. When an MOH area changes (or disappears),
      the old row is closed (valid_to set, is_current = false) and a new row is added.
      Facts join on the row that was valid at the fact's date -> history stays correct.

IMPORTANT: this table is INCREMENTAL - never CREATE OR REPLACE it, or history is lost.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import duckdb

from src.config import DB_PATH, REFERENCE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = REFERENCE_DIR / "moh_snapshots"
OPEN_END = "9999-12-31"   # industry convention: 'still valid' = far-future date (no NULLs in BETWEEN)
TRACKED = ["district", "parent_moh_area", "boundary_note"]   # a change in these = new version

DDL = f"""
CREATE SCHEMA IF NOT EXISTS gold;
CREATE TABLE IF NOT EXISTS gold.dim_region (
    region_sk        VARCHAR PRIMARY KEY,   -- md5(moh_area | valid_from) : one per VERSION
    moh_area         VARCHAR NOT NULL,      -- natural/business key (same across versions)
    district         VARCHAR,
    parent_moh_area  VARCHAR,
    boundary_note    VARCHAR,
    row_hash         VARCHAR NOT NULL,      -- md5 of tracked columns -> fast change detection
    valid_from       DATE NOT NULL,
    valid_to         DATE NOT NULL DEFAULT DATE '{OPEN_END}',
    is_current       BOOLEAN NOT NULL
);
"""

HASH_EXPR = "md5(concat_ws('|', " + ", ".join(f"coalesce({c}, '')" for c in TRACKED) + "))"


def ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(DDL)


def latest_applied(con: duckdb.DuckDBPyConnection) -> date | None:
    row = con.execute("SELECT max(valid_from) FROM gold.dim_region").fetchone()
    return row[0] if row else None


def apply_snapshot(con: duckdb.DuckDBPyConnection, csv_path: Path, as_of: date) -> dict[str, int]:
    """Merge one full snapshot into the SCD2 table. Returns counts of expired/inserted rows."""
    last = latest_applied(con)
    if last is not None and as_of < last:
        raise ValueError(f"Snapshot {as_of} is older than already-applied {last} - out of order")

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE stg AS
        SELECT *, {HASH_EXPR} AS row_hash
        FROM read_csv_auto(?, all_varchar = true)
        """,
        [str(csv_path)],
    )

    # 1) EXPIRE: current rows that changed OR disappeared from the snapshot
    expired = con.execute(
        """
        UPDATE gold.dim_region d
        SET valid_to = ?, is_current = false
        WHERE d.is_current
          AND NOT EXISTS (SELECT 1 FROM stg s WHERE s.moh_area = d.moh_area AND s.row_hash = d.row_hash)
        RETURNING region_sk
        """,
        [as_of],
    ).fetchall()

    # 2) INSERT: snapshot rows with no identical current row (new areas + new versions)
    inserted = con.execute(
        """
        INSERT INTO gold.dim_region
        SELECT md5(s.moh_area || '|' || CAST(? AS VARCHAR)), s.moh_area, s.district,
               s.parent_moh_area, s.boundary_note, s.row_hash, ?, DATE '9999-12-31', true
        FROM stg s
        WHERE NOT EXISTS (
            SELECT 1 FROM gold.dim_region d
            WHERE d.is_current AND d.moh_area = s.moh_area AND d.row_hash = s.row_hash
        )
        RETURNING region_sk
        """,
        [as_of, as_of],
    ).fetchall()

    counts = {"expired": len(expired), "inserted": len(inserted)}
    logger.info("Snapshot %s: %s", as_of, counts)
    return counts


def snapshot_files(folder: Path = SNAPSHOT_DIR) -> list[tuple[date, Path]]:
    """moh_YYYY-MM-DD.csv -> sorted [(date, path)]"""
    out = []
    for f in folder.glob("moh_*.csv"):
        m = re.fullmatch(r"moh_(\d{4}-\d{2}-\d{2})\.csv", f.name)
        if m:
            out.append((date.fromisoformat(m.group(1)), f))
    return sorted(out)


def main() -> None:
    setup_logging()
    with duckdb.connect(str(DB_PATH)) as con:
        ensure_table(con)
        last = latest_applied(con)
        for as_of, path in snapshot_files():
            if last is not None and as_of < last:
                logger.info("Skip %s (already applied)", path.name)
                continue
            apply_snapshot(con, path, as_of)
        print(con.sql("SELECT moh_area, parent_moh_area, boundary_note, valid_from, valid_to, is_current "
                      "FROM gold.dim_region ORDER BY moh_area, valid_from").df().to_string(index=False))


if __name__ == "__main__":
    main()
