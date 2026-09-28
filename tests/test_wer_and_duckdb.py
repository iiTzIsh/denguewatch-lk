"""Extra tests: link parsing on fake HTML + DuckDB load is idempotent."""
from __future__ import annotations

import duckdb
import pandas as pd

from src.extract.wer_links import extract_pdf_links
from src.load.duckdb_load import WEEKLY_SQL, load_weather


def test_extract_pdf_links_finds_only_pdfs():
    html = """
    <a href="/files/wer/2024/week1.pdf">Week 1</a>
    <a href="/about">About</a>
    <a href="https://x.lk/a.PDF">Week 2</a>
    <a href="/files/wer/2024/week1.pdf">dup</a>
    """
    df = extract_pdf_links(html, base_url="https://www.epid.gov.lk")
    assert len(df) == 2
    assert df.loc[0, "url"] == "https://www.epid.gov.lk/files/wer/2024/week1.pdf"


def test_load_weather_is_idempotent(tmp_path):
    csv = tmp_path / "w.csv"
    pd.DataFrame({
        "date": ["2024-05-06", "2024-05-07", "2024-05-13"],
        "rainfall_mm": [10.0, 5.0, 2.0],
        "temperature_2m_mean": [28.0, 29.0, 27.0],
    }).to_csv(csv, index=False)
    con = duckdb.connect()
    load_weather(con, csv)
    assert load_weather(con, csv) == 3  # second run: still 3 rows, not 6
    weekly = con.sql(WEEKLY_SQL).df()
    assert weekly["rainfall_mm_total"].tolist() == [15.0, 2.0]
