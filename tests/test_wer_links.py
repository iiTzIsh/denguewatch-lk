"""Tests for the WER link scraper - uses fake HTML, no network."""

from __future__ import annotations

from datetime import date

import pytest

from src.extract.wer_links import extract_pdf_links, parse_listing_text

SAMPLE_HTML = """
<ul>
  <li><a href="/storage/post/pdfs/wer_2024_18.pdf">Week 18 2024.04.27 - 2024.05.03 - The Commercial Dete...</a></li>
  <li>Week 1 2023.12.30 - 2024.01.05 - Flashback <a href="/storage/post/pdfs/wer_2024_1.pdf">Download</a></li>
  <li><a href="/about">About us</a></li>
  <li><a href="https://www.epid.gov.lk/storage/post/pdfs/wer_2024_18.pdf">duplicate</a></li>
</ul>
"""


def test_extract_finds_pdfs_and_dedupes():
    df = extract_pdf_links(SAMPLE_HTML, base_url="https://www.epid.gov.lk")
    assert len(df) == 2
    assert df.loc[0, "url"] == "https://www.epid.gov.lk/storage/post/pdfs/wer_2024_18.pdf"


def test_extract_reads_text_next_to_link():
    df = extract_pdf_links(SAMPLE_HTML, base_url="https://www.epid.gov.lk")
    assert df.loc[1, "week"] == 1  # week info was in the <li>, not inside the <a>


@pytest.mark.parametrize(
    "text, week, epi_year, start",
    [
        ("Week 18 2024.04.27 - 2024.05.03 - Title", 18, 2024, date(2024, 4, 27)),
        ("Week 1 2023.12.30 - 2024.01.05 - Flashback", 1, 2024, date(2023, 12, 30)),  # starts in old year
        ("Week 52 2023.12.23 - 2023.12.29 - GBV", 52, 2023, date(2023, 12, 23)),
        ("Week 53 2020.12.26 - 2021.01.01 - X", 53, 2020, date(2020, 12, 26)),  # spills into Jan
    ],
)
def test_parse_listing_text(text, week, epi_year, start):
    out = parse_listing_text(text)
    assert (out["week"], out["epi_year"], out["start_date"]) == (week, epi_year, start)


def test_parse_listing_text_handles_garbage():
    assert parse_listing_text("Annual report") == {"week": None, "start_date": None, "end_date": None, "epi_year": None}
