"""Export the API responses the dashboard needs as static JSON files (for the Vercel deployment).

The hosted dashboard has no API or warehouse behind it: it reads these files instead. Each file is the
exact response of the matching FastAPI endpoint, so the hosted and the Docker dashboard show the same
numbers. A 404 from the API (for example a week without an MOH table) writes no file, and the static
host returns 404 for it, which the dashboard already handles.

Run after the weekly pipeline, then commit and push `web/public/data/`:

    python -m src.export_static
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient  # needs httpx2 (requirements-dev.txt)

from src.api.main import app
from src.config import PROJECT_ROOT
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

OUT_DIR = PROJECT_ROOT / "web" / "public" / "data"
RAIN_LEAD_DAYS = 7 * 6  # the district rain chart starts 6 weeks before the first case week (DistrictSection.tsx)


def district_slug(name: str) -> str:
    """File-name-safe district key; web/src/api.ts uses the same rule."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Exporter:
    def __init__(self, client: TestClient, out_dir: Path) -> None:
        self.client = client
        self.out_dir = out_dir
        self.written = 0
        self.missing: list[str] = []

    def fetch(self, path: str) -> Any:
        r = self.client.get(path)
        if r.status_code == 404:
            self.missing.append(path)
            return None
        r.raise_for_status()
        return r.json()

    def save(self, path: str, rel: str) -> Any:
        body = self.fetch(path)
        if body is not None:
            target = self.out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
            self.written += 1
        return body


def export(out_dir: Path = OUT_DIR, client: TestClient | None = None) -> dict[str, int]:
    client = client or TestClient(app)
    if out_dir.exists():
        shutil.rmtree(out_dir)  # no stale weeks or districts left behind
    out_dir.mkdir(parents=True)
    ex = Exporter(client, out_dir)

    health = ex.save("/health", "health.json")
    if health is None:
        raise RuntimeError("API /health failed - is the warehouse built?")
    weeks: list[str] = ex.save("/weeks", "weeks.json") or []
    ex.save("/national/trend", "national.json")
    ex.save("/forecast", "forecast.json")
    ex.save("/model/health", "model-health.json")
    for h in (2, 4):
        ex.save(f"/model/forecast-vs-actual?horizon={h}", f"accuracy-{h}.json")

    districts: set[str] = set()
    for week in weeks:
        hot = ex.save(f"/hotspots?top=25&week={week}", f"hotspots/{week}.json")
        ex.save(f"/moh/hotspots?top=200&week={week}", f"moh/{week}.json")
        if hot:
            districts.update(d["district"] for d in hot["districts"])

    for d in sorted(districts):
        slug = district_slug(d)
        trend = ex.save(f"/districts/{d}/trend", f"districts/{slug}/trend.json")
        if trend:
            since = date.fromisoformat(trend[0]["week_start"]) - timedelta(days=RAIN_LEAD_DAYS)
            ex.save(f"/districts/{d}/rain?since={since.isoformat()}", f"districts/{slug}/rain.json")

    geo = client.get("/geo/districts")
    geo.raise_for_status()
    (out_dir / "districts.geojson").write_bytes(geo.content)
    ex.written += 1

    logger.info(
        "Exported %d files to %s (%d weeks, %d districts, data to %s)",
        ex.written,
        out_dir,
        len(weeks),
        len(districts),
        health["dengue_data_until"],
    )
    if ex.missing:
        logger.info("No data (404) for %d request(s), e.g. %s", len(ex.missing), ex.missing[0])
    return {"files": ex.written, "weeks": len(weeks), "districts": len(districts)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output folder (default: web/public/data)")
    args = parser.parse_args()
    setup_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request otherwise
    export(args.out)


if __name__ == "__main__":
    main()
