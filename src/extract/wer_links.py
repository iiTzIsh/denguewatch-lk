"""List WER PDF links from the Epidemiology Unit page into data/bronze/wer/pdf_links.csv.

Run:  python -m src.extract.wer_links [--refresh]    (--refresh ignores today's cached page)
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import WER_BRONZE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

BASE_URL = "https://www.epid.gov.lk"
WER_PAGE = f"{BASE_URL}/weekly-epidemiological-report"
BRONZE_DIR = WER_BRONZE_DIR
USER_AGENT = "DengueWatchLK/1.0 (+https://github.com/iiTzIsh/denguewatch-lk)"

# Listing text looks like: "Week 18 2024.04.27 - 2024.05.03 - The Commercial Dete..."
WEEK_RE = re.compile(r"Week\s*(\d{1,2})", re.IGNORECASE)
DATES_RE = re.compile(r"(\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})")


def make_session() -> requests.Session:
    """Return a session that retries GETs on 5xx responses."""
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504], allowed_methods=["GET"])
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def allowed_by_robots(url: str) -> bool:
    """Check robots.txt; if it cannot be read, allow the single request."""
    rp = RobotFileParser(urljoin(BASE_URL, "/robots.txt"))
    try:
        rp.read()
    except Exception as exc:  # noqa: BLE001 - courtesy check only
        logger.warning("Could not read robots.txt (%s) - proceeding with 1 request only", exc)
        return True
    ok = rp.can_fetch(USER_AGENT, url)
    logger.info("robots.txt allows %s: %s", url, ok)
    return ok


def get_page_cached(session: requests.Session, url: str, cache_file: Path, refresh: bool = False) -> str:
    """Download the page at most once per cache file; later runs read it from disk."""
    if cache_file.exists() and not refresh:
        logger.info("Cache hit: %s", cache_file)
        return cache_file.read_text(encoding="utf-8")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    logger.info("Downloaded %s (%d bytes) -> %s", url, len(resp.text), cache_file)
    return resp.text


def parse_listing_text(text: str) -> dict[str, object]:
    """Parse week number and date range from listing text; missing parts are None."""
    week = WEEK_RE.search(text)
    dates = DATES_RE.search(text)
    out: dict[str, object] = {"week": None, "start_date": None, "end_date": None, "epi_year": None}
    wk = int(week.group(1)) if week else None
    out["week"] = wk
    if dates:
        start, end = (date.fromisoformat(d.replace(".", "-")) for d in dates.groups())
        out["start_date"], out["end_date"] = start, end
        # Epi year = end date's year (week 1 of 2024 starts 2023-12-30), except
        # a late week ending in January still belongs to the previous year.
        year = end.year
        if wk is not None and wk >= 50 and end.month == 1:
            year -= 1
        out["epi_year"] = year
    return out


def extract_pdf_links(html: str, base_url: str = BASE_URL) -> pd.DataFrame:
    """Return every .pdf link with week and dates parsed from the surrounding text."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if ".pdf" not in href.lower():
            continue
        text = a.get_text(" ", strip=True)
        if not WEEK_RE.search(text) and a.parent is not None:  # info may sit beside the link
            text = a.parent.get_text(" ", strip=True)
        rows.append({"text": text, "url": urljoin(base_url, href), **parse_listing_text(text)})
    cols = ["text", "url", "week", "start_date", "end_date", "epi_year"]
    return pd.DataFrame(rows, columns=cols).drop_duplicates("url").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="ignore today's cache")
    args = parser.parse_args()

    setup_logging()
    if not allowed_by_robots(WER_PAGE):
        raise SystemExit("robots.txt disallows this page - stop and check manually.")

    session = make_session()
    try:
        html = get_page_cached(session, WER_PAGE, BRONZE_DIR / f"index_{date.today():%Y%m%d}.html", args.refresh)
    except requests.RequestException as exc:
        logger.error("Could not download %s: %s", WER_PAGE, exc)
        raise SystemExit(1) from exc
    links = extract_pdf_links(html)
    out = BRONZE_DIR / "pdf_links.csv"
    links.to_csv(out, index=False)
    logger.info("Found %d PDF links -> %s", len(links), out)

    if links.empty:
        logger.warning("0 PDF links - page may load its list with JavaScript. Check browser F12 > Network.")
        return
    print(links[["week", "start_date", "end_date", "epi_year", "url"]].head(10).to_string())
    print("\nPDFs per year:\n", links.groupby("epi_year", dropna=False).size().to_string())
    print(f"\nUnparsed rows (no week/date found): {links['week'].isna().sum()}")


if __name__ == "__main__":
    main()
