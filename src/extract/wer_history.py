"""Weekly dengue history from `srilanka_weekly_data` in the R package denguedatahub (GPL-3).

The data is extracted from the Epidemiology Unit's Weekly Epidemiological Reports; the commit is
pinned and the result validated and cross-checked against NDCU (dbt test assert_wer_vs_ndcu_2025).
Run:  python -m src.extract.wer_history     (raw .rda -> bronze, validated CSV -> data/parsed)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src.config import PARSED_DIR, REFERENCE_DIR, WER_HISTORY_BRONZE_DIR
from src.log_setup import setup_logging

logger = logging.getLogger(__name__)

REPO = "thiyangt/denguedatahub"
COMMIT = "86d8070966644ee0b4e5b937c3792d5719390b38"  # pinned 2026-06-21
RDA_URL = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/data/srilanka_weekly_data.rda"
OUT_DIR = PARSED_DIR / "wer_history"
EXPECTED_REGIONS = 26


class WERHistoryError(Exception):
    pass


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def rdhs_lookup() -> dict[str, str]:
    """Map source region spellings to rdhs codes (slug match, then reference/rdhs_aliases.csv)."""
    codes = set(pd.read_csv(REFERENCE_DIR / "rdhs.csv")["rdhs"])
    aliases = pd.read_csv(REFERENCE_DIR / "rdhs_aliases.csv")
    lookup = {c: c for c in codes}
    lookup.update({slug(a): r for a, r in zip(aliases["alias"], aliases["rdhs"], strict=True)})
    return lookup


def download(dest_dir: Path = WER_HISTORY_BRONZE_DIR) -> Path:
    path = dest_dir / f"srilanka_weekly_data_{COMMIT[:7]}.rda"
    if path.exists():
        logger.info("Already in bronze: %s", path.name)
        return path
    dest_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(RDA_URL, timeout=60)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    logger.info("Downloaded %s (%.0f KB)", path.name, len(resp.content) / 1024)
    return path


def read_rda(path: Path) -> pd.DataFrame:
    import pyreadr

    return pyreadr.read_r(str(path))["srilanka_weekly_data"]


def tidy(raw: pd.DataFrame) -> pd.DataFrame:
    """Standardise and validate; raise on bad data, warn on missing regions or irregular weeks."""
    lookup = rdhs_lookup()
    df = pd.DataFrame(
        {
            "year": raw["year"].astype(int),
            "week": raw["week"].astype(int),
            "week_start": pd.to_datetime(raw["start.date"], format="%m/%d/%Y").dt.date,
            "week_end": pd.to_datetime(raw["end.date"], format="%m/%d/%Y").dt.date,
            "rdhs": raw["district"].map(lambda n: lookup.get(slug(str(n)))),
            "cases": raw["cases"],
        }
    )
    unknown = sorted(set(raw.loc[df["rdhs"].isna(), "district"]))
    if unknown:
        raise WERHistoryError(f"Unknown region names (add to reference/rdhs_aliases.csv): {unknown}")
    if df["cases"].isna().any() or (df["cases"] < 0).any() or (df["cases"] % 1 != 0).any():
        raise WERHistoryError("cases must be whole numbers >= 0")
    df["cases"] = df["cases"].astype(int)
    if df.duplicated(["year", "week", "rdhs"]).any():
        raise WERHistoryError("duplicate year + week + region rows")

    # irregular weeks are recorded as columns, not corrected
    start = pd.to_datetime(df["week_start"])
    df["week_days"] = (pd.to_datetime(df["week_end"]) - start).dt.days + 1
    df["week_start_day"] = start.dt.day_name()
    counts = df.groupby(["year", "week"]).size().reset_index(name="n")
    for r in counts[counts["n"] != EXPECTED_REGIONS].itertuples():
        logger.warning("%d-W%02d has %d regions (expected %d)", r.year, r.week, r.n, EXPECTED_REGIONS)
    odd = df[(df["week_days"] != 7)].drop_duplicates(["year", "week"])
    for r in odd.itertuples():
        logger.warning("%d-W%02d spans %d days (%s -> %s)", r.year, r.week, r.week_days, r.week_start, r.week_end)

    df["source"] = f"denguedatahub@{COMMIT[:7]} (WER, Epidemiology Unit)"
    df["loaded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return df.sort_values(["week_start", "rdhs"]).reset_index(drop=True)


def main() -> None:
    setup_logging()
    rda = download()
    df = tidy(read_rda(rda))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"wer_weekly_{COMMIT[:7]}.csv"
    df.to_csv(out, index=False)
    by_year = df.groupby("year")["cases"].sum()
    logger.info(
        "WER history: %d rows, %d-%d, %d regions -> %s",
        len(df),
        df["year"].min(),
        df["year"].max(),
        df["rdhs"].nunique(),
        out,
    )
    logger.info("Cases per year: %s", by_year.to_dict())


if __name__ == "__main__":
    main()
