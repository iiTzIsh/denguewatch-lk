-- Grain: one row per district per ISO week that NDCU reported.
-- Cases (and per 100k, Census 2024), this week's weather, and rainfall 1-4 weeks earlier (breeding delay).
-- Rain lags are computed on the full weather history first, so they only look backwards.
with rain as (
    select
        district_sk,
        week_start,
        rainfall_mm_total,
        temp_mean_c,
        lag(rainfall_mm_total, 1) over w as rain_lag1_mm,
        lag(rainfall_mm_total, 2) over w as rain_lag2_mm,
        lag(rainfall_mm_total, 3) over w as rain_lag3_mm,
        lag(rainfall_mm_total, 4) over w as rain_lag4_mm
    from {{ ref('fact_weather_iso_weekly') }}
    window w as (partition by district_sk order by week_start)
),
cases as (
    select district_sk, iso_week_key, min(week_start) as week_start,
           sum(cases_latest) as cases, bool_or(is_restated) as any_restated
    from {{ ref('fact_dengue_ndcu_weekly') }}
    group by district_sk, iso_week_key          -- Ampara + Kalmunai RDHS -> Ampara district
)
select
    c.district_sk,
    dd.district,
    dd.province,
    c.iso_week_key,
    c.week_start,
    c.cases,
    pop.population,
    round(c.cases * 100000.0 / pop.population, 1)                       as cases_per_100k,   -- NULL until census loaded
    -- only vs the directly preceding week (NDCU skipped some, e.g. 2026-W18 and W20)
    case when lag(c.week_start) over wc = c.week_start - 7
         then c.cases - lag(c.cases) over wc end                        as cases_change_vs_prev_week,
    c.any_restated,
    r.rainfall_mm_total,
    r.temp_mean_c,
    r.rain_lag1_mm, r.rain_lag2_mm, r.rain_lag3_mm, r.rain_lag4_mm
from cases c
join {{ ref('dim_district') }} dd using (district_sk)
left join rain r on r.district_sk = c.district_sk and r.week_start = c.week_start
left join {{ source('silver', 'district_population') }} pop on pop.district = dd.district
window wc as (partition by c.district_sk order by c.week_start)
