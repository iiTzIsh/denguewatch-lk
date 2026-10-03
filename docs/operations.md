# Operations

## Services

`docker compose up -d` starts MLflow, runs the one-time setup (`init`, `src/bootstrap.py`; it skips itself once
set up), then starts the API and the dashboard. Airflow is a separate stack because it is only needed for the
weekly schedule.

| Service | Start | Address |
|---|---|---|
| Dashboard (nginx + React) | `docker compose up -d web` | http://localhost:3000 |
| API (FastAPI) | `docker compose up -d api` or `uvicorn src.api.main:app` | http://localhost:8000/docs |
| MLflow | `docker compose up -d mlflow` | http://localhost:5000 |
| Airflow | `docker compose -f docker-compose.airflow.yml up -d` | http://localhost:8080 |
| Warehouse | DuckDB file `data/denguewatch.duckdb` | |

Useful commands: `docker compose logs -f init` (setup progress), `docker compose run --rm init --force` (rerun
setup), `docker compose run --rm pipeline` (one-off pipeline run).

Rebuild an image after changing a `requirements*.txt` file (`docker compose build`, or
`docker compose -f docker-compose.airflow.yml build`). Code changes in `src/`, `dags/` and `dbt/` are picked up
without a rebuild by Airflow, which mounts the project folders.

## Schedule (Airflow, Asia/Colombo time)

| DAG | When | Tasks | Retries |
|---|---|---|---|
| `wer_ingest_weekly` | Mon 06:00 | list WER PDF links | 3, 30 min apart |
| `ndcu_ingest_weekly` | Mon 06:30 | download PDFs, parse district and MOH tables | download 3, parsing 0 |
| `denguewatch_weekly` | Mon 07:00 | weather, silver, SCD2, dbt build, docs, forecasts, alert, drift check, retrain trigger | 2; dbt build 0 |
| `retrain_monthly` | 1st of month 09:00, or when drift is detected | train and promote | 1 |

Ingestion runs in separate DAGs so an unavailable government site does not block the weekly build. Parsing and
dbt tests are not retried: a bad PDF or failed data test needs a fix, not another attempt. Airflow, dbt and the
ML code each use their own virtualenv in the Airflow image because their dependency pins conflict.

## Weekly alert (Telegram)

`src/alerts/telegram.py` runs after `predict_forecasts` and sends the top districts by cases plus the regions
forecast at or near their outbreak level.

- Configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` (never committed; see `.env.example`).
  Airflow reads `.env` at start-up, so restart the stack after editing it.
- One message per data week. Sent weeks are recorded in `data/alerts/telegram_sent_weeks.txt`, so re-running a
  DAG does not send duplicates.
- Forecasts older than 21 days are left out of the message.

```bash
python -m src.alerts.telegram --dry-run   # print the message only
python -m src.alerts.telegram --force     # send again for a week that was already sent
```

## Model registry and retraining

Every backtest and training run is logged to the MLflow experiment `denguewatch-forecast` (parameters, metrics,
per-year errors, feature importance). Trained models are registered as `denguewatch-forecaster`:

| Alias | Meaning |
|---|---|
| `@champion` | the version used for weekly forecasts |
| `@previous_champion` | the version before it, kept for rollback |

A retrained model is promoted only if it beats the naive forecast at both horizons and is no more than 1% worse
than the current champion. Otherwise it stays registered with `decision = rejected` and the reason. Training also
refuses to run on fewer than 10,000 labelled rows (exit code 2).

Rollback: move the `champion` alias back to an earlier version in the MLflow UI, or

```bash
python -c "from mlflow import MlflowClient; MlflowClient('http://localhost:5000').set_registered_model_alias('denguewatch-forecaster', 'champion', '1')"
```

## Forecasts and monitoring

- `python -m src.ml.predict` scores each region's latest week with `@champion` and appends to
  `ml.forecast_weekly` (idempotent per base week and model version). The API, dashboard and alert read this
  table, so they keep working when MLflow is down. `--soft` skips scoring with a warning in that case.
- `gold.mart_forecast_accuracy` joins every forecast whose target week has passed to the actual cases and to the
  naive forecast.
- `python -m src.ml.replay` rebuilds the last 16 weeks of forecasts as-of each week (no hindsight).
- `python -m src.ml.monitor` compares the last 8 weeks of model inputs with the same months of the previous five
  years (Evidently, Wasserstein distance). It writes `ml.drift_runs` and an HTML report to `data/reports/drift/`;
  if drift is detected, the weekly DAG triggers `retrain_monthly`.

## Data quality

| Stage | Check | On failure |
|---|---|---|
| Weather download | more than 5% missing values, negative rain, min > max temperature, duplicate dates | pull rejected |
| Weather API quota | HTTP 429 | stops cleanly (exit 3); the next run resumes |
| NDCU district table | region sums equal the printed total, 26 regions, dates match the ISO week | PDF quarantined to `data/quarantine/ndcu/` |
| NDCU MOH table | known headings only, header weeks match, no duplicates, counts 0-5,000 | PDF quarantined to `data/quarantine/ndcu_moh/` |
| WER history | known region names, whole non-negative counts, no duplicates | load stops |
| dbt (87 tests) | keys, nulls, ranges, relationships, grain, reconciliations, no leakage into features | build fails; forecasts and alert do not run |
| Cross-source | NDCU 2025 cumulative vs WER | warning |

Every step is idempotent and can be re-run safely.

## CI

`.github/workflows/ci.yml` runs on every push and pull request:

1. ruff (lint and format check), mypy and pytest
2. the full pipeline and dbt build on generated sample data plus three real NDCU PDFs
3. Airflow DAG integrity
4. web dashboard type check and production build

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| WER or NDCU DAG red | source site unavailable | none; it catches up next week |
| PDF in `data/quarantine/` | new layout or data problem | inspect the PDF, fix the parser, add a test |
| `dbt_build` failed | a data test failed | read the task log, fix data or code, clear the task |
| No forecast section | MLflow down or no champion | `docker compose up -d mlflow`, then `python -m src.ml.train` |
| `No module named ...` in Airflow | image older than `requirements*.txt` | rebuild the Airflow image |
| Telegram task skipped | week already sent | use `--force` to resend |
| Telegram token exposed | | revoke it with @BotFather (`/revoke`) and update `.env` |
