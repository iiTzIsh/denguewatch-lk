"""
NDCU (National Dengue Control Unit) weekly update PDFs -> bronze.

Discovers PDF links on the site (no URL guessing - file names are inconsistent: 'Week-31-1.pdf',
lower-case 'weekly-dengue-update-...'), downloads only NEW ones. One polite request per page.

The archive (/weekly-report/) is PAGINATED and not strictly by week: reports uploaded late (e.g. 2026
weeks 18 and 20, uploaded in August) appear on page 2 next to weeks 1-15. So every archive page is
followed (/weekly-report/page/N/), up to MAX_PAGES.

Run:  python -m src.extract.ndcu
Out:  data/bronze/ndcu/weekly/<original file name>.pdf
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
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
PAGE_RE = re.compile(r"/weekly-report/page/(\d+)/?$")
MAX_PAGES = 30          # safety cap: never crawl forever if the site's paging breaks
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


def extract_page_links(html: str, base_url: str = BASE_URL) -> list[str]:
    """Archive pagination links (/weekly-report/page/N/) on a page, normalised with a trailing slash."""
    soup = BeautifulSoup(html, "html.parser")
    pages: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a["href"]).strip()).split("#")[0].split("?")[0]
        if PAGE_RE.search(href):
            href = href.rstrip("/") + "/"
            if href not in pages:
                pages.append(href)
    return pages


def crawl_listing(fetch: Callable[[str], str | None], start_pages: list[str] = LISTING_PAGES,
                  max_pages: int = MAX_PAGES) -> list[str]:
    """Visit the start pages and every archive page they link to; return all weekly PDF links.
    `fetch(url) -> html | None` does the HTTP (None = page failed), so this is testable without a network."""
    queue: list[str] = list(start_pages)
    seen: set[str] = set()
    links: list[str] = []
    while queue and len(seen) < max_pages:
        page = queue.pop(0)
        if page in seen:
            continue
        seen.add(page)
        html = fetch(page)
        if html is None:
            continue
        for url in extract_weekly_links(html):
            if url not in links:
                links.append(url)
        queue += [p for p in extract_page_links(html) if p not in seen and p not in queue]
    if queue:
        logger.warning("Stopped after %d listing pages (MAX_PAGES); %d not visited", len(seen), len(queue))
    logger.info("Read %d listing pages", len(seen))
    return links


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

    def fetch(page: str) -> str | None:
        try:
            resp = session.get(page, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logger.error("Could not read %s: %s", page, exc)
            return None
        finally:
            time.sleep(PAUSE_S)

    links = crawl_listing(fetch)
    if not links:
        logger.error("No weekly PDF links found - site down or layout changed")
        raise SystemExit(1)
    new = download_new(session, links)
    logger.info("Weekly PDFs listed: %d, newly downloaded: %d", len(links), len(new))


if __name__ == "__main__":
    main()
