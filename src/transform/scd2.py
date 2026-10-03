"""SCD Type 2 MOH region dimension (gold.dim_region) built from weekly NDCU MOH observations.

Weeks are merged incrementally; a late report for an already-applied week triggers a full,
deterministic rebuild from silver (gold.dim_region_weeks tracks applied weeks).
Run: python -m src.transform.scd2
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date

import duckdb
import pandas as pd

from src.config import DB_PATH, REFERENCE_DIR
from src.log_setup import setup_logging
from src.transform.ndcu_moh_parse import moh_key

logger = logging.getLogger(__name__)

PARENTS_CSV = REFERENCE_DIR / "moh_parents.csv"  # lk_dengue mapping; split dates unverified
OPEN_END = "9999-12-31"  # far-future end date keeps BETWEEN free of NULLs
TRACKED = ["district", "parent_moh_area", "boundary_note"]  # a change in these = new version
CONFIRM_WEEKS = 3  # consecutive reports needed before a district change is applied

DDL = f"""
CREATE SCHEMA IF NOT EXISTS gold;
CREATE TABLE IF NOT EXISTS gold.dim_region (
    region_sk        VARCHAR PRIMARY KEY,   -- md5(moh_key | valid_from), one per version
    moh_key          VARCHAR NOT NULL,      -- natural key, spelling-normalised
    moh_area         VARCHAR NOT NULL,      -- display name
    district         VARCHAR,
    parent_moh_area  VARCHAR,
    boundary_note    VARCHAR,
    row_hash         VARCHAR NOT NULL,      -- md5 of tracked columns, for change detection
    valid_from       DATE NOT NULL,
    valid_to         DATE NOT NULL DEFAULT DATE '{OPEN_END}',
    is_current       BOOLEAN NOT NULL
);
"""

WEEKS_DDL = "CREATE TABLE IF NOT EXISTS gold.dim_region_weeks (week_start DATE PRIMARY KEY)"

HASH_EXPR = "md5(concat_ws('|', " + ", ".join(f"coalesce({c}, '')" for c in TRACKED) + "))"


def ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(DDL)


def latest_applied(con: duckdb.DuckDBPyConnection) -> date | None:
    row = con.execute("SELECT max(valid_from) FROM gold.dim_region").fetchone()
    return row[0] if row else None


def apply_snapshot(con: duckdb.DuckDBPyConnection, snapshot: pd.DataFrame, as_of: date) -> dict[str, int]:
    """Merge one full snapshot (moh_area, district, parent_moh_area, boundary_note) valid from `as_of`."""
    last = latest_applied(con)
    if last is not None and as_of < last:
        raise ValueError(f"Snapshot {as_of} is older than already-applied {last} - out of order")

    snap = snapshot.astype(object).copy()
    snap = snap.where(snap.notna(), None)
    snap["moh_key"] = snap["moh_area"].map(moh_key)
    for c in ("parent_moh_area", "boundary_note"):
        if c not in snap:
            snap[c] = None
    con.register("snap_df", snap)
    con.execute(f"CREATE OR REPLACE TEMP TABLE stg AS SELECT *, {HASH_EXPR} AS row_hash FROM snap_df")
    con.unregister("snap_df")

    # expire current rows that changed or disappeared from the snapshot
    expired = con.execute(
        """
        UPDATE gold.dim_region d
        SET valid_to = ?, is_current = false
        WHERE d.is_current
          AND NOT EXISTS (SELECT 1 FROM stg s WHERE s.moh_key = d.moh_key AND s.row_hash = d.row_hash)
        RETURNING region_sk
        """,
        [as_of],
    ).fetchall()

    # insert snapshot rows with no identical current row (new areas and new versions)
    inserted = con.execute(
        """
        INSERT INTO gold.dim_region
        SELECT md5(s.moh_key || '|' || CAST(? AS VARCHAR)), s.moh_key, s.moh_area, s.district,
               s.parent_moh_area, s.boundary_note, s.row_hash, ?, DATE '9999-12-31', true
        FROM stg s
        WHERE NOT EXISTS (
            SELECT 1 FROM gold.dim_region d
            WHERE d.is_current AND d.moh_key = s.moh_key AND d.row_hash = s.row_hash
        )
        RETURNING region_sk
        """,
        [as_of, as_of],
    ).fetchall()

    counts = {"expired": len(expired), "inserted": len(inserted)}
    logger.info("Snapshot %s: %s", as_of, counts)
    return counts


def observed_snapshots(obs: pd.DataFrame, parents: pd.DataFrame | None = None) -> list[tuple[date, pd.DataFrame]]:
    """Cumulative weekly snapshots from observations (week_start, moh_area, district).

    Every area seen up to a week stays in its snapshot; its district changes only after
    CONFIRM_WEEKS consecutive reports under the new district (one-offs are logged)."""
    obs = obs.copy()
    obs["moh_key"] = obs["moh_area"].map(moh_key)
    obs["week_start"] = pd.to_datetime(obs["week_start"]).dt.date
    display = {k: Counter(g).most_common(1)[0][0] for k, g in obs.groupby("moh_key")["moh_area"]}
    parent = (
        {}
        if parents is None
        else {moh_key(a): p for a, p in zip(parents["moh_area"], parents["parent_moh_area"], strict=True)}
    )
    weeks = sorted(obs["week_start"].unique())
    printed = obs.groupby(["moh_key", "week_start"])["district"].first()
    state: dict[str, dict] = {}  # moh_key -> {district, first_seen, pending: (district, count)}
    out = []
    for w in weeks:
        for key_, dist in printed.xs(w, level="week_start").items():
            key = str(key_)
            st = state.get(key)
            if st is None:
                state[key] = {"district": dist, "first_seen": w, "pending": None}
                continue
            if dist == st["district"]:
                st["pending"] = None
                continue
            seen = st["pending"][1] + 1 if st["pending"] and st["pending"][0] == dist else 1
            if seen >= CONFIRM_WEEKS:
                logger.info("%s moves %s -> %s (confirmed in %d reports)", key, st["district"], dist, seen)
                st["district"], st["pending"] = dist, None
            else:
                st["pending"] = (dist, seen)
                logger.warning(
                    "%s printed under %s in week %s (normally %s) - not applied unless repeated",
                    display[key],
                    dist,
                    w,
                    st["district"],
                )
        out.append(
            (
                w,
                pd.DataFrame(
                    [
                        {
                            "moh_area": display[k],
                            "district": s["district"],
                            "parent_moh_area": parent.get(k),
                            "boundary_note": f"first reported by NDCU in the week of {s['first_seen']}",
                        }
                        for k, s in sorted(state.items())
                    ]
                ),
            )
        )
    return out


def sync(con: duckdb.DuckDBPyConnection, obs: pd.DataFrame, parents: pd.DataFrame | None = None) -> dict:
    """Bring gold.dim_region up to date with the observations; returns a summary of the run."""
    ensure_table(con)
    con.execute(WEEKS_DDL)
    snaps = observed_snapshots(obs, parents)
    done = {r[0] for r in con.execute("SELECT week_start FROM gold.dim_region_weeks").fetchall()}
    has_rows = (con.execute("SELECT count(*) FROM gold.dim_region").fetchone() or (0,))[0] > 0
    last = max(done) if done else None
    late = [w for w, _ in snaps if last is not None and w < last and w not in done]

    rebuilt = bool(late) or (has_rows and not done)  # late report, or rows without a week log
    if rebuilt:
        if late:
            logger.warning(
                "Late NDCU report(s) for already-passed week(s) %s - rebuilding dim_region from silver",
                ", ".join(str(w) for w in late),
            )
        con.execute("DELETE FROM gold.dim_region")
        con.execute("DELETE FROM gold.dim_region_weeks")
        done, last = set(), None

    applied = 0
    for as_of, snap in snaps:
        if last is not None and as_of <= last:
            continue
        apply_snapshot(con, snap, as_of)
        con.execute("INSERT OR IGNORE INTO gold.dim_region_weeks VALUES (?)", [as_of])
        applied += 1
    return {"applied": applied, "rebuilt": rebuilt, "late_weeks": late}


def main() -> None:
    setup_logging()
    with duckdb.connect(str(DB_PATH)) as con:
        ensure_table(con)
        try:
            obs = con.execute("SELECT week_start, moh_area, district FROM ndcu_moh_weekly_cases").df()
        except duckdb.CatalogException:
            obs = pd.DataFrame()
        if obs.empty:
            logger.info("No MOH observations yet (python -m src.transform.ndcu_moh_parse) - dim_region unchanged")
            return
        parents = pd.read_csv(PARENTS_CSV) if PARENTS_CSV.exists() else None
        result = sync(con, obs, parents)
        row = con.execute("SELECT count(*) FILTER (WHERE is_current), count(*) FROM gold.dim_region").fetchone()
        logger.info(
            "dim_region: %d weekly snapshots applied%s; %s current MOH areas, %s versions in total",
            result["applied"],
            " (full rebuild)" if result["rebuilt"] else "",
            row[0] if row else 0,
            row[1] if row else 0,
        )


if __name__ == "__main__":
    main()
