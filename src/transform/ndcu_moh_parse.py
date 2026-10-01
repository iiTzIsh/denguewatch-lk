"""
NDCU weekly update, page 2: "Table 2: High risk MOH areas" -> MOH-level weekly cases (silver).

Why word POSITIONS, not plain text: the table has 4 side-by-side column groups. The PDF's text order
interleaves close rows ("G Ha o n th w a e tu ll w a a" = Gothatuwa + Hanwella), so we read each word's
x/y position, split the page into the 4 groups using the "MOH Area" headers, and rebuild rows by y.

The table lists only HIGH-RISK MOH areas (not all ~350), so a MOH area missing in a week means
"not high-risk that week", not "zero cases".

Checks (fail -> the PDF goes to data/quarantine/ndcu_moh/, nothing is written):
  - table title found; 2-4 column groups found from the headers
  - header weeks are (W-1, W) for the report's issue week W (from page 1)
  - every MOH row sits under a known district (25 districts, incl. Kalmunai RDHS -> Ampara)
  - no MOH area twice in the same week; counts are whole numbers 0..5000
Cross-check in dbt (assert_ndcu_moh_within_district_total): MOH cases of a district <= that district's
page-1 total for the same week.

Run:  python -m src.transform.ndcu_moh_parse
Out:  data/parsed/ndcu_moh/<pdf name>.csv
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pdfplumber

from src.config import NDCU_BRONZE_DIR, PARSED_DIR, QUARANTINE_DIR, REFERENCE_DIR
from src.log_setup import setup_logging
from src.transform.ndcu_parse import YEAR_WEEK_RE

logger = logging.getLogger(__name__)

OUT_DIR = PARSED_DIR / "ndcu_moh"
BAD_DIR = QUARANTINE_DIR / "ndcu_moh"
NUMBER = re.compile(r"^\d+$")
MAX_CASES = 5000
ROW_TOLERANCE = 3.0          # words whose tops differ by < 3 pt are on the same row


class MOHParseError(Exception):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def moh_key(name: str) -> str:
    """Stable id across spellings/spacing: 'Bope Poddala', 'Bope-Poddala', 'BopePoddala' -> 'bopepoddala'."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def district_lookup() -> dict[str, str]:
    """District / RDHS heading spelling -> our district code (Kalmunai RDHS belongs to Ampara district)."""
    d = pd.read_csv(REFERENCE_DIR / "districts.csv")
    r = pd.read_csv(REFERENCE_DIR / "rdhs.csv")
    a = pd.read_csv(REFERENCE_DIR / "rdhs_aliases.csv").merge(r, on="rdhs")
    out = {slug(n): c for c, n in zip(d["district"], d["district_name"], strict=True)}
    out.update({slug(n): c for n, c in zip(r["rdhs_name"], r["district"], strict=True)})
    out.update({slug(n): c for n, c in zip(a["alias"], a["district"], strict=True)})
    out["moneragala"] = "monaragala"
    out["vavuniy"] = "vavuniya"                 # typo printed in the NDCU PDFs of 2026 weeks 28-29
    return out


def table_region(words: list[dict]) -> tuple[float, float]:
    """(top, bottom) of Table 2: from its title to the next 'Table' title below it."""
    title_top = None
    for i, w in enumerate(words):
        nxt = " ".join(x["text"] for x in words[i:i + 5]).lower()
        if w["text"] == "Table" and "high risk moh" in nxt:
            title_top = w["top"]
            break
    if title_top is None:
        raise MOHParseError("'Table 2: High risk MOH areas' not found")
    below = [w["top"] for w in words if w["text"] == "Table" and w["top"] > title_top + 5]
    return title_top, (min(below) if below else float("inf"))


def column_starts(words: list[dict]) -> list[float]:
    """x of each 'MOH' header that is followed by 'Area' -> left edge of each column group."""
    xs = sorted({round(w["x0"]) for i, w in enumerate(words[:-1])
                 if w["text"] == "MOH" and words[i + 1]["text"] == "Area"})
    if not 2 <= len(xs) <= 4:
        raise MOHParseError(f"expected 2-4 column groups, found {len(xs)}")
    return [float(x) for x in xs]


