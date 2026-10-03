"""Parse NDCU page 2 ("Table 2: High risk MOH areas") into weekly MOH-level cases per PDF.

Rows are rebuilt from word x/y positions because the text order interleaves the 4 column groups.
Only high-risk areas are listed, so a missing area means "not high-risk", not zero cases.
Run: python -m src.transform.ndcu_moh_parse   (failures go to data/quarantine/ndcu_moh/)
"""

from __future__ import annotations

import difflib
import logging
import re
import shutil
from datetime import UTC, date, datetime, timedelta
from functools import cache
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
# bump when parsing rules change; CSVs from an older version are re-parsed
PARSER_VERSION = 2
HEADER_WORDS = {"Cases", "reported", "MOH", "Area", "Week"}  # count-less table header cells
CMC_LABELS = {"cmc", "cmc_colombo"}  # Colombo Municipal Council sub-heading = Colombo district
HEADING_SUFFIXES = ("district", "rdhs", "province", "prov")
PROVINCE_WORDS = {
    "WESTERN",
    "CENTRAL",
    "SOUTHERN",
    "NORTHERN",
    "NOTHERN",
    "EASTERN",
    "NORTH",
    "SABARAGAMUWA",
    "UVA",
    "PROVINCE",
    "PROV",
}
ROW_TOLERANCE = 3.0  # pt; words whose tops differ by less are on the same row


class MOHParseError(Exception):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@cache
def moh_aliases() -> dict[str, str]:
    """Spelling variant -> canonical MOH key, from reference/moh_aliases.csv."""
    path = REFERENCE_DIR / "moh_aliases.csv"
    if not path.exists():
        return {}
    a = pd.read_csv(path, dtype=str)
    return dict(zip(a["variant_key"], a["moh_key"], strict=True))


def moh_key(name: str) -> str:
    """Stable id across spacing and known spellings: 'Bope-Poddala' -> 'bopepoddala'."""
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return moh_aliases().get(key, key)


def district_lookup() -> dict[str, str]:
    """District/RDHS heading slug -> district code (Kalmunai RDHS maps to Ampara)."""
    d = pd.read_csv(REFERENCE_DIR / "districts.csv")
    r = pd.read_csv(REFERENCE_DIR / "rdhs.csv")
    a = pd.read_csv(REFERENCE_DIR / "rdhs_aliases.csv").merge(r, on="rdhs")
    out = {slug(n): c for c, n in zip(d["district"], d["district_name"], strict=True)}
    out.update({slug(n): c for n, c in zip(r["rdhs_name"], r["district"], strict=True)})
    out.update({slug(n): c for n, c in zip(a["alias"], a["district"], strict=True)})
    out["moneragala"] = "monaragala"
    out["vavuniy"] = "vavuniya"  # typo printed in 2026-W28/W29
    return out


def table_region(words: list[dict]) -> tuple[float, float]:
    """(top, bottom) of Table 2: from its title to the next 'Table' title below it."""
    title_top = None
    for i, w in enumerate(words):
        nxt = " ".join(x["text"] for x in words[i : i + 5]).lower()
        if w["text"] == "Table" and "high risk moh" in nxt:
            title_top = w["top"]
            break
    if title_top is None:
        raise MOHParseError("'Table 2: High risk MOH areas' not found")
    below = [w["top"] for w in words if w["text"] == "Table" and w["top"] > title_top + 5]
    # stop above the next title: its superscript ("01st week") sits higher than the word "Table"
    return title_top, (min(below) - 4 if below else float("inf"))


def column_starts(words: list[dict]) -> list[float]:
    """Left edge of each column group (x of each 'MOH Area' header)."""
    xs = sorted(
        {round(w["x0"]) for i, w in enumerate(words[:-1]) if w["text"] == "MOH" and words[i + 1]["text"] == "Area"}
    )
    if not 2 <= len(xs) <= 4:
        raise MOHParseError(f"expected 2-4 column groups, found {len(xs)}")
    return [float(x) for x in xs]


def week_columns(words: list[dict], starts: list[float]) -> list[tuple[float, float]]:
    """Per column group: (name_end_x, split_x), located from its two 'Week' headers."""
    edges = [s - 20 for s in starts] + [float("inf")]
    out = []
    for g in range(len(starts)):
        xs = sorted(w["x0"] for w in words if w["text"] == "Week" and edges[g] <= w["x0"] < edges[g + 1])
        if len(xs) < 2:
            raise MOHParseError(f"column group {g + 1}: 'Week' headers not found")
        out.append((xs[0] - 4, (xs[0] + xs[1]) / 2))
    return out


