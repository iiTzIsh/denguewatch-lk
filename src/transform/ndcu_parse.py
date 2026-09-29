"""
Parse NDCU weekly update PDFs (bronze) -> one clean CSV per week (data/parsed/ndcu_weekly/).

Table 1 of each PDF = cases per RDHS region (25 districts, Ampara split into Ampara + Kalmunai = 26 rows).
We read the PDF TEXT layer (the table layer splits some rows), then VALIDATE:
  - all 26 regions found
  - our sums == the 'Total' row printed in the PDF, for the columns we USE (this week + cumulative this year).
    (The 'last year' columns don't add up even in the source PDFs, and some Total rows miss a number.)
  - week dates in the header match the ISO week (NDCU weeks run Monday -> Sunday!)
Anything that fails is moved to data/quarantine/ndcu/ - never loaded.

Run:  python -m src.transform.ndcu_parse
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pdfplumber

from src.config import NDCU_BRONZE_DIR, PARSED_DIR, QUARANTINE_DIR, REFERENCE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

OUT_DIR = PARSED_DIR / "ndcu_weekly"
BAD_DIR = QUARANTINE_DIR / "ndcu"
RDHS = pd.read_csv(REFERENCE_DIR / "rdhs.csv")

# a cell: number, number with * (revised), 'Nil' (or 'Ni': text-layer glitch)
VAL = r"(\d+\*?|Nil|Ni)"
ROW_RE = {
    str(code): re.compile(rf"\b{re.escape(str(name))}\*?\s+" + r"\s+".join([VAL] * 6) + r"(?:\s|$)")
    for code, name in zip(RDHS["rdhs"], RDHS["rdhs_name"], strict=True)
}
TOTAL_RE = re.compile(r"\bTotal\*?\s+((?:(?:\d+\*?|Nil)\s*){5,6})")   # 6 numbers, sometimes only 5
YEAR_WEEK_RE = re.compile(r"Year:\s*(\d{4}).*?Issue:\s*(\d{1,2})", re.DOTALL)
HEADER_RE = re.compile(r"Week\s+(\d{1,2})\s*\((.+?)\)")
COLUMNS = [
    "cases_prev_year_prev_week", "cases_prev_year_this_week",
    "cases_prev_week", "cases_this_week",
    "cum_prev_year", "cum_this_year",
]


class NDCUParseError(Exception):
    pass


def to_int(cell: str) -> int:
    return 0 if cell in ("Nil", "Ni") else int(cell.rstrip("*"))


def parse_text(text: str) -> pd.DataFrame:
    """Page-1 text -> DataFrame (26 rows). Raises NDCUParseError if anything doesn't add up."""
    m = YEAR_WEEK_RE.search(text)
    if not m:
        raise NDCUParseError("Year/Issue not found")
    year, week = int(m.group(1)), int(m.group(2))
    week_start = date.fromisocalendar(year, week, 1)          # Monday
    week_end = week_start + timedelta(days=6)                  # Sunday

    header = HEADER_RE.search(text)
    if not header or int(header.group(1)) != week:
        raise NDCUParseError("Header week missing or different from Issue number")
    days = re.findall(r"\b(\d{1,2})(?!\d)", re.sub(r"\d{4}", "", header.group(2)))  # drop years, keep day numbers
    end_day = days
    if not end_day or int(end_day[-1]) != week_end.day:        # e.g. '07th – 13th September 2026' -> 13
        raise NDCUParseError(f"Header dates '{header.group(2)}' don't match ISO week {year}-W{week:02d}")

    rows = []
    for rdhs, rx in ROW_RE.items():
        found = rx.search(text)
        if not found:
            raise NDCUParseError(f"Region not found: {rdhs}")
        cells = found.groups()
        rows.append({"rdhs": rdhs, **{c: to_int(v) for c, v in zip(COLUMNS, cells, strict=True)},
                     "has_revised_value": any(v.endswith("*") for v in cells)})
    df = pd.DataFrame(rows)

    total = TOTAL_RE.search(text)
    if not total:
        raise NDCUParseError("Total row not found")
    printed = [to_int(v) for v in total.group(1).split()]
    this_week, cum = int(df["cases_this_week"].sum()), int(df["cum_this_year"].sum())
    if len(printed) == 6:
        ok, check = printed[3] == this_week and printed[5] == cum, "full"
    else:  # one number missing from the printed Total row -> this week must still appear, cumulative is last
        ok, check = this_week in printed and printed[-1] == cum, "partial"
    if not ok:
        raise NDCUParseError(f"Sums (this week {this_week}, cumulative {cum}) don't match printed Total {printed}")
    df["total_check"] = check

    df.insert(0, "year", year)
    df.insert(1, "iso_week", week)
    df.insert(2, "week_start", week_start)
    df.insert(3, "week_end", week_end)
    return df


def parse_pdf(path: Path) -> pd.DataFrame:
    with pdfplumber.open(path) as pdf:
        text = pdf.pages[0].extract_text() or ""
    df = parse_text(text)
    df["source_file"] = path.name
    df["parsed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def main() -> None:
    setup_logging()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = bad = skipped = 0
    for pdf in sorted(NDCU_BRONZE_DIR.glob("*.pdf")):
        out = OUT_DIR / f"{pdf.stem}.csv"
        if out.exists():
            skipped += 1
            continue
        try:
            df = parse_pdf(pdf)
        except (NDCUParseError, Exception) as exc:  # noqa: BLE001 - any failure -> quarantine
            BAD_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, BAD_DIR / pdf.name)
            (BAD_DIR / f"{pdf.stem}.error.txt").write_text(str(exc), encoding="utf-8")
            logger.error("QUARANTINED %s: %s", pdf.name, exc)
            bad += 1
            continue
        df.to_csv(out, index=False)
        for stale in BAD_DIR.glob(f"{pdf.stem}.*"):   # parsed OK now -> clear an old quarantine entry
            stale.unlink()
        logger.info("Parsed %s -> %d-W%02d, %d regions, total %d",
                    pdf.name, df["year"][0], df["iso_week"][0], len(df), df["cases_this_week"].sum())
        ok += 1
    logger.info("NDCU parse done: %d parsed, %d skipped (already parsed), %d quarantined", ok, skipped, bad)
    if bad:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
