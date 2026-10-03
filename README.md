# DengueWatch LK

[![CI](https://github.com/iiTzIsh/denguewatch-lk/actions/workflows/ci.yml/badge.svg)](https://github.com/iiTzIsh/denguewatch-lk/actions/workflows/ci.yml)

An automated dengue early-warning pipeline for Sri Lanka. Every week it ingests weather and dengue surveillance
data, builds a tested star schema, and forecasts cases for all 26 health regions 2 and 4 weeks ahead, flagging
regions that are heading above their usual outbreak level.

> **Disclaimer:** this is a portfolio project, not official health advice. For official figures see the
> [National Dengue Control Unit](https://www.dengue.health.gov.lk/).

![Dashboard](docs/images/web_1_hero.png)

## Why

Dengue peaks with the monsoons, and case counts usually show an outbreak only after it has started. Rain drives
mosquito breeding weeks before cases rise, so combining weather with surveillance data can flag regions earlier,
leaving time for vector control and awareness work.

## Architecture

```
SOURCES                         BRONZE              SILVER                  GOLD (dbt)                    SERVING
Open-Meteo (daily weather) ─┐
NDCU weekly PDFs ───────────┼─► raw files ──► parsed + validated ──► star schema + marts ──► FastAPI ──► React dashboard
WER history (denguedatahub) ┘   (immutable)    (DuckDB, quarantine)   87 data tests             │
                                                     │                      │                   └──► Telegram alert
                                                     └─► SCD2 MOH regions   └─► mart_ml_features
                                                                                  │
                                         LightGBM ◄── walk-forward backtest ◄─────┘
                                            │  MLflow tracking + registry (@champion)
                                            └─► weekly batch scoring ─► ml.forecast_weekly ─► forecast vs actual, drift
```

Orchestrated by Airflow (weekly ingest, build, forecast and alert; monthly and drift-triggered retraining).

![dbt lineage](docs/images/dbt_lineage.png)

## Results

Walk-forward backtest, test years 2014-2025, 16,250 region-weeks. Mean absolute error in weekly cases per region:

| Model | 2 weeks ahead | 4 weeks ahead |
|---|---|---|
| Naive ("same as this week") | 15.49 | 21.62 |
| LightGBM, cases only | 15.25 | 19.59 |
| **LightGBM + weather** | **15.03 (-3%)** | **18.99 (-12%)** |

On the 2026 epidemic, with a model trained only on data up to mid-May, the error was 26% (2 weeks) and 44%
(4 weeks) lower than naive. The model anticipated the decline after the July peak but under-forecast the start of
the rise. An as-of replay of Jun-Sep 2026 gives +28% / +47% skill, and the 2-week alert caught 76% of outbreak
weeks. Details: [docs/forecasting.md](docs/forecasting.md).

## Tech stack

| Layer | Tools |
|---|---|
| Ingestion | Python (requests, BeautifulSoup, pdfplumber), Open-Meteo API |
| Storage | DuckDB, medallion layout (bronze / silver / gold) |
| Transformation | dbt-duckdb: staging, star schema, marts, 87 data tests; SCD Type 2 region dimension |
| Machine learning | LightGBM, scikit-learn, MLflow (tracking, registry, champion/challenger), Evidently (drift) |
| Orchestration | Apache Airflow 3 (Docker Compose, LocalExecutor) |
| Serving | FastAPI, React + TypeScript (Vite, Tailwind, ECharts, MapLibre), nginx, Telegram Bot API |
| Quality | pytest, ruff, mypy, GitHub Actions CI (unit tests, full pipeline on sample data, DAG checks, web build) |

## Quick start

Requires Docker Desktop.

```bash
git clone https://github.com/iiTzIsh/denguewatch-lk && cd denguewatch-lk
docker compose up -d             # MLflow -> one-time setup -> API + dashboard
docker compose logs -f init      # follow setup until "DengueWatch LK is ready"
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| MLflow | http://localhost:5000 |

Setup (`src/bootstrap.py`) downloads the case data and 20 years of weather, runs every data check, trains and
registers the model and makes the first forecasts. Open-Meteo's free daily quota covers most but not all of the
weather backfill; run `docker compose run --rm init --force` the next day to finish it.

Weekly automation runs in a separate Airflow stack:

```bash
docker compose -f docker-compose.airflow.yml up airflow-init
docker compose -f docker-compose.airflow.yml up -d        # http://localhost:8080
```

## Development

```bash
python -m venv .venv && .venv\Scripts\activate             # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt -r requirements-dbt.txt -r requirements-api.txt -r requirements-ml.txt -r requirements-dev.txt
python -m src.pipeline                                     # parse -> silver -> SCD2 -> dbt build -> forecasts
pytest && ruff check . && ruff format --check . && mypy src
```

Dashboard with live reload (Node 22+, API on port 8000): `cd web && npm install && npm run dev`.

## Project layout

```
dags/            Airflow DAGs (weekly pipeline, ingestion, monthly retraining)
dbt/             staging models, star schema, marts and data tests
src/extract/     weather, NDCU and WER extractors
src/transform/   NDCU PDF parsers (district and MOH tables), SCD2 region dimension
src/load/        silver layer loader (DuckDB)
src/ml/          features, models, backtest, training/registry, batch scoring, monitoring
src/api/         FastAPI service
src/alerts/      weekly Telegram alert
web/             React dashboard, nginx config
reference/       versioned reference data (districts, regions, population, MOH aliases)
infra/airflow/   Airflow image (dbt and ML in separate virtualenvs)
tests/           unit and integration tests, sample PDFs
docs/            design notes and decisions
```

## Documentation

- [Operations](docs/operations.md): services, schedules, alerts, retraining, data quality, troubleshooting
- [Dashboard](docs/dashboard.md): what each section shows and where the numbers come from
- [Data model](docs/data_model.md) and [data sources](docs/data_sources.md)
- [Forecasting](docs/forecasting.md): features, backtest, outbreak rule, registry, monitoring
- [MOH areas and SCD2](docs/moh_regions.md)
- Decisions: [two week systems](docs/decisions/0001-two-week-systems.md), [WER history source](docs/decisions/0002-wer-history-source.md)

## Data sources

| Source | Used for | Licence / notes |
|---|---|---|
| [NDCU](https://www.dengue.health.gov.lk/) weekly updates | 2026 cases per region and high-risk MOH areas | Parsed from PDFs and checked against the printed totals |
| [denguedatahub](https://github.com/thiyangt/denguedatahub) (Talagala) | Weekly case history 2007-2026, from the Epidemiology Unit's WER | GPL-3, pinned commit |
| [Open-Meteo](https://open-meteo.com/) | Daily rainfall and temperature (ERA5) | CC BY 4.0 |
| [Census 2024](https://www.statistics.gov.lk/Resource/en/Population/CPH_2024/CPH2024_Final_Eng.pdf) | District population for rates per 100,000 | Department of Census and Statistics, Table 3.2 |
| [geoBoundaries](https://github.com/wmgeolab/geoBoundaries) | District boundaries and centroids | OpenStreetMap, ODbL 1.0 |

## Roadmap

- Cloud deployment: Azure Data Factory and storage for ingestion, Databricks for the gold layer and ML.
- Re-verify the WER history against the original PDFs once the Epidemiology Unit site is back online.

## Author

**Ishara Madusanka**, BSc (Hons) Information Technology (Data Science), SLIIT
