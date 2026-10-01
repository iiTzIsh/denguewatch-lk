# DengueWatch LK: How the Whole System Works

The dashboard is only one part. This guide covers everything else: the **Telegram alert**, the **API**, **Airflow** (automatic scheduling), **MLflow** (model tracking), **automatic retraining**, **monitoring**, **data quality checks** and **CI**. For each one: what it does, how it works in practice, and how to use it.

> Companion guide: [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) explains the dashboard itself.

---

## 1. The big picture: what happens every Monday

Nobody has to press anything. Airflow runs this by itself (Sri Lanka time):

```
06:00  wer_ingest_weekly     check the Epidemiology Unit site for new WER reports (site often down → isolated)
06:30  ndcu_ingest_weekly    download new NDCU weekly PDFs → read the district table → check vs printed Total
                             → read the high-risk MOH table (page 2)
                             (bad PDF → quarantine folder, never loaded)
07:00  denguewatch_weekly
         extract_weather       last 35 days of weather for 25 districts (Open-Meteo)
         load_silver           clean tables in DuckDB (newest download wins, no duplicates)
         scd2_regions          MOH area history table (SCD2, from page 2 of the NDCU PDFs)
         dbt_build             gold tables + ~95 automatic data checks  ← any failed check STOPS here
         ├─ dbt_docs           documentation + lineage graph
         └─ predict_forecasts  champion model forecasts every region 2 and 4 weeks ahead
              ├─ send_alert    Telegram message (cases + forecast)
              └─ monitor_drift Evidently check → if unusual → trigger retrain_monthly
1st of month 09:00
       retrain_monthly       train a new model → keep it only if it beats the current one
```

**The golden rule:** nothing reaches the dashboard, API or phone unless **all data checks passed** first.

---

## 2. The Telegram alert (message system)

### What you receive

A real message generated from the data on 30 Sep 2026:

```
🦟 DengueWatch LK - 2026-W37
07 Sep - 13 Sep 2026

Cases this week (all districts): 1,156 (+4 vs last week)

Top 5 districts by cases
1. Gampaha: 218 (-6)
2. Colombo: 207 (-15)
3. Kandy: 174 (+16)
4. Kalutara: 73 (+2)
5. Kegalle: 69 (+11)

Biggest rise: Galle +22

Forecast (model v2, case data to 13 Sep)
⚠️ Kegalle: ~48 cases in 4 wks (outbreak level 48) - HIGH
⚠️ Nuwara Eliya: ~14 cases in 4 wks (outbreak level 16) - watch
⚠️ Hambantota: ~17 cases in 4 wks (outbreak level 21) - watch
⚠️ Galle: ~65 cases in 4 wks (outbreak level 81) - watch
⚠️ Gampaha: ~182 cases in 2 wks (outbreak level 216) - watch

Source: NDCU weekly update; forecast: DengueWatch model (WER + NDCU cases,
Open-Meteo weather). Portfolio project - not official health advice.
```

### How it's built (`src/alerts/telegram.py`)

| Part of the message | Comes from |
|---|---|
| Cases, Top 5, Biggest rise | `gold.mart_ndcu_monitoring`, the newest NDCU week |
| Forecast lines | `ml.forecast_latest`, regions at 🟠 watch or 🔴 high (max 5). If none: *"No region is forecast near its outbreak level"* plus the closest one. |

The script only **reads the warehouse**. It never runs the model, so it's fast and can't break the model.

### Safety rules built in

| Rule | Why |
|---|---|
| **Sent once per week.** Sent weeks are remembered in `data/alerts/telegram_sent_weeks.txt`. | Airflow retries or re-runs never spam your phone. `--force` sends again on purpose. |
| **Only after a green dbt build.** | You never get a message built on data that failed its checks. |
| **Forecast optional.** If MLflow is down or no model exists, the forecast part is just left out. | The case alert must never depend on the ML part. |
| **Stale guard.** A forecast based on data more than 3 weeks older than the cases week is hidden and says "stale". | Prevents old warnings (this really happened once and was caught). |
| **The token is never logged**, and it lives only in `.env` (git-ignored). | The token = full control of your bot. If it leaks, run `/revoke` in @BotFather. |