def rows_by_group(words: list[dict], starts: list[float]) -> list[tuple[str, list]]:
    """Words -> (name, [prev, this]) rows in reading order, assigned to columns by x position.

    Digits in the same count column are joined, so letter-spaced rows
    ("B i y a g a m a 1 3 2 2") read as Biyagama, 13, 22."""
    edges = [s - 20 for s in starts] + [float("inf")]
    cols = week_columns(words, starts)
    out: list[tuple[str, list]] = []
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
            if "Week" in texts and all(t == "Week" or NUMBER.match(t) for t in texts):  # header row
                out.append(("Week", [int(t) for t in texts if t != "Week"]))
                continue
            # counts = trailing digit tokens; everything before is the name (even "D2B-CMC")
            k = len(r)
            while k > 0 and NUMBER.match(texts[k - 1]) and r[k - 1]["x0"] >= name_end - 15:
                k -= 1
            name_parts = [w["text"] for w in r[:k]]
            prev_digits = "".join(t for w, t in zip(r[k:], texts[k:], strict=True) if w["x0"] < split)
            this_digits = "".join(t for w, t in zip(r[k:], texts[k:], strict=True) if w["x0"] >= split)
            # a blank cell (area new to the list) stays None
            nums = (
                [int(prev_digits) if prev_digits else None, int(this_digits) if this_digits else None]
                if (prev_digits or this_digits)
                else []
            )
            out.append((clean_name(name_parts), nums))
    return out


def digits_only(text: str) -> str:
    """'18]' (stray bracket in 2026-W31) -> '18'; non-numbers -> ''."""
    m = re.fullmatch(r"(\d+)[\]\).,]?", text)
    return m.group(1) if m else ""


def clean_name(parts: list[str]) -> str:
    """'B o p e P o d d a l a' (letter-spaced) -> 'BopePoddala'; normal names keep their spaces."""
    if parts and sum(len(p) <= 2 for p in parts) >= max(3, len(parts) * 0.6):
        return "".join(parts)
    return " ".join(parts).strip()


def is_suffix(word: str) -> bool:
    """Heading suffix such as 'District', 'RDHS', 'PROVINCE'; tolerates the 'Distrcit' typo."""
    w = word.lower()
    return any(
        w == s or (abs(len(w) - len(s)) <= 1 and difflib.SequenceMatcher(None, w, s).ratio() >= 0.75)
        for s in HEADING_SUFFIXES
    )


def join_split_headings(rows: list[tuple[str, list]]) -> list[tuple[str, list]]:
    """Join a count-less suffix-only row to the heading above it ('Hambantota' / 'Distrcit')."""
    out: list[tuple[str, list]] = []
    for name, nums in rows:
        if not nums and out and not out[-1][1] and len(name.split()) == 1 and is_suffix(name):
            out[-1] = (f"{out[-1][0]} {name}", [])
        else:
            out.append((name, nums))
    return out


def heading_district(name: str, districts: dict[str, str]) -> str | None:
    """'Galle District', 'G am p ah a Distrcit' -> district code; None if not a heading."""
    if slug(name) in CMC_LABELS:
        return districts["colombo"]
    if slug(name) in districts:  # bare district name, no "District" word
        return districts[slug(name)]
    if len(name.split()) == 1:  # bare and misspelt: 'Hambanota'
        close = difflib.get_close_matches(slug(name), list(districts), n=1, cutoff=0.85)
        if close:
            logger.info("District heading %r read as %s (spelling variant)", name, districts[close[0]])
            return districts[close[0]]
    name = re.sub(r"(?i)(?<=[a-z])(district|distrcit|rdhs)$", r" \1", name)  # glued: 'RatnapuraDistrict'
    parts = name.split()
    if len(parts) < 2 or not is_suffix(parts[-1]) or parts[-1].lower().startswith("prov"):
        return None
    raw = " ".join(parts[:-1])
    for key in (slug(raw), slug(raw.replace(" ", ""))):  # normal, then letter-spaced
        if key in districts:
            return districts[key]
    close = difflib.get_close_matches(slug(raw.replace(" ", "")), list(districts), n=1, cutoff=0.85)
    if close:  # 'Hambanthota', 'Rathnapura'
        logger.info("District heading %r read as %s (spelling variant)", name, districts[close[0]])
        return districts[close[0]]
    raise MOHParseError(f"unknown district heading: {name!r}")


