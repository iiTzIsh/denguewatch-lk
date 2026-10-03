"""Parse district population from Census 2024 Table 3.2 (reference/population/CPH2024_Final_Eng.pdf).

Values are checked against totals printed in the report; on any mismatch no CSV is written.
Run:  python -m src.reference.build_population     (writes district_population_2024.csv)
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

from src.config import REFERENCE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

POP_DIR = REFERENCE_DIR / "population"
PDF_PATH = POP_DIR / "CPH2024_Final_Eng.pdf"
OUT_CSV = POP_DIR / "district_population_2024.csv"
SOURCE = (
    "Census of Population and Housing 2024 - Final Report, Department of Census and Statistics "
    "Sri Lanka (10 Apr 2026), Table 3.2"
)
CHECKS = {"total": 21_781_800, "gampaha": 2_436_142, "mullaitivu": 122_619}  # printed in the report

NUMBER = r"(\d{1,3}(?:,\d{3})+|\d{4,})"


class PopulationError(Exception):
    pass


def district_names() -> dict[str, str]:
    """Map report spellings (lower-case letters only) to district codes."""
    d = pd.read_csv(REFERENCE_DIR / "districts.csv")
    out = {re.sub(r"[^a-z]", "", n.lower()): code for code, n in zip(d["district"], d["district_name"], strict=True)}
    out["nuwaraeliya"] = "nuwara_eliya"
    out["moneragala"] = "monaragala"  # the census spells it "Moneragala"
    return out


def find_table_pages(pdf: pdfplumber.PDF) -> list[int]:
    """Return the page index with the Table 3.2 title, skipping the table-of-contents entry.

    The following page (Table 3.3, 1981-2024 history) is deliberately excluded.
    """
    title = re.compile(r"^\s*Table\s*3\.2\s*:.*District.*2024\s*$", re.MULTILINE)
    return [i for i, p in enumerate(pdf.pages) if title.search(p.extract_text() or "")]


def parse_lines(lines: list[str]) -> dict[str, int]:
    """Take the first number after each district name as its total population."""
    names = district_names()
    found: dict[str, int] = {}
    for line in lines:
        m = re.match(rf"^\s*([A-Za-z][A-Za-z .\-]+?)\s+{NUMBER}", line)
        if not m:
            continue
        key = re.sub(r"[^a-z]", "", m.group(1).lower())
        if key in names and names[key] not in found:
            found[names[key]] = int(m.group(2).replace(",", ""))
        elif key in ("srilanka", "total") and "total" not in found:
            found["total"] = int(m.group(2).replace(",", ""))
    return found


def validate(found: dict[str, int]) -> pd.DataFrame:
    names = set(district_names().values())
    missing = sorted(names - found.keys())
    if missing:
        raise PopulationError(f"districts not found in Table 3.2: {missing}")
    df = pd.DataFrame(sorted((k, v) for k, v in found.items() if k in names), columns=["district", "population"])
    total = int(df["population"].sum())
    if total != CHECKS["total"]:
        raise PopulationError(f"districts sum to {total:,}, report says {CHECKS['total']:,}")
    for d in ("gampaha", "mullaitivu"):
        got = int(df.loc[df["district"] == d, "population"].iloc[0])
        if got != CHECKS[d]:
            raise PopulationError(f"{d}: parsed {got:,}, report text says {CHECKS[d]:,}")
    if "total" in found and found["total"] != CHECKS["total"]:
        raise PopulationError(f"printed total row {found['total']:,} != {CHECKS['total']:,}")
    df["census_year"] = 2024
    df["source"] = SOURCE
    return df


def main(pdf_path: Path = PDF_PATH, out_csv: Path = OUT_CSV) -> int:
    setup_logging()
    if not pdf_path.exists():
        logger.error("Missing %s - download the census report first (see reference/population/README.md)", pdf_path)
        return 2
    with pdfplumber.open(pdf_path) as pdf:
        pages = find_table_pages(pdf)
        if not pages:
            logger.error("Table 3.2 not found in %s", pdf_path.name)
            return 1
        lines = [ln for i in pages for ln in (pdf.pages[i].extract_text() or "").splitlines()]
    try:
        df = validate(parse_lines(lines))
    except PopulationError as exc:
        logger.error("Population table rejected: %s (pages %s)", exc, [p + 1 for p in pages])
        return 1
    df.to_csv(out_csv, index=False)
    logger.info(
        "Wrote %s: %d districts, total %s (all checks passed, PDF pages %s)",
        out_csv.name,
        len(df),
        f"{df['population'].sum():,}",
        [p + 1 for p in pages],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
