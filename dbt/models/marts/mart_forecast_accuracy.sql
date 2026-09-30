-- GRAIN: one forecast (region x base week x horizon x model version) whose target week has happened.
-- Forecast vs actual, next to the naive "same as this week" forecast, so model health = "still beating naive?"
-- Forecasts come from src.ml.predict (live @champion) and src.ml.replay (as-of replay, no hindsight).
with forecasts as (
    select * from {{ source('ml', 'forecast_weekly') }}
),

actuals as (
    select rdhs, week_end, cases, case_source
    from {{ ref('mart_ml_features') }}
)

select
    f.rdhs,
    f.district,
    f.model_name,
    f.model_version,
    f.horizon_weeks,
    f.base_week_end,
    f.target_week_end,
    f.cases_now                                   as naive_pred_cases,
    f.pred_cases,
    a.cases                                       as actual_cases,
    a.case_source                                 as actual_source,
    abs(f.pred_cases - a.cases)                   as abs_error,
    abs(f.cases_now - a.cases)                    as naive_abs_error,
    f.outbreak_level,
    f.risk_level,
    f.risk_level in ('high', 'watch')             as alerted,
    coalesce(a.cases > f.outbreak_level, false)   as outbreak_happened,
    f.scored_at
from forecasts f
join actuals a
  on a.rdhs = f.rdhs
 and a.week_end between f.target_week_end - interval 3 day and f.target_week_end + interval 3 day