def week_columns(words: list[dict], starts: list[float]) -> list[tuple[float, float]]:
    """Per column group: (name_end_x, split_x). The 2 'Week' headers mark where the two count columns are."""
    edges = [s - 20 for s in starts] + [float("inf")]
    out = []
    for g in range(len(starts)):
        xs = sorted(w["x0"] for w in words if w["text"] == "Week" and edges[g] <= w["x0"] < edges[g + 1])
        if len(xs) < 2:
            raise MOHParseError(f"column group {g + 1}: 'Week' headers not found")
        out.append((xs[0] - 4, (xs[0] + xs[1]) / 2))
    return out


def rows_by_group(words: list[dict], starts: list[float]) -> list[tuple[str, list[int]]]:
    """Words -> rows (name, [numbers]), group by group, top to bottom (= the table's reading order).

    Each word is placed by its x position: left of the first 'Week' column = name; under the first / second
    'Week' column = last week / this week. Digits in the same count column are joined, so letter-spaced
    rows ("B i y a g a m a 1 3 2 2") are read correctly as Biyagama, 13, 22 - not guessed from spaces."""
    edges = [s - 20 for s in starts] + [float("inf")]
    cols = week_columns(words, starts)
    out: list[tuple[str, list[int]]] = []
    for g in range(len(starts)):
        name_end, split = cols[g]
        ws = sorted((w for w in words if edges[g] <= w["x0"] < edges[g + 1]), key=lambda w: (w["top"], w["x0"]))
        rows: list[tuple[float, list[dict]]] = []
        for w in ws:
            if rows and abs(rows[-1][0] - w["top"]) < ROW_TOLERANCE:
                rows[-1][1].append(w)
            else:
                rows.append((w["top"], [w]))
        for _, r in rows:
            r = sorted(r, key=lambda w: w["x0"])
            texts = [digits_only(w["text"]) or w["text"] for w in r]
            if "Week" in texts and all(t == "Week" or NUMBER.match(t) for t in texts):   # header row, any layout
                out.append(("Week", [int(t) for t in texts if t != "Week"]))
                continue
            # numbers = the run of digit tokens at the END of the row (left of it = the name, even "D2B-CMC")
            k = len(r)
            while k > 0 and NUMBER.match(texts[k - 1]) and r[k - 1]["x0"] >= name_end - 15:
                k -= 1
            name_parts = [w["text"] for w in r[:k]]
            prev_digits = "".join(t for w, t in zip(r[k:], texts[k:], strict=True) if w["x0"] < split)
            this_digits = "".join(t for w, t in zip(r[k:], texts[k:], strict=True) if w["x0"] >= split)
            nums = [int(d) for d in (prev_digits, this_digits) if d]
            out.append((clean_name(name_parts), nums))
    return out


def digits_only(text: str) -> str:
    """'18]' (stray bracket printed in the 2026-W31 PDF) -> '18'; anything else that isn't a number -> ''."""
    m = re.fullmatch(r"(\d+)[\]\).,]?", text)
    return m.group(1) if m else ""


def clean_name(parts: list[str]) -> str:
    """'B o p e P o d d a l a' (letter-spaced) -> 'BopePoddala'; normal names keep their spaces."""
    if parts and sum(len(p) <= 2 for p in parts) >= max(3, len(parts) * 0.6):
        return "".join(parts)
    return " ".join(parts).strip()