### Set it up (once)

1. In Telegram, message **@BotFather** → `/newbot` → copy the **token**.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `"chat":{"id": ...}`.
3. Put both in `F:\DengueWatchLK\.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=123456789
   ```

### Use it by hand

```powershell
python -m src.alerts.telegram --dry-run     # print the message, send nothing (safe test)
python -m src.alerts.telegram               # send (skipped if this week was already sent)
python -m src.alerts.telegram --force       # send again anyway
```

| Exit / log | Meaning |
|---|---|
| "Alert sent for 2026-W37" | Delivered |
| "already sent - skipping" | Normal on a re-run |
| exit code 2, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set" | `.env` is missing the values |
| exit code 1, "Telegram returned HTTP 401" | Wrong or revoked token |

---

## 3. The REST API (for other apps)

A read-only "data counter": other programs (a website, a mobile app, another team) can ask for the same numbers as JSON. **The dashboard itself is one of these programs**: the React app gets every number from this API, so the two can never disagree.

```powershell
uvicorn src.api.main:app --reload            # http://localhost:8000/docs (interactive)
```

| Endpoint | Returns |
|---|---|
| `GET /health` | Is the warehouse reachable + data freshness dates |
| `GET /weeks` | Weeks that have NDCU data |
| `GET /hotspots?week=2026-W37&top=5` | Top districts by cases |
| `GET /districts` · `GET /districts/{name}/trend` | District list · weekly cases and rainfall |
| `GET /forecast?top=5` | Forecast per region with risk level + model version |
| `GET /moh/hotspots?week=2026-W37&top=10` | High-risk MOH areas NDCU listed that week |
| `GET /model/health` | Forecast error vs naive + latest drift check |
| `GET /national/trend` | National weekly cases |
| `GET /districts/{name}/rain?since=2026-03-02` | Weekly rainfall, continuous |
| `GET /model/forecast-vs-actual?horizon=4` | National actual vs model vs naive per week |
| `GET /geo/districts` | District outlines (GeoJSON) for the map |

How it works in practice:
- **Typed responses (Pydantic).** Every answer has a fixed shape, which is the "contract" other apps can rely on.
- **Input checking.** `week=2026-37` → **422** (bad format); `top=0` → **422**; a week with no data → **404**; database busy or missing → **503**.
- **Read-only.** It opens the database in read-only mode, so an API call can never change data.
- In `/docs`: click an endpoint → **Try it out** → **Execute**, and you see the real request and response.

---

## 4. Airflow: the automatic scheduler

```powershell
docker compose -f docker-compose.airflow.yml up -d      # http://localhost:8080  (airflow / airflow)
```

### The 4 DAGs (jobs)

