"""
Day 6: download ONE WER PDF and pull the dengue table into a DataFrame.

Run (pick a URL from data/bronze/wer/pdf_links.csv, or a PDF you downloaded by hand):
    python -m src.extract.wer_pdf --url "<pdf url>"
    python -m src.extract.wer_pdf --pdf "data/bronze/wer/pdfs/some_week.pdf"

Step 1 (explore): prints + saves every table on pages mentioning "Dengue".
Step 2 (your task): look at the CSVs, then fill in clean_dengue_table().
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
import pdfplumber
import requests

from src.config import DATA_DIR, WER_BRONZE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

PDF_DIR = WER_BRONZE_DIR / "pdfs"
EXPLORE_DIR = DATA_DIR / "explore" / "wer_tables"
HEADERS = {"User-Agent": "DengueWatchLK/0.1 (student portfolio project)"}


def download_pdf(url: str, dest_dir: Path = PDF_DIR) -> Path:
    """Download once; skip if already in bronze (idempotent)."""
    dest = dest_dir / url.rstrip("/").split("/")[-1]
    if dest.exists():
        logger.info("Already downloaded: %s", dest)
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise ValueError(f"Not a PDF: {url}")
    dest.write_bytes(resp.content)
    logger.info("Saved %s (%.0f KB)", dest, len(resp.content) / 1024)
    return dest


def pages_with_keyword(pdf_path: Path, keyword: str = "dengue") -> list[int]:
    """0-based page numbers whose text contains the keyword."""
    hits = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if keyword in (page.extract_text() or "").lower():
                hits.append(i)
    logger.info("'%s' found on pages %s (of %s)", keyword, [p + 1 for p in hits], pdf_path.name)
    return hits


def extract_tables(pdf_path: Path, page_numbers: list[int]) -> list[pd.DataFrame]:
    """Raw tables (no header cleaning yet) from the given pages."""
    tables: list[pd.DataFrame] = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in page_numbers:
            for t_idx, raw in enumerate(pdf.pages[p].extract_tables()):
                df = pd.DataFrame(raw)
                df.attrs["source"] = f"page{p + 1}_table{t_idx + 1}"
                tables.append(df)
                logger.info("Page %d table %d: %d rows x %d cols", p + 1, t_idx + 1, *df.shape)
    return tables


def clean_dengue_table(raw: pd.DataFrame) -> pd.DataFrame:
    """
    TODO (Day 6 task) - after looking at the explore CSVs:
      1. Find the header row(s) and the column that holds dengue cases for the week.
      2. Keep: region name + dengue cases.
      3. Drop total / blank rows; convert cases to int.
    Return columns: region, dengue_cases
    """
    raise NotImplementedError("Look at data/explore/wer_tables/*.csv first, then write this.")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url")
    group.add_argument("--pdf")
    args = parser.parse_args()

    setup_logging()
    pdf_path = download_pdf(args.url) if args.url else Path(args.pdf)
    tables = extract_tables(pdf_path, pages_with_keyword(pdf_path))

    EXPLORE_DIR.mkdir(parents=True, exist_ok=True)
    for df in tables:
        out = EXPLORE_DIR / f"{pdf_path.stem}_{df.attrs['source']}.csv"
        df.to_csv(out, index=False, header=False)
        print(f"\n=== {df.attrs['source']} ({df.shape[0]}x{df.shape[1]}) -> {out}")
        print(df.head(8).to_string())


if __name__ == "__main__":
    main()
