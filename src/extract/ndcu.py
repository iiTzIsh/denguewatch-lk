"""
NDCU (National Dengue Control Unit) weekly update PDFs -> bronze.

Discovers PDF links on the site (no URL guessing - file names are inconsistent: 'Week-31-1.pdf',
lower-case 'weekly-dengue-update-...'), downloads only NEW ones. One polite request per page.

Run:  python -m src.extract.ndcu
Out:  data/bronze/ndcu/weekly/<original file name>.pdf
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.config import NDCU_BRONZE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dengue.health.gov.lk"
LISTING_PAGES = [f"{BASE_URL}/", f"{BASE_URL}/weekly-report/"]   # robots.txt allows both
USER_AGENT = "DengueWatchLK/0.1 (student portfolio project)"
WEEKLY_RE = re.compile(r"weekly-dengue-update-(\d{4})-week-(\d{1,2})", re.IGNORECASE)
PAUSE_S = 2.0


def extract_weekly_links(html: str, base_url: str = BASE_URL) -> list[str]:
    """All weekly-update PDF URLs on a page, de-duplicated, in page order."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a["href"]).strip())
        if href.lower().endswith(".pdf") and WEEKLY_RE.search(href) and href not in urls:
            urls.append(href)
    return urls


def download_new(session: requests.Session, urls: list[str], dest: Path = NDCU_BRONZE_DIR) -> list[Path]:
    """Download PDFs we don't have yet (idempotent). Returns the new files."""
    dest.mkdir(parents=True, exist_ok=True)
    new: list[Path] = []
    for url in urls:
        path = dest / url.rsplit("/", 1)[-1]
        if path.exists():
            continue
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            logger.warning("Not a PDF, skipped: %s", url)
            continue
        path.write_bytes(resp.content)
        logger.info("Downloaded %s (%.0f KB)", path.name, len(resp.content) / 1024)
        new.append(path)
        time.sleep(PAUSE_S)
    return new


def main() -> None:
    setup_logging()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    links: list[str] = []
    for page in LISTING_PAGES:
        try:
            resp = session.get(page, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Could not read %s: %s", page, exc)
            continue
        for url in extract_weekly_links(resp.text):
            if url not in links:
                links.append(url)
        time.sleep(PAUSE_S)
    if not links:
        logger.error("No weekly PDF links found - site down or layout changed")
        raise SystemExit(1)
    new = download_new(session, links)
    logger.info("Weekly PDFs listed: %d, newly downloaded: %d", len(links), len(new))


if __name__ == "__main__":
    main()
