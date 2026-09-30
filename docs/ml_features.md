# ML feature table: `gold.mart_ml_features`

**Grain:** one row per RDHS region (26) per WER week (2006 → 2026). This is the table the forecasting model trains on.

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
| Endemic channel | `endemic_mean_5y`, `endemic_sd_5y`, `endemic_years`, `endemic_threshold` | The same week in the previous 5 years (past only). Threshold = mean + 2 SD, needs ≥ 3 years |
| Rainfall | `rain_w0_mm` … `rain_w3_mm`, `rain_w4_7_mm`, `rain_w8_11_mm`, `rain_w12_15_mm` | Rain in the week itself, each of the 3 weeks before, then in 4-week blocks back to 15 weeks |
| Other weather | `rainy_days_4w` (days with ≥ 1 mm), `temp_mean_4w_c`, `temp_min_4w_c` | Last 28 days |
| Targets | `target_cases_h2`, `target_cases_h4`, `target_threshold_h2`, `target_threshold_h4` | Cases 2 and 4 weeks later, and the endemic threshold of that week (the outbreak label) |

## Why these lags (sources)

The Sri Lankan studies don't agree on a single rainfall lag, so the model gets 0–15 weeks and the walk-forward backtest decides which help:

- Goto et al. 2013 (Colombo, Ratnapura, Anuradhapura, 2005–2011): VAR lag orders of 3–4 weeks; rainfall effect weak (p ≈ 0.05). [PLOS One](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0063717)
- Withanage et al. 2018 (Gampaha): monthly model using rainfall, rainy days and minimum temperature lagged 3 months; forecasts 1 month ahead. [Parasites & Vectors](https://link.springer.com/article/10.1186/s13071-018-2828-2)
- Prabodanie et al. 2020 (Colombo, Batticaloa, 2009–2017): "most recent available incidence data performed as best explanatory variables, outweighing the importance of past weather data." [Science of the Total Environment](https://www.sciencedirect.com/science/article/abs/pii/S0048969720317824)

## Known limits

- Region names map to districts, so Kalmunai uses Ampara district weather.
- No population data yet, so the table uses case counts, not rates per 100,000.
- 2026 WER weeks are Mon→Sun, so `week` numbers there are ISO weeks. The endemic channel compares week N with week N and ignores that one-to-two-day shift.
- Reporting delay isn't modelled yet: WER publishes a week's cases after that week ends.

## Backtest results (walk-forward, test years 2014–2025, 26 regions, 16,250 region-weeks)

The model predicts **growth**: log(cases in h weeks + 1) − log(recent 4-week level + 1). Case features are log ratios to that level, so one model fits big and small regions. See `src/ml/models.py`.

| Model | h=2 MAE | h=2 skill vs naive | h=4 MAE | h=4 skill vs naive |
|---|---|---|---|---|
| Last value (naive) | 15.49 | 0 | 21.62 | 0 |
| Mean of last 4 weeks | 18.08 | −17% | 23.71 | −10% |
| Same week last year | 42.31 | −173% | 42.39 | −96% |
| LightGBM, no weather | 15.16 | +2.1% | 19.51 | +9.7% |
| **LightGBM + weather** | **14.97** | **+3.4%** | **18.97** | **+12.3%** |

What this shows:
- Recent cases are the strongest signal. At 2 weeks, "same as this week" is hard to beat.
- **Weather adds the most at 4 weeks** (+2.6 points of skill over the no-weather model).
- At h=4, **rain 12–15 weeks earlier** is the second-highest feature by gain (≈10%). That's close to the 3-month lag in Withanage et al. 2018. Gain shows what the model uses, not what causes cases.
- Outbreak calls: LightGBM is more **precise** (fewer false alarms: 0.83 vs 0.71 at h=2) but catches fewer outbreak weeks (recall 0.66 vs 0.74).

Known issue: the current outbreak rule (5-year mean + 2 SD) marks ~17% of weeks as outbreaks, which is too many to be useful as an alert. To revisit before alerts use the forecast.

Reproduce: `python -m src.ml.backtest`. Every number above is a run in the MLflow experiment `denguewatch-forecast`.
