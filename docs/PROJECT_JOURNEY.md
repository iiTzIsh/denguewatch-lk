# DengueWatch LK — What We Built So Far

*Summary as of 29 September 2026*

---

## 1. The idea in one paragraph

Dengue outbreaks hit Sri Lanka every monsoon. Rain today creates mosquito breeding sites, and cases usually rise **2–4 weeks later**. DengueWatch LK collects **weather** and **dengue case** data every week, cleans and checks it, stores it in an organised way, and (later) will predict which districts are likely to see a rise, so action can start earlier.

> This is a portfolio project, not official health advice.

---

## 2. The big picture (how data flows)

```
 Websites / APIs          Our pipeline (runs every Monday)                    Result
 ───────────────          ───────────────────────────────                    ──────
 Open-Meteo (weather) ─┐
 NDCU weekly PDFs     ─┼─►  1. Download (raw copy kept)      = BRONZE
 WER PDFs (history)   ─┘    2. Clean + check                 = SILVER    ──►  Tables ready for
                            3. Organise into a star schema   = GOLD           dashboard + ML
```

- **Bronze** = the raw files exactly as downloaded. Never edited, so we can always go back.
- **Silver** = cleaned tables, one row per district per day or week.
- **Gold** = final, well-organised tables with automatic quality checks.

This "bronze → silver → gold" pattern is called the **medallion architecture**, and many real companies use it.

---

## 3. What we did, step by step

### Step 1: Python basics, done properly
- Wrote a script that downloads daily weather from a free weather service (Open-Meteo).
- Added **retries** (if the internet or the server fails, try again, waiting a bit longer each time).
- Added **logging** (a written record of what happened and when).
- Added **validation**: rainfall can't be negative, min temperature can't be above max, and so on.
- Wrote **automated tests** (pytest) that check the code still works after every change.

