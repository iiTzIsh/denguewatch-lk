"""Page-2 MOH table parser on 3 REAL NDCU PDFs covering the different layouts seen in 2026."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.transform import ndcu_moh_parse as m

FIX = Path(__file__).parent / "fixtures"


def parse(name):
    return m.parse_pdf(FIX / name).set_index("moh_area")


def test_week23_values_match_the_pdf():
    df = parse("weekly-dengue-update-2026-week-23.pdf")
    assert len(df) == 89 and set(df["iso_week"]) == {23}
    for area, prev, this in [("Kesbewa", 19, 16), ("Piliyandala", 23, 33), ("Maharagama", 71, 121),
                             ("Kelaniya", 56, 86)]:
        assert (df.loc[area, "cases_prev_week"], df.loc[area, "cases_this_week"]) == (prev, this)
    # these two rows come out INTERLEAVED in the PDF's text layer ("G Ha o n th w a e tu ll w a a ...")
    assert (df.loc["Gothatuwa", "cases_prev_week"], df.loc["Gothatuwa", "cases_this_week"]) == (51, 46)
    assert (df.loc["Hanwella", "cases_prev_week"], df.loc["Hanwella", "cases_this_week"]) == (41, 39)


def test_week27_split_header_layout():
    df = parse("Weekly-Dengue-Update-2026-Week-27.pdf")          # header printed as "Week 27" / "26"
    assert len(df) == 175 and df["district"].nunique() == 20
    assert df.loc["Battaramulla", "cases_prev_week"] == 56 and df.loc["Battaramulla", "cases_this_week"] == 84


def test_week37_larger_font_layout():
    df = parse("Weekly-Dengue-Update-2026-Week-37.pdf")
    assert len(df) == 34
    assert (df.loc["Dehiwala", "cases_prev_week"], df.loc["Dehiwala", "cases_this_week"]) == (4, 10)


@pytest.mark.parametrize(("parts", "expected"), [
    (["Bope", "Poddala"], "Bope Poddala"),
    (["B", "o", "p", "e", "P", "o", "d", "d", "a", "l", "a"], "BopePoddala"),     # letter-spaced in some weeks
])
def test_clean_name(parts, expected):
    assert m.clean_name(parts) == expected


def test_keys_ignore_spelling_and_spacing():
    assert m.moh_key("Bope Poddala") == m.moh_key("Bope-Poddala") == m.moh_key("BopePoddala") == "bopepoddala"


def test_digits_only_strips_stray_bracket():
    assert m.digits_only("18]") == "18" and m.digits_only("Week") == ""


def test_header_week_mismatch_rejected():
    with pytest.raises(m.MOHParseError, match="header weeks"):
        m.parse_rows([("Week", [20, 21]), ("Colombo District", []), ("Kesbewa", [1, 2])], issue_week=23)


def test_row_before_district_rejected():
    with pytest.raises(m.MOHParseError, match="before any district"):
        m.parse_rows([("Week", [22, 23]), ("Kesbewa", [1, 2])], issue_week=23)


def test_quarantine(tmp_path):
    src, out, bad = tmp_path / "src", tmp_path / "out", tmp_path / "bad"
    src.mkdir()
    (src / "broken.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
    with pytest.raises(Exception):  # noqa: B017 - unreadable PDF is not a parse error but must not be loaded
        m.main(src, out, bad)
    assert not list(out.glob("*.csv"))


# ---- early-2026 layouts (weeks 1-15) and heading quirks found when the archive's page 2 was added ----
HDR = ("Week", [4, 5])


def districts_of(rows, week=5):
    recs, _ = m.parse_rows([HDR if week == 5 else ("Week", [week - 1 if week > 1 else 52, week]), *rows], week)
    return {r["moh_area"]: r["district"] for r in recs}


def test_heading_typos_and_two_line_headings():
    rows = [("SOUTHERN PROVINCE", []), ("Matara District", []), ("Devinuwara", [25, 30]),
            ("Hambantota", []), ("Distrcit", []),            # W02: split over two lines AND misspelt
            ("Beliatta", [16, 10])]
    assert districts_of(rows) == {"Devinuwara": "matara", "Beliatta": "hambantota"}


@pytest.mark.parametrize("heading", ["Hambantota", "Hambanota", "Hambanthota District", "HambantotaDistrict",
                                     "Hambantota Distrcit"])
def test_heading_variants_seen_in_2026(heading):
    """bare (W19/20), misspelt bare (W08/09), misspelt (W01), glued (W24-30 style), typo suffix (W05)."""
    rows = [("Matara District", []), ("Weligama", [11, 20]), (heading, []), ("Katuwana", [4, 11])]
    assert districts_of(rows)["Katuwana"] == "hambantota"


def test_unknown_label_stops_the_file_instead_of_misfiling_rows():
    """The old parser skipped unknown labels, so the next rows silently stayed under the previous district."""
    rows = [("Matara District", []), ("Weligama", [11, 20]), ("Something Odd Here", []), ("Katuwana", [4, 11])]
    with pytest.raises(m.MOHParseError, match="unrecognised label"):
        districts_of(rows)


def test_wrapped_moh_name_and_province_word():
    rows = [("Kandy District", []), ("Gangawata", [1, 11]), ("Korale", []),        # W02: name on two lines
            ("Kalutara District", []), ("Panadura", [12, 38]), ("NIHS", []),     # capital name part
            ("SABARAGAMUWA", []), ("Ratnapura District", []), ("Balangoda", [6, 11])]   # W33: province alone
    assert districts_of(rows) == {"Gangawata Korale": "kandy", "Panadura NIHS": "kalutara",
                                  "Balangoda": "ratnapura"}


def test_blank_last_week_cell_and_week_one_header():
    recs, _ = m.parse_rows([("Week", [52, 1]), ("Gampaha District", []), ("Katana", [None, 12])], issue_week=1)
    assert (recs[0]["cases_prev_week"], recs[0]["cases_this_week"]) == (None, 12)   # W01: area new to the list


def test_spelling_variants_share_one_key():
    assert m.moh_key("Pyagala") == m.moh_key("Payagala") == "payagala"
    assert m.moh_key("Pugode(Dompe)") == m.moh_key("Pugoda (Dompe)")


def test_outputs_of_an_older_parser_version_are_redone(tmp_path):
    csv = tmp_path / "x.csv"
    csv.write_text("iso_year,moh_area\n2026,Katuwana\n")                         # made before versions existed
    assert not m.is_current(csv)
    csv.write_text(f"iso_year,moh_area,parser_version\n2026,Katuwana,{m.PARSER_VERSION}\n")
    assert m.is_current(csv)
