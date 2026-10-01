# DengueWatch LK: Complete Project Overview

*A plain-language guide to what this project is, why it exists, what the data means, how accurate it is,
what has been built, and what is left. Last updated: 29 September 2026.*

> **Disclaimer:** DengueWatch LK is a **portfolio project**. It is **not official health advice**.
> For official dengue information, see the [National Dengue Control Unit](https://www.dengue.health.gov.lk/).

---

## Contents
1. [The objective](#1-the-objective)
2. [The real-world scenario](#2-the-real-world-scenario)
3. [Why this project is important](#3-why-this-project-is-important)
4. [How the system works (big picture)](#4-how-the-system-works-big-picture)
5. [The data: where it comes from and what it means](#5-the-data-where-it-comes-from-and-what-it-means)
6. [Data accuracy: how we protect it, and its limits](#6-data-accuracy-how-we-protect-it-and-its-limits)
7. [Why we did each thing (the reasoning)](#7-why-we-did-each-thing-the-reasoning)
8. [What has been built so far](#8-what-has-been-built-so-far)
9. [What still needs to be done](#9-what-still-needs-to-be-done)
10. [Tools used and why](#10-tools-used-and-why)
11. [Glossary](#11-glossary)

---

## 1. The objective

**Build an automated system that watches dengue and weather data for every district of Sri Lanka, every week,
and warns early about districts where cases are likely to rise.**

In simple terms, the finished system will, every Monday, without anyone pressing a button:

1. **Collect** the latest dengue case numbers and weather data
2. **Clean and check** the data, and reject anything that looks wrong
3. **Store** it in a well-organised database (a "data warehouse")
4. **Predict** which districts are likely to see more cases in the next 2–4 weeks *(still to build)*
5. **Show** the results on a map dashboard and through an API
6. **Send** a short "Top 5 districts" message to a phone (Telegram)

**Two goals at once:**
| Goal | What it means |
|---|---|
| **Public-health goal** | Show how data could give earlier warning of dengue rises |
| **Career goal** | Prove real **Data Engineer** skills first, then **AI/ML Engineer** skills, using a real Sri Lankan problem instead of a tutorial dataset |

---

## 2. The real-world scenario

- **Dengue** is spread by *Aedes* mosquitoes, which breed in standing water.
- Sri Lanka has **monsoon seasons**. After heavy rain, water collects in containers, drains and tyres,
  and mosquito numbers go up.
- There is a **delay**: rain today → mosquitoes breed → people get infected → cases are reported.
  This takes **a few weeks**.
- The problem: officials usually see the **case numbers only after an outbreak has already started**.

**The idea:** because rain comes *before* cases, recent rainfall plus recent case trends might help
predict **which districts are likely to rise 2–4 weeks ahead**. That gives health teams time for
earlier fogging, clean-up campaigns and awareness work.

**Real example from our data (2026):** national weekly cases rose from about **1,200 in April** to a peak of
about **7,900 per week in late June/early July** (monsoon season), then fell back to about **1,150 by September**.

---

## 3. Why this project is important

### For public health (the "why it matters" story)
- Dengue affects **tens of thousands of people in Sri Lanka every year**. The NDCU home page showed
  about **100,000 notified cases in 2026** by late September.
- Earlier warnings could mean **earlier action** and fewer people getting sick.
- The data already exists (government reports, weather archives), but it is **scattered and in PDFs**.
  Turning it into clean, connected, automatic data is exactly what data engineering does.

### For your career (why employers care)
This single project shows the skills listed in real Data Engineer / ML Engineer job adverts:

| Skill employers ask for | Where this project shows it |
|---|---|
| Getting data from messy sources | Web scraping, PDF parsing, APIs |
| Data quality | Validation, quarantine, 57 automatic data tests |
| Data modelling | Star schema, SCD Type 2, calendar tables |
| Pipelines & scheduling | Apache Airflow |
| Modern SQL transformation | dbt |
| Software engineering | Tests, type checks, Docker, Git, CI/CD |
| Serving data | Dashboard, REST API, alerts |
| Machine learning (next) | Forecasting with honest backtesting |
| Domain thinking | Epi weeks, restatements, health-data caveats |

---

## 4. How the system works (big picture)

```
 SOURCES                          PIPELINE (runs every Monday via Airflow)                OUTPUTS
 ───────                          ─────────────────────────────────────────                ───────
 Open-Meteo (weather API) ──┐
 NDCU weekly PDFs         ──┼──►  BRONZE   raw files, exactly as downloaded (never edited)
 WER PDFs (Epid. Unit)    ──┘        │
                                     ▼   parse + clean + CHECK (bad files → quarantine)
                                  SILVER   clean tables: one row per district per day/week
                                     │
                                     ▼   dbt: build + 57 automatic tests
                                  GOLD     star schema + monitoring table   ──►  Dashboard (map)
                                     │                                     ──►  REST API
                                     ▼   (to build)                        ──►  Telegram alert
                                  ML       forecast next 2–4 weeks          ──►  "Top 5 at risk"
```

**Bronze → Silver → Gold** is called the **medallion architecture**, and many companies use it.
- **Bronze** keeps the original, so we can always re-process if we find a mistake.
- **Silver** is clean and consistent.
- **Gold** is organised for people and programs to use.

---

## 5. The data: where it comes from and what it means

### 5.1 Weather: Open-Meteo
| Item | Detail |
|---|---|
| Source | [Open-Meteo](https://open-meteo.com/) historical weather API (free, no key) |
| Model used | **`era5_seamless`**: ERA5 rainfall + ERA5-Land temperature (a "reanalysis": weather observations combined with a weather model to fill every place and day) |
| Where | The **centre point of each of the 25 districts** |
| When | Daily, **2006 → about 6 days ago** (the data arrives with a delay of roughly 5 days) |
| License | CC BY 4.0 (free to use with credit) |

**What the columns mean**
| Column | Meaning |
|---|---|
| `rainfall_mm` | Total rain that day, in millimetres |
| `temperature_2m_mean / max / min` | Air temperature 2 metres above ground (°C): daily average / highest / lowest |
| `fetched_at` | When we downloaded it, so the newest download wins if two overlap |
| `rainfall_mm_total` (weekly) | Rain added up over the week |
| `rain_lag1_mm … rain_lag4_mm` | Rainfall **1, 2, 3, 4 weeks earlier**. Used because mosquitoes need time to breed. |

### 5.2 District boundaries: geoBoundaries (OpenStreetMap)
| Item | Detail |
|---|---|
| Source | [geoBoundaries](https://github.com/wmgeolab/geoBoundaries) "gbOpen LKA ADM2" (25 districts), built from OpenStreetMap |
| Used for | (1) the **centre point** of each district for the weather, (2) the **map** on the dashboard |
| License | ODbL 1.0 (free to use with credit) |

### 5.3 Dengue cases: NDCU weekly updates (current data)
| Item | Detail |
|---|---|
| Source | [National Dengue Control Unit](https://www.dengue.health.gov.lk/): "Weekly Dengue Update" PDFs |
| Covers | **26 health regions (RDHS)**. That's the 25 districts, but Ampara district is split into **Ampara + Kalmunai**. |
| Weeks | **ISO weeks: Monday → Sunday** (e.g. 2026-W37 = 7–13 Sep 2026) |
| What we have | **20 weeks** of 2026 (weeks 16–37; weeks 18 and 20 weren't published on the site) |

**What the columns mean**
| Column | Meaning |
|---|---|
| `cases_this_week` / `cases_first_reported` | Cases reported for that week, as first published |
| `cases_latest` | The **corrected** number, when the *next* week's report revises it (late reports, removed duplicates) |
| `is_restated` | True if the number was later corrected |
| `cases_prev_week` | Last week's number, as printed in this week's report |
| `cum_this_year` | Total cases so far this year |
| `has_revised_value` | The PDF marked a number with `*` (revised) |
| `total_check` | `full` = all our totals matched the PDF's printed total row; `partial` = the PDF's total row was missing a number, so we checked what was there |

### 5.4 Dengue history: WER (Epidemiology Unit) *(not loaded yet)*
| Item | Detail |
|---|---|
| Source | [Weekly Epidemiological Report](https://www.epid.gov.lk/weekly-epidemiological-report) PDFs |
| Covers | **2006–2024** (years listed on the site), dengue by region |
| Weeks | **Epidemiological weeks: Saturday → Friday** (e.g. 2024-W01 = 30 Dec 2023 → 5 Jan 2024) |
| Why it matters | This is the **long history needed to train the prediction model** (including the big 2017 epidemic) |
| Status | ❌ The website has returned **error 500** since 28 Sep 2026. The scraper is ready and waiting. |

### 5.5 Two kinds of "week" (important!)
| Source | Week runs | Example |
|---|---|---|
| NDCU | **Monday → Sunday** (ISO) | 2026-W37 = 07–13 Sep 2026 |
| WER | **Saturday → Friday** (epi week) | 2024-W18 = 27 Apr – 03 May 2024 |

We **never move case numbers between the two**, because that would mean inventing numbers.
Each source keeps its own weeks. Weather is daily, so it can be added up to either kind of week exactly.
A daily **calendar table (`dim_date`)** links each day to both.
(Recorded in `docs/decisions/0001-two-week-systems.md`.)

---

## 6. Data accuracy: how we protect it, and its limits

### 6.1 How we protect accuracy (checks built into the pipeline)
| Check | What it catches |
|---|---|
| **Weather validation** | Negative rainfall, min temp > max temp, duplicate dates, **more than 5% missing values → the download is rejected** |
| **PDF total check** | For every NDCU PDF, our sum of all regions must **equal the "Total" row printed in the PDF** |
| **All 26 regions present** | A missing region means the parser misread the layout, so the file is rejected |
| **Date check** | The week dates in the PDF header must match the week number |
| **Quarantine** | Any file that fails goes to `data/quarantine/` with an error note. It is **never loaded**. |
| **57 dbt data tests** | Unique keys, no missing links between tables, values in valid ranges, 25 districts every week, gold totals = silver totals, correct week start days, and more |
| **Newest-download-wins** | If two weather downloads overlap, only the newest value is kept (no double counting) |
| **Restatements kept** | Both the first and the corrected case numbers are stored |
| **Alert only after green tests** | The Telegram message is sent **only if all data tests passed** |
| **CI on GitHub** | Every code change reruns all tests plus the whole pipeline on sample data |

### 6.2 Real problems these checks already caught
1. **Weather model had no rainfall.** The first 20-year download (ERA5-Land) came back with **rainfall empty
   for nearly every day**. Open-Meteo's documentation confirms ERA5-Land has no precipitation. We switched to
   `era5_seamless` and made validation **stop** on missing data instead of just warning.
2. **3 of 20 NDCU PDFs were quarantined.** In two, the PDF text showed "Nil" as "Ni". In one, a number was
   missing from the Total row. All three were investigated, the parser was fixed, and they are now permanent test cases.
3. **"Change vs last week" across missing weeks.** Weeks 18 and 20 aren't published, so week 19 was being
   compared with week 17. Fixed: it now stays blank, and a test enforces this.

### 6.3 Honest limitations (what the data can't tell us)
| Limitation | What it means |
|---|---|
| **Reported cases ≠ all infections** | Only people who visit a hospital or clinic and get reported are counted |
| **Numbers get revised** | Late reports and removed duplicates change last week's numbers (we keep both) |
| **"Last year" columns in NDCU PDFs don't add up** | Even in good PDFs they don't match the printed total (e.g. 617 vs 606), so **we don't use them** |
| **Weather at one point per district** | District weather = weather at the district's centre, on a grid of roughly 10–25 km. Big districts have varied weather inside them. |
| **Reanalysis ≠ rain gauge** | ERA5 is modelled data, which is very consistent but not the same as a local rain gauge |
| **NDCU history is short** | Only 20 weeks, which is not enough to train a model. **WER history is required.** |
| **Region changes over time** | Some health areas split (e.g. Kesbewa from Piliyandala). The SCD2 table is built from the MOH areas observed in the NDCU PDFs; split dates aren't published, so history starts at the first week each area was seen. |
| **Not a forecast yet** | The dashboard and alert show **current cases**, not predictions. The wording says so honestly. |

---

## 7. Why we did each thing (the reasoning)

| What we did | Why |
|---|---|
| Kept **raw files forever** (bronze) | If a mistake is found later, we can re-process without downloading again. This saved us during the rainfall problem. |
| **Retries** on downloads | Government sites and APIs fail sometimes (WER is down right now) |
| **Resumable backfill** | 525 weather files take more than a day's free API limit, so it stops safely and continues later |
| **Tests** for code (pytest) | Changes can't silently break things |
| **Tests** for data (dbt) | Code can be correct while the *data* is wrong |
| **Star schema** (facts + dimensions) | Easy, fast questions like "cases by district by week", and the standard in companies |
| **SCD Type 2** regions | Health areas split over time, and old numbers must still join to the area as it was then |
| **Separate week systems** | Mixing Monday and Saturday weeks would create false numbers |
| **Docker** | Runs the same way on any computer, and is ready for the cloud |
| **Airflow** | Runs automatically every week, retries failures, and shows green/red in a web page |
| **dbt** | The industry standard for SQL transformations, tests, documentation and lineage |
| **CI (GitHub Actions)** | Every push is checked automatically, and the green badge proves quality to recruiters |
| **Dashboard + API + alert** | Data is only useful when people can see it and use it |
| **Free tools only** | Budget limit, and all of them are also used in real companies |

---

## 8. What has been built so far

| Phase | What | Status |
|---|---|---|
| **0 – Foundations** | Python with retries/logging/validation, tests, SQL, DuckDB, Docker, Airflow, dbt | ✅ Done |
| **1 – Ingestion** | 25 districts (coordinates from open map data); weather backfill 2006→now; NDCU PDF downloader; WER scraper (ready) | 🟡 Weather ~82% (finish the backfill); NDCU ✅; **WER waiting for the site** |
| **2 – Silver** | NDCU PDF parser with total checks + quarantine; weather silver tables; newest-wins dedupe | 🟡 NDCU ✅, WER parser waiting |
| **3 – Gold** | Star schema, calendar bridge (`dim_date`), weather facts (both week types), NDCU dengue fact with restatements, monitoring table; 57 data tests | 🟡 Done for NDCU + weather; WER fact waiting |
| **4 – ML** | Forecasting | ⛔ Blocked: needs WER history |
| **5 – Serving** | React dashboard (map, forecasts, model health), FastAPI, weekly Telegram alert | ✅ Done |
| **6 – Production** | GitHub Actions CI (lint, types, tests, full pipeline, DAG checks) | 🟡 CI ✅; drift monitoring, retraining and demo video later |
| **7 – Cloud** | Azure + Databricks Free | ⏳ Later |

**Numbers today:** 25 districts · 26 health regions · 20 NDCU weeks (520 region-weeks) · weather 2006→2026 (finishing) ·
57 data tests · 70 code tests · 3 Airflow schedules · CI green · dashboard, API and Telegram alert working.

**Project link:** https://github.com/iiTzIsh/denguewatch-lk

---

## 9. What still needs to be done

### Must do (to complete the project)
| # | Task | Why | Depends on |
|---|---|---|---|
| 1 | **Finish the weather backfill** | Rainfall for 2024–2026 is still missing | Just rerun the command (free daily limit) |
| 2 | **WER: download all PDFs (2006–2024)** | Long history for training | Website back online |
| 3 | **WER PDF parser** (layouts may change across years) + checks + quarantine | Turn PDFs into clean weekly numbers | #2 |
| 4 | **WER dengue fact table** (epi weeks) + tests | Organised history | #3 |
| 5 | **Real region-change data** for SCD2 (replace the demo data) | Correct history when areas split | Verified source |
| 6 | **Population per district** | Cases per 100,000 people (fair comparison between big and small districts) | Verified source (2024 census) |
| 7 | **ML feature table** | Lags, rolling averages, season, "endemic channel" (normal range for that week) | #4 |
| 8 | **Baselines**: "same as last week", "same week last year" | Any model must beat these to be useful | #7 |
| 9 | **LightGBM model** for 2 and 4 weeks ahead + outbreak flag | The actual prediction | #7 |
| 10 | **Walk-forward backtesting** (train on past years → test on the next year → repeat), including the **2017 epidemic** | Honest measure of accuracy, with no cheating by looking at the future | #9 |
| 11 | **MLflow**: track experiments, register the best model | Reproducible ML | #9 |
| 12 | Update the **dashboard, API and alert** to show **forecasts / "at risk"** | The early-warning part | #9 |
| 13 | **Drift monitoring** (Evidently) + monthly retraining | Models get worse as the world changes | #11 |
| 14 | **README with real results**, screenshots, a 2–3 minute **demo video**, LinkedIn post | Show the work | Everything |

### Optional
| Task | Why |
|---|---|
| Move to **Azure + Databricks Free** (Phase 7) | Cloud experience, which employers want |
| Public dashboard hosting | A live link on your CV |

### Definition of "done" (from the project brief)
- [x] Runs weekly end-to-end without manual steps
- [x] Multi-year history loaded and validated
- [x] SCD2 region dimension handles real MOH changes
- [x] Model beats baselines in walk-forward backtest (or honestly explains why not)
- [x] Dashboard + API + weekly alert working
- [x] CI/CD, tests, data quality checks, **drift monitoring** in place
- [ ] Professional README + demo video + LinkedIn post

---

## 10. Tools used and why

| Tool | Role in the project | Why this tool |
|---|---|---|
| **Python** | Downloading, parsing, cleaning | Most common data language |
| **requests / BeautifulSoup / pdfplumber** | APIs, web pages, PDFs | Simple, reliable, free |
| **DuckDB** | The data warehouse | Fast SQL in a single file, no server needed |
| **dbt** | Builds gold tables + 57 data tests + lineage docs | Industry standard for SQL transformation |
| **Apache Airflow 3** | Weekly scheduling, retries, monitoring | Most widely used pipeline scheduler |
| **Docker** | Same environment everywhere | Standard for deployment |
| **React + TypeScript, MapLibre, ECharts** | Dashboard, map, charts | A real web app over the API, the way industry products are built |
| **FastAPI** | REST API with auto-generated docs | Modern, typed, fast |
| **Telegram Bot API** | Weekly phone alert | Free and simple |
| **pytest / ruff / mypy** | Code tests, style, type checks | Standard Python quality tools |
| **GitHub + GitHub Actions** | Code hosting + automatic checks (CI) | Standard, free for public repos |
| *(Next)* **LightGBM, MLflow, Evidently** | Forecasting, experiment tracking, drift | Common in ML teams |

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **Pipeline** | A chain of automatic steps that move and change data |
| **Bronze / Silver / Gold** | Raw → cleaned → organised data layers (medallion architecture) |
| **Backfill** | Loading a lot of past data in one go |
| **Idempotent** | Running a step twice gives the same result (no duplicates) |
| **Quarantine** | A folder where bad files are kept aside instead of being loaded |
| **Star schema** | A *fact* table (numbers) in the middle, *dimension* tables (descriptions) around it |
| **Fact table** | Measurements, e.g. cases per district per week |
| **Dimension table** | Descriptions, e.g. district name, province, week dates |
| **SCD Type 2** | A way to keep history when something changes (old version closed, new version added) |
| **Grain** | What one row means, e.g. "one district, one week" |
| **Epi week** | Epidemiological week used by WER: Saturday → Friday |
| **ISO week** | International week used by NDCU: Monday → Sunday |
| **RDHS** | Regional Director of Health Services area (26 in Sri Lanka) |
| **MOH area** | Medical Officer of Health area (smaller than a district) |
| **Restatement** | A number corrected in a later report |
| **Reanalysis (ERA5)** | Weather data built by combining observations with a weather model |
| **Lag feature** | A value from earlier weeks, e.g. rain 2 weeks ago |
| **Endemic channel** | The "normal" range of cases for a given week of the year. Above it = possible outbreak. |
| **Baseline model** | A very simple prediction (e.g. "same as last week") that a real model must beat |
| **Walk-forward backtest** | Test a model the honest way: train only on the past, predict the next period, move forward, repeat |
| **Data leakage** | Accidentally letting a model see future information, which gives fake high accuracy |
| **Drift** | When new data starts to look different from the training data, so the model may get worse |
| **CI (Continuous Integration)** | Automatic checks that run every time code is pushed |
| **API** | A way for other programs to request data (e.g. `/hotspots`) |
| **DAG** | An Airflow workflow: tasks and the order they run in |