### Step 2: The website scraper
- Wrote a scraper for the Epidemiology Unit's weekly reports (WER).
- It checks `robots.txt` first (the website's rules for scrapers) and saves a copy so it never downloads the same page twice.
- ⚠️ The WER website has been **down (error 500)** since 28 Sep 2026, so this part is waiting.

### Step 3: A local data warehouse (DuckDB)
- Loaded the data into **DuckDB**, a free database that lives in a single file.
- Learned SQL joins, CTEs and window functions on our own data.
- Found out that **Sri Lankan epidemiological weeks run Saturday → Friday**.

### Step 4: Data modelling (star schema + SCD2)
- Organised the data into a **star schema**: *fact* tables (the numbers, e.g. weekly rainfall) surrounded by *dimension* tables (the descriptions, e.g. district, week).
- Built an **SCD Type 2** region table, which keeps history when an area changes. Example: Kesbewa MOH was split from Piliyandala. Old case numbers still join to the region as it was *at that time*. (We practised with demo data; real data comes later.)

### Step 5: Docker
- Packaged the whole project into a **Docker container**, so it runs the same way on any computer with one command.
- Moved all settings (folders, file paths) into one config file, which makes a later move to the cloud easy.

### Step 6: Airflow (automatic scheduling)
- Set up **Apache Airflow 3.3.2** in Docker. It runs the pipeline **every Monday at 7am** by itself.
- Failed steps retry automatically, and you can watch every run in a web page (green = OK, red = failed).
- The WER scraper has its **own separate schedule**, so when the government site is down, everything else still runs.

### Step 7: dbt (professional SQL transformations)
- Replaced our hand-made "build gold tables" script with **dbt**, the industry-standard tool.
- dbt builds the tables in the right order, runs **57 automatic data checks**, and draws a **lineage graph** showing where every table comes from. It's in the README.

### Step 8: GitHub
- Published the project: **github.com/iiTzIsh/denguewatch-lk**
- Added a README, a license, and the lineage picture.

### Step 9: Real districts + 20 years of weather
- Replaced the 5 test cities with **all 25 districts**. Their centre points were **calculated from an open map dataset** (geoBoundaries / OpenStreetMap), not typed in by hand.
- Wrote a **resumable backfill** that downloads weather from 2006 to now: 25 districts × 21 years = 525 files. If it stops (daily limit reached, Wi-Fi drops), you run the same command again and it continues where it left off.

### Step 10: A real problem we caught and fixed
- The first backfill finished, but **rainfall was empty for nearly every day**.
- The cause: the weather model we chose (ERA5-Land) **doesn't include rainfall**. The Open-Meteo documentation confirms this.
- Fixes:
  - switched to the **era5_seamless** model (has rainfall, and it's consistent for all 20 years)
  - kept the old files in their own folder instead of deleting them (raw data is never destroyed)
  - validation now **stops the run** if more than 5% of values are missing, instead of just warning
  - added a test that recreates this exact problem, so it can't happen again unnoticed
- Status: **431 of 525 files re-downloaded with no empty rainfall values**. The rest finishes tomorrow.

### Step 11: Dengue case data from NDCU
- Built a downloader for the **National Dengue Control Unit's weekly PDF reports**. It finds the links on the website instead of guessing file names, because the names are inconsistent.
- Built a **PDF parser** that reads the cases for each of the **26 health regions (RDHS)**.
- Every PDF is **checked against the "Total" row printed in the report**. If the numbers don't match, the file goes to a **quarantine folder** and is never loaded.
- First run: **20 weeks downloaded, 17 passed, 3 quarantined**. We looked at the 3 bad ones:
  - two had a text glitch ("Nil" showed up as "Ni")
  - one had a missing number in its Total row
- Fixed the parser, and all **20 of 20 weeks now pass**. Those 3 PDFs are kept as permanent test cases.

### Step 12: Two different "weeks"
- **NDCU weeks run Monday → Sunday** (the international ISO standard).
- **WER weeks run Saturday → Friday** (epidemiological weeks).
- Decision (written down in `docs/decisions/0001-two-week-systems.md`): each source **keeps its own weeks**, because moving numbers between them would mean inventing data. A daily calendar table connects the two.

### Step 13: The monitoring table
- Built `mart_ndcu_monitoring`: for every district and week, it shows cases, change vs last week, this week's rainfall and **rainfall 1–4 weeks earlier**.
- Handled **restatements**. NDCU often revises last week's number (e.g. Week 27: first 7,916, later 7,891). We keep both the first and the latest number.
- Fixed a bug: when a week was missing (weeks 18 and 20 aren't on the site), "change vs last week" was comparing against 2 weeks earlier. It now stays blank instead.
- Added a simple report: `python -m src.reports.hotspots`

### Step 14: CI (automatic checks on GitHub)
- Every time you `git push`, GitHub automatically:
  1. checks code quality (ruff) and types (mypy), and runs the tests (pytest)
  2. runs the **whole pipeline on sample data**, including all 57 dbt checks
  3. checks the Airflow schedules load correctly
- **First run: all green ✅**. The badge on the README shows "passing".

---

## 4. Key numbers today

| What | Number |
|---|---|
| Districts covered | 25 (26 health regions) |
| Weather history | 2006 → Sep 2026 (about 82% downloaded; finishing) |
| NDCU weeks loaded | 20 weeks of 2026 (520 region-week rows) |
| Automatic data checks (dbt) | 57, all passing |
| Code tests (pytest) | 57, all passing |
| Airflow schedules | 3 (weather + gold, NDCU, WER) |
| CI | ✅ green |

---

## 5. Tools used (all free)

| Tool | What it does for us |
|---|---|
| Python | Downloading, cleaning, parsing PDFs |
| DuckDB | The database (warehouse) |
| dbt | Builds the final tables and runs data checks |
| Airflow | Runs everything on a schedule, with retries |
| Docker | Same setup on any computer |
| GitHub + GitHub Actions | Code storage + automatic checks on every push |
| pytest, ruff, mypy | Tests, code style, type checks |

---

## 6. Lessons worth telling in an interview

1. **"Trust but verify your data source."** The weather backfill looked successful but had no rainfall. Stricter validation now catches problems like this automatically.
2. **"Government data is messy."** PDF glitches, missing totals and revised numbers. The parser checks every file against its own printed totals and quarantines anything that doesn't match.
3. **"Keep raw data forever."** Bronze files are never edited or deleted. That's what let us switch weather models safely.
4. **"Don't invent data."** Two week systems exist, so each source keeps its own weeks.
5. **"Make re-runs safe."** Every step can be run again without creating duplicates (idempotent).

---

## 7. What's still open

| Item | Status |
|---|---|
| Finish the weather backfill | Run `python -m src.extract.weather_backfill` tomorrow |
| WER history (2006–2024) | Waiting: site returns error 500. **Needed to train the prediction model.** |
| Real MOH region changes (SCD2) | ✅ Done: 233 MOH areas from NDCU page-2 tables (see moh_regions.md) |
| Population (for cases per 100,000 people) | Not yet sourced |

---

## 8. What's next

1. **Streamlit dashboard**: a Sri Lanka map of this week's hotspots
2. **WER ingestion + PDF parser**, as soon as the site is back
3. **Machine learning**: simple baselines first, then LightGBM, tested properly on past years
4. **Prediction API + weekly "Top 5 districts" alert**
5. **Move to the cloud** (Azure + Databricks Free) once the local version is complete
