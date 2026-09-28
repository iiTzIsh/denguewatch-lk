"""
Day 5: list WER PDF links from the Epidemiology Unit page (ONE polite request).

Run:  python -m src.extract.wer_links
Out:  data/bronze/wer/index_<date>.html  (raw page, cached)
      data/bronze/wer/pdf_links.csv      (all .pdf links found)
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

BASE_URL = "https://www.epid.gov.lk"
WER_PAGE = f"{BASE_URL}/weekly-epidemiological-report"
BRONZE_DIR = Path("data/bronze/wer")
HEADERS = {"User-Agent": "DengueWatchLK student project (contact: your-email@example.com)"}


def allowed_by_robots(url: str) -> bool:
    """Check robots.txt before scraping. If robots.txt can't be read, log it and continue carefully."""
    rp = RobotFileParser(urljoin(BASE_URL, "/robots.txt"))
    try:
        rp.read()
    except Exception as exc:  # noqa: BLE001 - just a courtesy check
        logger.warning("Could not read robots.txt (%s) - proceeding with 1 request only", exc)
        return True
    ok = rp.can_fetch(HEADERS["User-Agent"], url)
    logger.info("robots.txt allows %s: %s", url, ok)
    return ok


def get_page_cached(url: str, cache_file: Path) -> str:
    """Download once per day; later runs read from disk (bronze = raw, never edited)."""
    if cache_file.exists():
        logger.info("Cache hit: %s", cache_file)
        return cache_file.read_text(encoding="utf-8")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    logger.info("Downloaded %s (%d bytes) -> %s", url, len(resp.text), cache_file)
    return resp.text


def extract_pdf_links(html: str, base_url: str = BASE_URL) -> pd.DataFrame:
    """Find every <a href> that points to a .pdf. We don't assume a URL pattern - we discover it."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if ".pdf" in href.lower():
            rows.append({"text": a.get_text(" ", strip=True), "url": urljoin(base_url, href)})
    return pd.DataFrame(rows, columns=["text", "url"]).drop_duplicates("url").reset_index(drop=True)


def main() -> None:
    setup_logging()
    if not allowed_by_robots(WER_PAGE):
        raise SystemExit("robots.txt disallows this page - stop and check manually.")
    html = get_page_cached(WER_PAGE, BRONZE_DIR / f"index_{date.today():%Y%m%d}.html")
    links = extract_pdf_links(html)
    out = BRONZE_DIR / "pdf_links.csv"
    links.to_csv(out, index=False)
    logger.info("Found %d PDF links -> %s", len(links), out)
    print(links.head(15).to_string())
    # Day 5 task: open pdf_links.csv, note the URL pattern + which years exist.


if __name__ == "__main__":
    main()