| DAG | When | Tasks | Retries |
|---|---|---|---|
| `wer_ingest_weekly` | Mon 06:00 | list WER PDFs | 3, 30 min apart (the government site is often down) |
| `ndcu_ingest_weekly` | Mon 06:30 | download PDFs → parse + validate | download 3; **parse 0** (a bad PDF won't fix itself) |
| `denguewatch_weekly` | Mon 07:00 | weather → silver → SCD2 → dbt build → docs / forecasts → alert / drift → retrain trigger | 2, 5 min apart; **dbt 0** (a failed data check is a real problem) |
| `retrain_monthly` | 1st of month 09:00 (+ when drift is detected) | train and promote | 1 |

**Why separate DAGs?** If the WER website is down, only that small DAG turns red. Weather, NDCU, forecasts and the alert still run.

### Using the Airflow UI

- **Unpause** a DAG with its toggle (new DAGs start paused).
- **▶ Trigger** runs it now.
- **Grid view:** 🟩 success · 🟥 failed · 🟧 retrying · pink = skipped (e.g. `trigger_retrain` when there's no drift, which is normal).
- Click a square → **Logs** to see exactly what the Python script printed.
- **Clear** a failed task to run it again after fixing the problem.

### Isolation inside the Airflow image

Airflow, dbt and ML each have their **own Python environment** (`dbt_venv`, `ml_venv`), because their libraries need different versions of the same packages. This is a common industry pattern.

---

## 5. MLflow: model tracking and the model registry

```powershell
docker compose up -d mlflow                  # http://localhost:5000
```

### Experiments (every training run is recorded)

`python -m src.ml.backtest` or `python -m src.ml.train` creates a **run** with:
- **params**: model settings (learning rate, trees, horizon, data rows, last data week)
- **metrics**: MAE, RMSE, skill vs naive, outbreak recall/precision, MAE per year (chart), 2017 results
- **artifacts**: backtest predictions CSV, per-year results, feature importance

**Use:** Experiments → `denguewatch-forecast` → tick runs → **Compare**. Every number in the README can be traced back to a run.

### Model registry (which model is "live")

`denguewatch-forecaster` has **versions** (v1, v2, …). Two labels (**aliases**) decide which one is used:

| Alias | Meaning |
|---|---|
| `@champion` | The model the weekly forecast uses |
| `@previous_champion` | The one before, kept for rollback |

Each version is tagged `decision = promoted / rejected` plus the **reason**, e.g. *"worse than champion at h=4: MAE 19.40 > 19.18"*.

**Rollback** (if a new model misbehaves): Models tab → version → move the `champion` alias back. Or:
```powershell
python -c "from mlflow import MlflowClient; MlflowClient('http://localhost:5000').set_registered_model_alias('denguewatch-forecaster','champion','1')"
```

---

## 6. Automatic retraining (champion / challenger)

```
retrain trigger (monthly, or drift detected)
   → backtest the new model on 2014–2025 (walk-forward: train on the past, test on the next year)
   → train it on all data → register as a new version
   → PROMOTE to @champion only if:
        ✔ beats "same as this week" at 2 AND 4 weeks
        ✔ not more than 1% worse than the current champion
     otherwise → stays registered, tagged "rejected" + reason; the old champion keeps working
```

- **Data gate:** training refuses to run on fewer than 10,000 rows (a broken or half-built warehouse). It exits with code 2.
- **Why this matters:** retraining is automatic, but **nothing gets worse automatically**. A bad retrain is simply not promoted.

---

## 7. Forecasts: how they're produced and stored

`python -m src.ml.predict` (weekly in Airflow, and at the end of `src.pipeline`):
1. Loads `@champion` from MLflow.
2. Takes each region's **latest week** (regions more than 2 weeks behind are skipped with a warning).
3. Forecasts cases 2 and 4 weeks ahead → risk level (high / watch / normal / unknown).
4. Saves the forecasts to `ml.forecast_weekly`, **keeping all past forecasts**. Re-running the same week and model replaces rows, never duplicates them.

**Industry pattern: batch scoring.** The dashboard, API and alert read the **table**, not the model, so they stay fast and keep working when MLflow is off. `--soft` means: if MLflow is down, warn and continue.

---

## 8. Monitoring: does the model still work?

| Check | How | Where to see it |
|---|---|---|
| **Forecast vs actual** | When a forecast's week arrives, dbt joins it to the real cases and the naive forecast (`gold.mart_forecast_accuracy`) | Dashboard "Model health", `/model/health` |
| **Data drift** | `python -m src.ml.monitor`: Evidently compares the last 8 weeks of model inputs with the **same months in the past 5 years**. Alarm if ≥ 60% of inputs changed (calibrated: normal years 23–55%, 2017 = 64%, 2026 = 73%). | `ml.drift_runs`, `data/reports/drift/drift_<date>.html` (open in a browser: a full chart per input) |
| **Honest history** | `python -m src.ml.replay` rebuilds past forecasts using only the data available at the time | Fills Model health immediately |

When drift is detected → Airflow triggers `retrain_monthly` → the champion/challenger check from section 6.

---

## 9. Data quality: how bad data is stopped

| Where | Check | If it fails |
|---|---|---|
| Weather download | > 5% missing values, negative rain, min > max temperature, duplicate dates | Whole pull **rejected** |
| Weather API limit | HTTP 429 | Stops cleanly (exit 3); the next run continues where it left off |
| NDCU PDF | Region sums must equal the **printed Total** row; all 26 regions present; dates match the week | PDF moved to `data/quarantine/ndcu/`, **never loaded** |
| WER history | Unknown region names, negative or non-whole cases, duplicates | Load **stops** |
| dbt (~95 tests) | Unique keys, no nulls, valid ranges, links between tables, 26 regions per week, reconciliations, **no future data in features** | `dbt build` fails → forecasts and alert **don't run** |
| Cross-source | WER vs NDCU 2025 totals | Warning (known small differences) |

Plus **idempotency**: every step can be re-run safely. Re-running never duplicates data.

---

## 10. CI: automatic checks on GitHub

Every `git push` runs 4 jobs (`.github/workflows/ci.yml`):

| Job | Does |
|---|---|
| Lint + types + tests | ruff (style), mypy (types), pytest (~120 tests) |
| Pipeline on sample data | Builds small fake data + 3 real NDCU PDFs, then runs the **whole pipeline and all dbt checks** |
| Airflow DAG check | All DAGs load, and task order is correct |
| Web dashboard | `npm ci` + TypeScript type check + production build of `web/` |

🟢 badge on the README = everything passed. 🔴 = GitHub emails you, and you fix before merging.

---

## 11. What runs where (ports)

**Everything in one command:** `docker compose up -d` starts MLflow → runs setup once (`init`, `src/bootstrap.py`: data → dbt → model → forecasts, skips itself if already done) → starts the API and the dashboard (`web`: nginx serving the React app, forwarding `/api/*` to the API). Watch it with `docker compose logs -f init`; re-run it with `docker compose run --rm init --force`. Airflow is a separate stack (next row) because it's heavy and only needed for the weekly schedule.

| Service | Start | Address |
|---|---|---|
| Dashboard (React) | `docker compose up -d web`, or `cd web; npm run dev` for development | http://localhost:3000 |
| API | `uvicorn src.api.main:app` or `docker compose up -d api` | http://localhost:8000/docs |
| MLflow | `docker compose up -d mlflow` | http://localhost:5000 |
| Airflow | `docker compose -f docker-compose.airflow.yml up -d` | http://localhost:8080 |
| Warehouse | a file: `data/denguewatch.duckdb` | — |

---

## 12. When something goes wrong

| Problem | What happens automatically | What you do |
|---|---|---|
| WER / NDCU website down | Retries; only that DAG goes red | Nothing. It catches up next week. |
| A PDF fails validation | Quarantined, not loaded | Open it, fix the parser, add it as a test |
| A dbt data check fails | Pipeline stops; no forecast or alert | Airflow → dbt_build → Logs → fix the data or code → Clear |
| MLflow is off | Forecast skipped; cases-only alert still sent | `docker compose up -d mlflow` |
| New model is worse | Not promoted; old champion keeps running | Read the "reason" tag in MLflow |
| Drift detected | Retrain triggered | Check the drift HTML report; watch the next Model health |
| Telegram token leaked | — | @BotFather → `/revoke` → new token in `.env` |

---

## 13. Command cheat sheet

```powershell
# data
python -m src.pipeline                        # everything: parse → silver → dbt (+ forecasts if MLflow is up)
python -m src.extract.weather_backfill        # weather history (resumable)
python -m src.extract.ndcu                    # download new NDCU PDFs
# ML
python -m src.ml.backtest                     # compare models → MLflow
python -m src.ml.train                        # train → register → promote if better
python -m src.ml.predict                      # forecasts → ml.forecast_weekly
python -m src.ml.replay                       # honest past forecasts
python -m src.ml.monitor                      # drift check (+ --calibrate)
# outputs
python -m src.alerts.telegram --dry-run       # preview the message
docker compose up -d web                      # dashboard -> http://localhost:3000
uvicorn src.api.main:app --reload             # API
# quality
pytest ; ruff check . ; mypy src
```