def parse_rows(rows: list[tuple[str, list[int]]], issue_week: int) -> tuple[list[dict], list[str]]:
    """Rows -> MOH records. Returns (records, ignored label rows)."""
    districts = district_lookup()
    weeks_seen: tuple[int, int] | None = None
    province = district = None
    records: list[dict] = []
    labels: list[str] = []
    header_nums: set[int] = set()
    for name, nums in rows:
        # header rows hold only "Week" and week numbers; layouts vary: "Week Week / 36 37", "Week 23 Week 24",
        # or split over two lines ("Week 27" / "26"). Numbers before the first district are header too.
        if name.replace("Week", "").strip() == "" or (district is None and not name):
            if district is None:
                header_nums |= set(nums)
                if len(header_nums) >= 2:
                    lo, hi = sorted(header_nums)[:2]
                    weeks_seen = (lo, hi)
            continue
        if not nums:
            if re.search(r"PROV(INCE)?$", name):
                province = name.replace("PROV", "PROVINCE") if name.endswith("PROV") else name
            elif name.endswith("District") or name.endswith("RDHS"):
                raw = re.sub(r"\s*(District|RDHS)$", "", name)
                key = slug(raw)
                if key not in districts:
                    key = slug(raw.replace(" ", ""))           # letter-spaced heading: "G am p ah a"
                if key not in districts:
                    raise MOHParseError(f"unknown district heading: {name!r}")
                district = districts[key]
            elif name not in ("Cases reported", "Cases", "reported", "MOH Area", "Week Week", "Week"):
                labels.append(name)                         # e.g. "CMC" sub-heading
            continue
        if len(nums) != 2:
            raise MOHParseError(f"row {name!r} has {len(nums)} numbers, expected 2")
        if district is None:
            raise MOHParseError(f"MOH row {name!r} before any district heading")
        if not all(0 <= n <= MAX_CASES for n in nums):
            raise MOHParseError(f"implausible counts for {name!r}: {nums}")
        records.append({"province": province, "district": district, "moh_area": name,
                        "moh_key": moh_key(name), "cases_prev_week": nums[0], "cases_this_week": nums[1]})
    if weeks_seen != (issue_week - 1, issue_week):
        raise MOHParseError(f"header weeks {weeks_seen} do not match issue week {issue_week}")
    keys = [r["moh_key"] for r in records]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise MOHParseError(f"MOH areas listed twice: {dupes}")
    if not records:
        raise MOHParseError("no MOH rows parsed")
    return records, labels


def parse_pdf(path: Path) -> pd.DataFrame:
    with pdfplumber.open(path) as pdf:
        m = YEAR_WEEK_RE.search(pdf.pages[0].extract_text() or "")
        if not m:
            raise MOHParseError("year/issue week not found on page 1")
        year, week = int(m.group(1)), int(m.group(2))
        page = pdf.pages[1]
        words = page.extract_words()
    top, bottom = table_region(words)
    region = [w for w in words if top + 5 < w["top"] < bottom]
    starts = column_starts(region)
    records, labels = parse_rows(rows_by_group(region, starts), week)
    if labels:
        logger.debug("%s: ignored labels %s", path.name, labels)
    week_start = date.fromisocalendar(year, week, 1)
    df = pd.DataFrame(records)
    df.insert(0, "iso_year", year)
    df.insert(1, "iso_week", week)
    df.insert(2, "week_start", week_start)
    df.insert(3, "week_end", week_start + timedelta(days=6))
    df["source_file"] = path.name
    df["parsed_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def main(src: Path = NDCU_BRONZE_DIR, out_dir: Path = OUT_DIR, bad_dir: Path = BAD_DIR) -> None:
    setup_logging()
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = skipped = bad = 0
    for pdf in sorted(src.glob("*.pdf")):
        out = out_dir / f"{pdf.stem}.csv"
        if out.exists():
            skipped += 1
            continue
        try:
            df = parse_pdf(pdf)
        except MOHParseError as exc:
            bad_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, bad_dir / pdf.name)
            logger.error("QUARANTINED %s: %s", pdf.name, exc)
            bad += 1
            continue
        df.to_csv(out, index=False)
        (bad_dir / pdf.name).unlink(missing_ok=True)       # fixed since last run -> clear old quarantine copy
        ok += 1
        logger.info("%s: %d high-risk MOH areas, %d districts", pdf.name, len(df), df["district"].nunique())
    logger.info("NDCU MOH parse done: %d parsed, %d skipped (already parsed), %d quarantined", ok, skipped, bad)


if __name__ == "__main__":
    main()
