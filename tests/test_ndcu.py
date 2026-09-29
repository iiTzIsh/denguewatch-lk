"""NDCU: link discovery + parser tested against a REAL weekly update PDF (week 37, 2026)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.extract.ndcu import extract_weekly_links
from src.transform.ndcu_parse import NDCUParseError, parse_pdf, parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "Weekly-Dengue-Update-2026-Week-37.pdf"


@pytest.fixture(scope="module")
def week37():
    return parse_pdf(FIXTURE)


def test_links_found_with_messy_names():
    html = """
      <a href="/wp-content/uploads/2026/09/Weekly-Dengue-Update-2026-Week-37.pdf">W37</a>
      <a href="/wp-content/uploads/2026/08/Weekly-Dengue-Update-2026-Week-31-1.pdf">W31</a>
      <a href="/wp-content/uploads/2026/06/weekly-dengue-update-2026-week-23.pdf">W23</a>
      <a href="/wp-content/uploads/2026/09/Daily-Update-2026.-09.-27.pdf">daily</a>
      <a href="/wp-content/uploads/2026/09/Weekly-Dengue-Update-2026-Week-37.pdf">dup</a>"""
    links = extract_weekly_links(html)
    assert len(links) == 3
    assert links[0].startswith("https://www.dengue.health.gov.lk/wp-content/")


def test_week_and_dates(week37):
    row = week37.iloc[0]
    assert (row.year, row.iso_week) == (2026, 37)
    assert (row.week_start, row.week_end) == (date(2026, 9, 7), date(2026, 9, 13))  # Monday -> Sunday


def test_all_26_regions_and_total(week37):
    assert len(week37) == 26
    assert week37["cases_this_week"].sum() == 1156          # printed Total row


def test_known_values(week37):
    r = week37.set_index("rdhs")
    assert r.loc["colombo", ["cases_prev_week", "cases_this_week", "cum_this_year"]].tolist() == [222, 207, 23161]
    assert r.loc["kilinochchi", "cases_prev_year_this_week"] == 0        # 'Nil' -> 0
    assert r.loc["kalutara", "cases_prev_week"] == 71                    # '71*' -> 71
    assert bool(r.loc["kalutara", "has_revised_value"]) is True
    assert r.loc["galle", "cases_this_week"] == 69                       # row the table layer split in 3
    assert r.loc["kalmunai", "cases_this_week"] == 31


def test_total_mismatch_is_rejected():
    text = FIXTURE_TEXT.replace("Total* 521 606 1152* 1156", "Total* 521 606 1152* 1999")
    with pytest.raises(NDCUParseError, match="don't match printed Total"):
        parse_text(text)


# ---- real PDFs that were quarantined on the first run ----
FIX = Path(__file__).parent / "fixtures"


def test_week27_ni_glitch_parses():
    df = parse_pdf(FIX / "Weekly-Dengue-Update-2026-Week-27.pdf")    # text layer has 'Nil Ni'
    r = df.set_index("rdhs")
    assert r.loc["vavuniya", "cases_prev_year_this_week"] == 0
    assert df["cases_this_week"].sum() == 7916 and (df["total_check"] == "full").all()


def test_week23_total_row_with_5_numbers():
    df = parse_pdf(FIX / "weekly-dengue-update-2026-week-23.pdf")    # PDF left out last week's total
    assert df["cases_this_week"].sum() == 3265 and df["cum_this_year"].sum() == 37118
    assert (df["total_check"] == "partial").all()


def test_missing_region_is_rejected():
    with pytest.raises(NDCUParseError, match="Region not found"):
        parse_text(FIXTURE_TEXT.replace("Kegalle", "Kegal1e"))


def _text() -> str:
    import pdfplumber
    with pdfplumber.open(FIXTURE) as pdf:
        return pdf.pages[0].extract_text() or ""


FIXTURE_TEXT = _text()
