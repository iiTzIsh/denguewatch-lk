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
