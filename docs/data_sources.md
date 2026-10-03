# Data sources

## NDCU weekly dengue updates

Site: https://www.dengue.health.gov.lk/ (robots.txt allows everything except `/wp-admin/`, checked 29 Sep 2026).

- PDFs are linked from the home page and from the paginated archive `/weekly-report/` (`/weekly-report/page/N/`).
  The archive is not strictly ordered: late uploads (2026 weeks 18 and 20) appear on page 2 next to weeks 1-15,
  so `src/extract/ndcu.py` follows every archive page.
- File names are inconsistent (`Week-31-1.pdf`, lower-case `weekly-dengue-update-2026-week-23.pdf`), so links are
  discovered from the pages, never guessed.
- Weeks are ISO weeks, Monday-Sunday (2026-W37 = 7-13 Sep 2026).
- Page 1, Table 1: cases per RDHS region, 26 rows (25 districts; Ampara district is split into the Ampara and
  Kalmunai regions). Columns: previous-year week N-1 and N, this-year week N-1 and N, cumulative previous year,
  cumulative this year.
- Page 2, Table 2: high-risk MOH areas with last week's and this week's cases (see [moh_regions.md](moh_regions.md)).

Parsing (`src/transform/ndcu_parse.py`) reads the PDF text layer; the table layer splits some rows (Galle,
Kegalle). Validation: all 26 regions present, header dates match the ISO week, and the parsed week-N and
cumulative columns equal the printed `Total` row. Known quirks:

| Quirk | Handling |
|---|---|
| `Nil` printed as `Ni` (weeks 27-28) | read as 0 |
| `Total` row with 5 numbers (week 23) | validated on week N and cumulative only |
| previous-year columns don't add up to their printed totals, even in clean PDFs | not used |
| a later PDF revises last week's count (late reports, `*` marker) | stored as a restatement next to the first report |
| 2026-W01 counted over a special split (last 3 days of 2025 and first 4 of 2026) | kept as published |

The open-source scraper [lk_dengue](https://github.com/nuuuwan/lk_dengue) was used only as a reference for the
page structure and for the MOH parent-area mapping; the parsers here are independent.

## WER history (Epidemiology Unit)

The Weekly Epidemiological Report (https://www.epid.gov.lk/weekly-epidemiological-report) lists PDFs from 2006 to
2024. robots.txt allows general crawlers (checked 28 Sep 2026). Listing entries look like
`Week 18 2024.04.27 - 2024.05.03 - <title>`: epi weeks run Saturday-Friday, and the epi year can differ from the
calendar year of the start date (2024-W01 = 30 Dec 2023 - 5 Jan 2024).

The site has returned HTTP 500 since 28 Sep 2026, so the history comes from the `denguedatahub` R package, which is
extracted from the same reports ([decision 0002](decisions/0002-wer-history-source.md)). `src/extract/wer_links.py`
remains in place to list the original PDFs when the site is back.

## Weather (Open-Meteo)

Daily rainfall and temperature from the Open-Meteo archive API for the 25 district centroids, 2006 to present,
model `era5_seamless` (ERA5 precipitation with ERA5-Land temperature). `best_match` was not used because it switches
models in 2017, and ERA5-Land alone has no precipitation. The free tier allows roughly 450 year-long requests per
day, so the backfill is resumable and stops cleanly on HTTP 429.

## Reference data (`reference/`)

| File | Source |
|---|---|
| `districts.csv`, `geo/lka_districts.geojson` | geoBoundaries gbOpen LKA ADM2 (OpenStreetMap, ODbL 1.0); centroids computed in `src/reference/build_districts.py` |
| `population/district_population_2024.csv` | Census of Population and Housing 2024, Table 3.2, read from the PDF by `src/reference/build_population.py` and checked against the printed totals |
| `rdhs.csv`, `rdhs_aliases.csv` | the 26 RDHS regions, their districts and spelling variants |
| `moh_parents.csv` | MOH areas split from an older area (lk_dengue mapping, unverified) |
| `moh_aliases.csv` | spelling variants of the same MOH area seen in NDCU PDFs |
