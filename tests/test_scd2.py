"""SCD Type 2 region dimension: merge mechanics, point-in-time lookup and snapshots built from observations."""

from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd
import pytest

from src.transform.scd2 import apply_snapshot, ensure_table, observed_snapshots, sync

COLS = ["moh_area", "district", "parent_moh_area", "boundary_note"]
D1, D2 = date(2025, 1, 1), date(2026, 1, 1)
# synthetic split: Kesbewa is carved out of Piliyandala between D1 and D2
SNAPS = {
    D1: pd.DataFrame(
        [("Maharagama", "colombo", None, None), ("Piliyandala", "colombo", None, "includes Kesbewa")], columns=COLS
    ),
    D2: pd.DataFrame(
        [
            ("Maharagama", "colombo", None, None),
            ("Piliyandala", "colombo", None, "Kesbewa split off"),
            ("Kesbewa", "colombo", "Piliyandala", "split from Piliyandala"),
        ],
        columns=COLS,
    ),
}


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
    assert con.execute(q, [date(2025, 6, 15)] * 2).fetchone()[0] == 2  # before split
    assert con.execute(q, [date(2026, 6, 15)] * 2).fetchone()[0] == 3  # after split


# ---------------- observed-data snapshots ----------------
def obs(rows):
    return pd.DataFrame(rows, columns=["week_start", "moh_area", "district"])


W = [date(2026, 6, 1), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22)]


def test_new_area_appears_from_its_first_week(con):
    snaps = observed_snapshots(
        obs([(W[0], "Piliyandala", "colombo"), (W[1], "Piliyandala", "colombo"), (W[1], "Kesbewa", "colombo")]),
        pd.DataFrame({"moh_area": ["Kesbewa"], "parent_moh_area": ["Piliyandala"]}),
    )
    for as_of, snap in snaps:
        apply_snapshot(con, snap, as_of)
    rows = con.execute(
        "SELECT moh_key, valid_from, parent_moh_area, is_current FROM gold.dim_region ORDER BY moh_key"
    ).fetchall()
    assert rows == [("kesbewa", W[1], "Piliyandala", True), ("piliyandala", W[0], None, True)]


def test_area_off_the_high_risk_list_stays_current(con):
    for as_of, snap in observed_snapshots(obs([(W[0], "Hanwella", "colombo"), (W[2], "Kesbewa", "colombo")])):
        apply_snapshot(con, snap, as_of)
    assert con.execute("SELECT is_current FROM gold.dim_region WHERE moh_key = 'hanwella'").fetchall() == [(True,)]


def test_one_off_district_misprint_is_not_applied(con):
    # two reports in a row are not enough (a heading misread can span W19/W20)
    rows = [
        (W[0], "Katuwana", "hambantota"),
        (W[1], "Katuwana", "matara"),
        (W[2], "Katuwana", "matara"),
        (W[3], "Katuwana", "hambantota"),
    ]
    for as_of, snap in observed_snapshots(obs(rows)):
        apply_snapshot(con, snap, as_of)
    assert con.execute("SELECT district FROM gold.dim_region").fetchall() == [("hambantota",)]  # one version


def test_confirmed_district_change_creates_a_version(con):
    rows = [(W[0], "X", "matara"), (W[1], "X", "galle"), (W[2], "X", "galle"), (W[3], "X", "galle")]
    for as_of, snap in observed_snapshots(obs(rows)):
        apply_snapshot(con, snap, as_of)
    hist = con.execute("SELECT district, valid_from, valid_to FROM gold.dim_region ORDER BY valid_from").fetchall()
    assert hist == [("matara", W[0], W[3]), ("galle", W[3], date(9999, 12, 31))]  # applied on the 3rd report


def test_spelling_variants_are_one_area(con):
    rows = [(W[0], "Bope Poddala", "galle"), (W[1], "Bope-Poddala", "galle"), (W[2], "BopePoddala", "galle")]
    for as_of, snap in observed_snapshots(obs(rows)):
        apply_snapshot(con, snap, as_of)
    assert con.execute("SELECT count(*) FROM gold.dim_region").fetchone()[0] == 1


def test_late_report_for_an_old_week_rebuilds_history():
    """NDCU uploaded 2026 W18/W20 months late: an area first printed in such a week must start there."""
    c = duckdb.connect()
    w = [date(2026, 4, 13), date(2026, 4, 27), date(2026, 5, 11)]
    first = obs([(w[0], "Piliyandala", "colombo"), (w[2], "Piliyandala", "colombo"), (w[2], "Kesbewa", "colombo")])
    assert sync(c, first) == {"applied": 2, "rebuilt": False, "late_weeks": []}
    assert sync(c, first)["applied"] == 0  # nothing new: no-op

    late = pd.concat([first, obs([(w[1], "Kesbewa", "colombo")])])  # the late W18 report arrives
    r = sync(c, late)
    assert r["rebuilt"] and r["late_weeks"] == [w[1]] and r["applied"] == 3
    assert c.execute("SELECT valid_from FROM gold.dim_region WHERE moh_area = 'Kesbewa'").fetchall() == [(w[1],)]
    assert c.execute("SELECT count(*) FROM gold.dim_region_weeks").fetchone() == (3,)


def test_table_from_before_the_week_log_is_rebuilt_once():
    c = duckdb.connect()
    ensure_table(c)
    apply_snapshot(c, SNAPS[D1], D1)  # dim_region exists, but no gold.dim_region_weeks yet
    r = sync(c, obs([(date(2026, 4, 13), "Piliyandala", "colombo")]))
    assert r["rebuilt"] and r["applied"] == 1
    assert sync(c, obs([(date(2026, 4, 13), "Piliyandala", "colombo")]))["rebuilt"] is False
