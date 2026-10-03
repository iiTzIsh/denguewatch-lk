# Forecasting

## Feature table: `gold.mart_ml_features`

One row per RDHS region (26) per week: WER history from 2006 to May 2026, then NDCU weekly updates after the WER
history ends. The model trains and scores from this table.

Rules:

1. **No leakage.** Features use only data up to the row's `week_end`; only `target_*` columns look forward.
2. **Date-checked lags.** "2 weeks ago" must be 14 +- 3 days earlier, otherwise the value is NULL, so a missing
   week cannot shift the series.
3. **No partial sums.** A weather window with a missing day is NULL.
4. **Week-system independent.** Windows are counted in days back from `week_end`, so they work for Saturday-Friday
   (up to 2025) and Monday-Sunday (2026) weeks.

| Group | Columns | Meaning |
|---|---|---|
| Keys | `rdhs`, `district`, `district_sk`, `wer_week_key`, `week_start`, `week_end`, `year`, `week`, `month` | region and week |
| Recent cases | `cases`, `cases_lag1..4`, `cases_mean_4w`, `cases_mean_8w` | the strongest predictor in Prabodanie et al. 2020 |
| Seasonality | `cases_same_week_last_year`, `month` | monsoon-driven yearly cycle |
| Endemic channel | `endemic_mean_5y`, `endemic_sd_5y`, `endemic_n_values`, `endemic_threshold` | weeks within +-17 days of the same date in each of the previous 5 years |
| Source | `case_source` | `WER` or `NDCU` |
| Rainfall | `rain_w0_mm` ... `rain_w3_mm`, `rain_w4_7_mm`, `rain_w8_11_mm`, `rain_w12_15_mm` | the week itself, each of the 3 weeks before, then 4-week blocks back to 15 weeks |
| Other weather | `rainy_days_4w`, `temp_mean_4w_c`, `temp_min_4w_c` | last 28 days |
| Targets | `target_cases_h2`, `target_cases_h4` | cases 2 and 4 weeks later |
| Target outbreak level | `target_threshold_h2`, `target_threshold_h4` | outbreak level of the target week; uses history only, so it exists for the latest week |

The Sri Lankan literature does not agree on a single rainfall lag, so the model sees 0-15 weeks and the backtest
decides what helps:

- Goto et al. 2013 (Colombo, Ratnapura, Anuradhapura): lag orders of 3-4 weeks, weak rainfall effect.
  [PLOS One](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0063717)
