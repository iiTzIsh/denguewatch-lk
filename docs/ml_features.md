# ML feature table: `gold.mart_ml_features`

**Grain:** one row per RDHS region (26) per week: WER history 2006 → May 2026, then NDCU weekly updates after WER ends. This is the table the forecasting model trains on and scores from.

## Rules

1. **No leakage.** Every feature uses only data up to `week_end` of that row. Only the `target_*` columns look forward.
2. **Date-checked lags.** "2 weeks ago" must really be 14 ± 3 days earlier. Otherwise the value is NULL, so a missing week can't shift the data.
3. **No partial sums.** A weather window with any missing day is NULL.
4. **Both week systems work.** Windows are counted in days back from `week_end`, so they fit Sat→Fri (≤2025) and Mon→Sun (2026) weeks.

## Columns

| Group | Columns | Meaning |
|---|---|---|
| Keys | `rdhs`, `district`, `district_sk`, `wer_week_key`, `week_start`, `week_end`, `year`, `week`, `month` | Which region and week |
| Recent cases | `cases`, `cases_lag1..4`, `cases_mean_4w`, `cases_mean_8w` | Recent cases were the strongest predictor in Prabodanie et al. 2020 |
| Seasonality | `cases_same_week_last_year`, `month` | Monsoon-driven yearly cycle |
| Endemic channel | `endemic_mean_5y`, `endemic_sd_5y`, `endemic_n_values`, `endemic_threshold` | Weeks within ±17 days of the same date in each of the previous 5 years (up to 25 values, past only). **Outbreak level** = exp(mean(log(cases+1)) + 2 SD) − 1, at least 10 cases, needs ≥ 10 values |
| Source | `case_source` | `WER` or `NDCU` |
| Rainfall | `rain_w0_mm` … `rain_w3_mm`, `rain_w4_7_mm`, `rain_w8_11_mm`, `rain_w12_15_mm` | Rain in the week itself, each of the 3 weeks before, then in 4-week blocks back to 15 weeks |
| Other weather | `rainy_days_4w` (days with ≥ 1 mm), `temp_mean_4w_c`, `temp_min_4w_c` | Last 28 days |
| Targets | `target_cases_h2`, `target_cases_h4` | Cases 2 and 4 weeks later |
| Outbreak level of the target week | `target_threshold_h2`, `target_threshold_h4` | Same rule, anchored 14 / 28 days ahead. It uses history only, so it exists for the **latest** week too, and the alert can use it |

## Why these lags (sources)

The Sri Lankan studies don't agree on a single rainfall lag, so the model gets 0–15 weeks and the walk-forward backtest decides which help:

