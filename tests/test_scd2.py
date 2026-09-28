"""SCD Type 2 behaviour: insert, expire, idempotent, out-of-order guard, point-in-time lookup."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from src.transform.scd2 import apply_snapshot, ensure_table, snapshot_files

SNAPS = dict(snapshot_files())  # {date: path} from reference/moh_snapshots
D1, D2 = date(2025, 1, 1), date(2026, 1, 1)


@pytest.fixture
def con():
    c = duckdb.connect()
    ensure_table(c)
    return c


def test_first_snapshot_inserts_all(con):
    assert apply_snapshot(con, SNAPS[D1], D1) == {"expired": 0, "inserted": 2}


def test_split_expires_parent_and_adds_versions(con):
    apply_snapshot(con, SNAPS[D1], D1)
    # Piliyandala changed (note) -> 1 expired; new Piliyandala version + new Kesbewa -> 2 inserted
    assert apply_snapshot(con, SNAPS[D2], D2) == {"expired": 1, "inserted": 2}
    rows = con.execute(
        "SELECT valid_to, is_current FROM gold.dim_region WHERE moh_area='Piliyandala' ORDER BY valid_from"
    ).fetchall()
    assert rows == [(D2, False), (date(9999, 12, 31), True)]


def test_reapply_same_snapshot_is_idempotent(con):
    apply_snapshot(con, SNAPS[D1], D1)
    apply_snapshot(con, SNAPS[D2], D2)
    assert apply_snapshot(con, SNAPS[D2], D2) == {"expired": 0, "inserted": 0}


def test_out_of_order_snapshot_rejected(con):
    apply_snapshot(con, SNAPS[D2], D2)
    with pytest.raises(ValueError, match="out of order"):
        apply_snapshot(con, SNAPS[D1], D1)


def test_exactly_one_current_row_per_area(con):
    apply_snapshot(con, SNAPS[D1], D1)
    apply_snapshot(con, SNAPS[D2], D2)
    bad = con.execute(
        "SELECT moh_area FROM gold.dim_region GROUP BY 1 HAVING sum(CASE WHEN is_current THEN 1 ELSE 0 END) <> 1"
    ).fetchall()
    assert bad == []


def test_point_in_time_lookup(con):
    apply_snapshot(con, SNAPS[D1], D1)
    apply_snapshot(con, SNAPS[D2], D2)
    q = "SELECT count(*) FROM gold.dim_region WHERE ? >= valid_from AND ? < valid_to"
    assert con.execute(q, [date(2025, 6, 15)] * 2).fetchone()[0] == 2   # before split
    assert con.execute(q, [date(2026, 6, 15)] * 2).fetchone()[0] == 3   # after split