- Withanage et al. 2018 (Gampaha): rainfall, rainy days and minimum temperature lagged 3 months.
  [Parasites & Vectors](https://link.springer.com/article/10.1186/s13071-018-2828-2)
- Prabodanie et al. 2020 (Colombo, Batticaloa): recent incidence outweighs past weather.
  [Science of the Total Environment](https://www.sciencedirect.com/science/article/abs/pii/S0048969720317824)

## Model and backtest

The model predicts growth, `log(cases in h weeks + 1) - log(recent 4-week level + 1)`, from scale-free features
(log ratios to that level), so one LightGBM model fits large and small regions (`src/ml/models.py`).

Walk-forward backtest: train on all earlier years, test on the next, for 2014-2025 (26 regions, 16,250
region-weeks). Mean absolute error in weekly cases:

| Model | h=2 MAE | skill vs naive | h=4 MAE | skill vs naive |
|---|---|---|---|---|
| Last value (naive) | 15.49 | 0 | 21.62 | 0 |
| Mean of last 4 weeks | 18.08 | -17% | 23.71 | -10% |
| Same week last year | 42.31 | -173% | 42.39 | -96% |
| LightGBM, no weather | 15.25 | +1.6% | 19.59 | +9.4% |
| **LightGBM + weather** | **15.03** | **+3.0%** | **18.99** | **+12.1%** |

- Recent cases carry most of the signal; at 2 weeks the naive forecast is hard to beat.
- Weather adds the most at 4 weeks (+2.6 points of skill).
- At h=4, rain 12-15 weeks earlier is the second most important feature by gain (about 10%), close to the
  3-month lag reported by Withanage et al. Gain shows what the model uses, not causation.

Reproduce with `python -m src.ml.backtest`; every number is a run in the MLflow experiment `denguewatch-forecast`.

## Outbreak rule and alert threshold (`src/ml/risk.py`)

Outbreak level = `exp(mean(log(cases + 1)) + 2 * sd) - 1` over the endemic-channel values, at least 10 cases,
requiring at least 10 values. It flags 7.9% of region-weeks overall, 59% during the 2017 epidemic and 0-2% in quiet
years. A plain same-week mean + 2 SD rule flagged about 17% of weeks, too many for an alert.

Because the model under-forecasts peaks, the alert ("watch") fires at 80% of the outbreak level. 0.8 gave the best
F1 at both horizons in the backtest:

| LightGBM, 2014-2025 | at 100% of level (recall / precision) | **at 80% (recall / precision)** |
|---|---|---|
| 2 weeks ahead | 0.56 / 0.84 | **0.70 / 0.73** |
| 4 weeks ahead | 0.44 / 0.77 | **0.58 / 0.67** |

The ratio was chosen on the same period it is scored on, so these figures are slightly optimistic. In 2020-2025
there were few outbreaks and precision is lower (about 0.36 at h=2).

## Out-of-sample: the 2026 epidemic

A model trained only on data up to 17 May 2026 forecast the NDCU weeks from 18 May to 7 Sep 2026 (about 1,200
cases a week in April, peaking at 7,891 in the week of 29 June).

| Jun-Sep 2026 | h=2 MAE | h=4 MAE | alert precision (h=4) |
|---|---|---|---|
| Naive | 65.9 | 121.0 | 0.46 |
| **LightGBM** | **48.5 (-26%)** | **68.0 (-44%)** | **0.66** |

It forecast the decline after the July peak, where the naive forecast kept predicting the peak. It under-forecast
the start of the rise: from the week of 18 May it predicted about 2,300 national cases for mid-June against an
actual 5,238.

## Training, registry and scoring (`src/ml/train.py`, `src/ml/predict.py`)

```
backtest 2014-2025 -> fit on all weeks -> log pyfunc to MLflow -> register a new version of denguewatch-forecaster
  -> promote to @champion only if it beats naive at h=2 and h=4 and is <= 1% worse than the current champion
  -> the previous champion keeps @previous_champion for rollback
```

- One pyfunc model covers both horizons and carries the feature code (`code_paths=src`).
- Callers pass `serving_frame(rows)`: an explicit schema of 23 float columns, NaN allowed.
- Weekly batch scoring writes to `ml.forecast_weekly` (history kept, idempotent per base week and model version);
  `ml.forecast_latest` is the newest batch. Consumers read the table, not the model.
- Training stops with exit code 2 on fewer than 10,000 labelled rows.
- `retrain_monthly` runs at 09:00 on the 1st of each month and when drift is detected.

## Monitoring

**Forecast vs actual.** `gold.mart_forecast_accuracy` joins each forecast whose target week has passed to the
actual cases and the naive forecast. `python -m src.ml.replay` rebuilds the last 16 weeks as-of each week (each
model trained only on data available then):

| As-of replay, Jun-Sep 2026 | Forecasts | MAE | Naive MAE | Skill | Alerts correct | Outbreak weeks caught |
|---|---|---|---|---|---|---|
| 2 weeks ahead | 364 | 48.6 | 67.6 | **+28%** | 105/146 (72%) | 105/139 (76%) |
| 4 weeks ahead | 312 | 63.6 | 120.8 | **+47%** | 79/123 (64%) | 79/120 (66%) |

**Data drift (Evidently).** Each week the last 8 weeks of model inputs are compared with the same months in the
previous five years, because dengue and weather are seasonal. A feature drifts if its normalised Wasserstein
distance is at least 0.3. Evidently's default of 0.1 flagged every feature even in normal years, so the alarm
threshold is calibrated on history (`python -m src.ml.monitor --calibrate`):

| Mid-September check | 2014 | 2015 | 2016 | **2017** | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | **2026** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Share of features drifted | .32 | .32 | .55 | **.64** | .59 | .23 | .36 | .50 | .45 | .50 | .36 | .50 | **.73** |

The alarm fires at a share of 0.60 or more (about the 90th percentile); only the two epidemic years reach it. A
drift alarm triggers `retrain_monthly`, and the champion/challenger gate decides whether the new model is used.

## Limitations

- RDHS regions map to districts for weather, so Kalmunai uses Ampara district weather.
- Forecasts are in case counts: Census 2024 population is published per district, not per RDHS region.
- 2026 WER weeks are Monday-Sunday; the endemic channel compares week N with week N and ignores the 1-2 day shift.
- Reporting delay is not modelled.
- WER to NDCU switch: over the 20 overlapping 2026 weeks, weekly counts differ by -9% to +17% (median +6%, +3.3% in
  total). Values are kept as published and tagged in `case_source`.