- Goto et al. 2013 (Colombo, Ratnapura, Anuradhapura, 2005–2011): VAR lag orders of 3–4 weeks; rainfall effect weak (p ≈ 0.05). [PLOS One](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0063717)
- Withanage et al. 2018 (Gampaha): monthly model using rainfall, rainy days and minimum temperature lagged 3 months; forecasts 1 month ahead. [Parasites & Vectors](https://link.springer.com/article/10.1186/s13071-018-2828-2)
- Prabodanie et al. 2020 (Colombo, Batticaloa, 2009–2017): "most recent available incidence data performed as best explanatory variables, outweighing the importance of past weather data." [Science of the Total Environment](https://www.sciencedirect.com/science/article/abs/pii/S0048969720317824)

## Known limits

- Region names map to districts, so Kalmunai uses Ampara district weather.
- The model uses case counts. Census 2024 population exists per **district** (used for the dashboard's per-100,000 rates), but not per RDHS region, so the forecasts stay in counts.
- 2026 WER weeks are Mon→Sun, so `week` numbers there are ISO weeks. The endemic channel compares week N with week N and ignores that one-to-two-day shift.
- Reporting delay isn't modelled yet: WER publishes a week's cases after that week ends.
- WER → NDCU switch: in the 3 overlapping 2026 weeks, NDCU weekly counts are 5–11% higher than WER (the 2025 cumulative differs by 2–3.5%). Values are kept as published and tagged in `case_source`, never rescaled.

## Backtest results (walk-forward, test years 2014–2025, 26 regions, 16,250 region-weeks)

The model predicts **growth**: log(cases in h weeks + 1) − log(recent 4-week level + 1). Case features are log ratios to that level, so one model fits big and small regions. See `src/ml/models.py`.

| Model | h=2 MAE | h=2 skill vs naive | h=4 MAE | h=4 skill vs naive |
|---|---|---|---|---|
| Last value (naive) | 15.49 | 0 | 21.62 | 0 |
| Mean of last 4 weeks | 18.08 | −17% | 23.71 | −10% |
| Same week last year | 42.31 | −173% | 42.39 | −96% |
| LightGBM, no weather | 15.25 | +1.6% | 19.59 | +9.4% |
| **LightGBM + weather** | **15.03** | **+3.0%** | **18.99** | **+12.1%** |

What this shows:
- Recent cases are the strongest signal. At 2 weeks, "same as this week" is hard to beat.
- **Weather adds the most at 4 weeks** (+2.6 points of skill over the no-weather model).
- At h=4, **rain 12–15 weeks earlier** is the second-highest feature by gain (≈10%). That's close to the 3-month lag in Withanage et al. 2018. Gain shows what the model uses, not what causes cases.
### Outbreak rule and alert operating point (`src/ml/risk.py`)
The first rule (same week number, mean + 2 SD) flagged ~17% of all weeks. That's too many for an alert. The current rule (log scale, ±2 weeks × 5 years, ≥ 10 cases) flags **7.9%** of weeks overall, **59% in the 2017 epidemic** and 0–2% in quiet years.

The model under-forecasts peaks, so the alert fires at **80% of the outbreak level** ("watch"), not 100%. 0.8 gave the best F1 at both horizons in the backtest:

| LightGBM, 2014–2025 | Alerts at 100% of level (recall / precision) | **Alerts at 80% (recall / precision)** |
|---|---|---|
| 2 weeks ahead | 0.56 / 0.84 | **0.70 / 0.73** |
| 4 weeks ahead | 0.44 / 0.77 | **0.58 / 0.67** |

The ratio was chosen on the same period it is scored on, so treat these numbers as slightly optimistic. After COVID (2020–2025) there were few outbreaks and alert precision is much lower (~0.36 at h=2).

### Out-of-sample: the 2026 epidemic
A model trained **only on data up to 17 May 2026** forecast the NDCU weeks from 18 May to 7 Sep 2026 (a large epidemic: about 1,200 cases a week in April, a peak of 7,891 in the week of 29 June). It never saw these weeks.

| Jun–Sep 2026 | h=2 MAE | h=4 MAE | alert precision (h=4) |
|---|---|---|---|
| Naive | 65.9 | 121.0 | 0.46 |
| **LightGBM** | **48.5 (−26%)** | **68.0 (−44%)** | **0.66** |

It forecast the **decline after the July peak** (naive keeps predicting the peak). It **under-forecast the start of the rise**: from the week of 18 May it predicted about 2,300 national cases for mid-June, and the real number was 5,238.

Reproduce: `python -m src.ml.backtest`. Every number above is a run in the MLflow experiment `denguewatch-forecast`.

## Training, registry and promotion (`src/ml/train.py`)

```
backtest (2014–2025) → fit on all weeks → log pyfunc to MLflow → register new version of denguewatch-forecaster
      → promote to @champion only if:  beats naive at h=2 AND h=4  AND  ≤ 1% worse MAE than the current champion
      → old champion keeps @previous_champion (rollback = move the alias back)
```

- **One model, both horizons.** A pyfunc wrapper carries the feature code (`code_paths=src`), so the API, dashboard and alert just call `predict()`.
- **Explicit input schema.** Callers pass `serving_frame(rows)`: 23 float columns, with NaN allowed.
- **Batch scoring** (`src/ml/predict.py`, weekly in Airflow and at the end of `src.pipeline`): the champion forecasts each region's latest week and writes to `ml.forecast_weekly` (all history kept, idempotent per week + model version). The view `ml.forecast_latest` holds the newest batch. The dashboard, API and alert read this table only, so they don't need MLflow. `--soft` skips with a warning if MLflow is down, and the cases-only alert still goes out.
- **Data gate.** Training refuses to run with fewer than 10,000 labelled rows (e.g. a half-built warehouse). It exits with code 2.
- **Schedule.** Airflow `retrain_monthly` runs at 09:00 on the 1st of each month in its own ML virtualenv.
- **Load the champion:** `mlflow.pyfunc.load_model("models:/denguewatch-forecaster@champion")`

## Monitoring (`src/ml/monitor.py`, `src/ml/replay.py`, `gold.mart_forecast_accuracy`)

**1. Forecast vs actual.** Every forecast is stored, and once its target week has happened, dbt joins it to the actual cases. The dashboard, `GET /model/health` and the table `gold.mart_forecast_accuracy` show the error next to the naive forecast. *Is the model still better than "same as this week"?*

To start with real history instead of waiting months, `python -m src.ml.replay` rebuilds the last 16 weeks **as-of**: each week's model is trained only on data available at that time (no hindsight). Results for Jun–Sep 2026:

| As-of replay 2026 | Forecasts | MAE | Naive MAE | Skill | Alerts correct | Outbreak weeks caught |
|---|---|---|---|---|---|---|
| 2 weeks ahead | 364 | 48.6 | 67.6 | **+28%** | 105/146 (72%) | 105/139 (76%) |
| 4 weeks ahead | 312 | 63.6 | 120.8 | **+47%** | 79/123 (64%) | 79/120 (66%) |

The stale forecast made from mid-May data (before the NDCU feed was added) shows up here too: 8 outbreak weeks missed. This is the kind of problem monitoring exists to expose.

**2. Data drift (Evidently).** Every week, the last 8 weeks of model inputs are compared with the **same months in the previous 5 years**, because dengue and weather are seasonal. Each feature is tested with the normalised Wasserstein distance (drifted if ≥ 0.3).

Evidently's default setting (0.1) flagged 22/22 features even in a normal year, so the alarm is **calibrated on history** (`python -m src.ml.monitor --calibrate`):

| Year (mid-Sep check) | 2014 | 2015 | 2016 | **2017** | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | **2026** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Share of features drifted | .32 | .32 | .55 | **.64** | .59 | .23 | .36 | .50 | .45 | .50 | .36 | .50 | **.73** |

Alarm at **≥ 0.60** (≈ 90th percentile). Only the two epidemic years reach it. When it fires, the weekly DAG triggers `retrain_monthly`. The champion/challenger gate then decides whether the retrained model replaces the current one, so drift never pushes a worse model into production. Each check writes a row to `ml.drift_runs` and an HTML report to `data/reports/drift/`.