def parse_rows(rows: list[tuple[str, list]], issue_week: int) -> tuple[list[dict], list[str]]:
    """Rows -> (MOH records, ignored label rows).

    An unknown count-less row raises: skipping it would file later rows under the wrong district."""
    districts = district_lookup()
    rows = join_split_headings(rows)
    weeks_seen: tuple[int, int] | None = None
    province = district = None
    records: list[dict] = []
    labels: list[str] = []
    header_nums: set[int] = set()
    prev_was_record = False
    for name, nums in rows:
        # header rows hold only "Week" and week numbers, possibly over two lines;
        # numbers before the first district are header too
        if name.replace("Week", "").strip() == "" or (district is None and not name):
            if district is None:
                header_nums |= {n for n in nums if n is not None}
                if len(header_nums) >= 2:
                    lo, hi = sorted(header_nums)[:2]
                    weeks_seen = (lo, hi)
            continue
        if not nums:
            if re.search(r"PROV(INCE)?$", name) or all(w in PROVINCE_WORDS for w in name.upper().split()):
                province = name.replace("PROV", "PROVINCE") if name.endswith("PROV") else name
            elif (d := heading_district(name, districts)) is not None:
                district = d
            elif set(name.split()) <= HEADER_WORDS:
                labels.append(name)
            elif records and prev_was_record and len(name.split()) == 1 and name.upper() not in PROVINCE_WORDS:
                # MOH name wrapped onto a second line ('Gangawata' / 'Korale'); province words are headings
                records[-1]["moh_area"] = f"{records[-1]['moh_area']} {name}"
                records[-1]["moh_key"] = moh_key(records[-1]["moh_area"])
                labels.append(f"(joined) {records[-1]['moh_area']}")
            else:
                raise MOHParseError(f"unrecognised label {name!r} - not a district/province heading or MOH row")
            prev_was_record = False
            continue
        prev, this = nums
        if this is None:
            raise MOHParseError(f"row {name!r} has no count for this week: {nums}")
        if district is None:
            raise MOHParseError(f"MOH row {name!r} before any district heading")
        if not all(0 <= n <= MAX_CASES for n in nums if n is not None):
            raise MOHParseError(f"implausible counts for {name!r}: {nums}")
        records.append(
            {
                "province": province,
                "district": district,
                "moh_area": name,
                "moh_key": moh_key(name),
                "cases_prev_week": prev,
                "cases_this_week": this,
            }
        )
        prev_was_record = True
    expected = {issue_week - 1 if issue_week > 1 else 52, issue_week}  # week 1 follows 52 or 53
    if not weeks_seen or (set(weeks_seen) != expected and not (issue_week == 1 and set(weeks_seen) == {53, 1})):
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
    df["parser_version"] = PARSER_VERSION
    return df


def is_current(csv: Path) -> bool:
    """True if the CSV exists and was written by the current PARSER_VERSION."""
    if not csv.exists():
        return False
    try:
        head = pd.read_csv(csv, nrows=1)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return False
    return "parser_version" in head and int(head["parser_version"].iloc[0]) == PARSER_VERSION


def main(src: Path = NDCU_BRONZE_DIR, out_dir: Path = OUT_DIR, bad_dir: Path = BAD_DIR) -> None:
    setup_logging()
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = skipped = bad = 0
    for pdf in sorted(src.glob("*.pdf")):
        out = out_dir / f"{pdf.stem}.csv"
        if is_current(out):
            skipped += 1
            continue
        try:
            df = parse_pdf(pdf)
        except MOHParseError as exc:
            bad_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, bad_dir / pdf.name)
            logger.error("QUARANTINED %s: %s", pdf.name, exc)
            out.unlink(missing_ok=True)  # drop stale output from an older parser version
            bad += 1
            continue
        df.to_csv(out, index=False)
        (bad_dir / pdf.name).unlink(missing_ok=True)  # clear an old quarantine copy
        ok += 1
        logger.info("%s: %d high-risk MOH areas, %d districts", pdf.name, len(df), df["district"].nunique())
    logger.info("NDCU MOH parse done: %d parsed, %d skipped (already parsed), %d quarantined", ok, skipped, bad)


if __name__ == "__main__":
    main()
