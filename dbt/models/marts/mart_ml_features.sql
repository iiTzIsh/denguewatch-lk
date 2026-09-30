-- GRAIN: one row per RDHS region per WER week. This is the table the forecasting model trains on.
--
-- Rule: every FEATURE uses only data up to the END of that week (week_end) -> no future leakage.
--       TARGETS are the cases 2 and 4 weeks later (what we want to predict).
--
-- Weeks are matched by position (row order per region), and every lag/lead is checked against the real
-- dates (+-3 days) so a missing week can never make "2 weeks ago" silently mean 3 weeks ago.
-- Weather windows are counted in DAYS back from week_end, so they work for both Sat->Fri (<=2025)
-- and Mon->Sun (2026) weeks. A window with any missing day is NULL (never a partial sum).
--
-- Lags: Sri Lankan studies report different rainfall lags (about 3-4 weeks in Goto et al. 2013,
-- about 3 months in Withanage et al. 2018), so we give the model 0-15 weeks and let the backtest decide.

{% set case_lags = [1, 2, 3, 4] %}

with cases as (
    select rdhs, district, wer_week_key, year, week, week_start, week_end, cases
    from {{ ref('stg_wer_weekly') }}
    where district is not null
),

-- endemic channel: same region, same week number, previous 5 years (past only)
endemic as (
    select
        c.rdhs,
        c.week_start,
        avg(p.cases)          as endemic_mean_5y,
        stddev_samp(p.cases)  as endemic_sd_5y,
        count(p.cases)        as endemic_years
    from cases c
    left join cases p
        on p.rdhs = c.rdhs and p.week = c.week and p.year between c.year - 5 and c.year - 1
    group by c.rdhs, c.week_start
),

sequenced as (
    select
        c.*,
        e.endemic_mean_5y,
        e.endemic_sd_5y,
        e.endemic_years,
        case when e.endemic_years >= 3 then e.endemic_mean_5y + 2 * e.endemic_sd_5y end as endemic_threshold,
        {% for k in case_lags %}
        case when date_diff('day', lag(c.week_end, {{ k }}) over w, c.week_end) between {{ 7 * k - 3 }} and {{ 7 * k + 3 }}
             then lag(c.cases, {{ k }}) over w end                                     as cases_lag{{ k }},
        {% endfor %}
        case when date_diff('day', lag(c.week_end, 52) over w, c.week_end) between 357 and 371
             then lag(c.cases, 52) over w end                                          as cases_same_week_last_year,
        case when date_diff('day', lag(c.week_end, 3) over w, c.week_end) between 18 and 24
             then avg(c.cases) over (w rows between 3 preceding and current row) end   as cases_mean_4w,
        case when date_diff('day', lag(c.week_end, 7) over w, c.week_end) between 46 and 52
             then avg(c.cases) over (w rows between 7 preceding and current row) end   as cases_mean_8w,
        -- targets
        case when date_diff('day', c.week_end, lead(c.week_end, 2) over w) between 11 and 17
             then lead(c.cases, 2) over w end                                          as target_cases_h2,
        case when date_diff('day', c.week_end, lead(c.week_end, 4) over w) between 25 and 31
             then lead(c.cases, 4) over w end                                          as target_cases_h4,
        lead(c.week_start, 2) over w                                                   as _lead_start_2,
        lead(c.week_start, 4) over w                                                   as _lead_start_4
    from cases c
    join endemic e using (rdhs, week_start)
    window w as (partition by c.rdhs order by c.week_start)
),

weather_days as (
    -- d = days before week_end (0 = the last day of the week)
    select
        c.rdhs,
        c.week_start,
        date_diff('day', x.date, c.week_end) as d,
        x.rainfall_mm,
        x.temp_mean_c,
        x.temp_min_c
    from cases c
    join {{ source('silver', 'weather_daily') }} x
        on x.district = c.district
       and x.date between c.week_end - interval 111 day and c.week_end
),

weather as (
    select
        x.rdhs,
        x.week_start,
        {% for (name, lo, hi) in [('w0', 0, 6), ('w1', 7, 13), ('w2', 14, 20), ('w3', 21, 27),
                                  ('w4_7', 28, 55), ('w8_11', 56, 83), ('w12_15', 84, 111)] %}
        case when count_if(d between {{ lo }} and {{ hi }} and x.rainfall_mm is not null) = {{ hi - lo + 1 }}
             then round(sum(x.rainfall_mm) filter (where d between {{ lo }} and {{ hi }}), 1) end as rain_{{ name }}_mm,
        {% endfor %}
        case when count_if(d between 0 and 27 and x.rainfall_mm is not null) = 28
             then count_if(d between 0 and 27 and x.rainfall_mm >= 1) end                     as rainy_days_4w,
        case when count_if(d between 0 and 27 and x.temp_mean_c is not null) = 28
             then round(avg(x.temp_mean_c) filter (where d between 0 and 27), 2) end           as temp_mean_4w_c,
        case when count_if(d between 0 and 27 and x.temp_min_c is not null) = 28
             then round(avg(x.temp_min_c) filter (where d between 0 and 27), 2) end            as temp_min_4w_c
    from weather_days x
    group by x.rdhs, x.week_start
)

select
    s.rdhs,
    s.district,
    md5(s.district)                                      as district_sk,
    s.wer_week_key,
    s.year,
    s.week,
    s.week_start,
    s.week_end,
    month(s.week_end)                                    as month,
    s.cases,
    {% for k in case_lags %}s.cases_lag{{ k }},
    {% endfor %}
    s.cases_mean_4w,
    s.cases_mean_8w,
    s.cases_same_week_last_year,
    s.endemic_mean_5y,
    s.endemic_sd_5y,
    s.endemic_years,
    s.endemic_threshold,
    w.rain_w0_mm, w.rain_w1_mm, w.rain_w2_mm, w.rain_w3_mm,
    w.rain_w4_7_mm, w.rain_w8_11_mm, w.rain_w12_15_mm,
    w.rainy_days_4w,
    w.temp_mean_4w_c,
    w.temp_min_4w_c,
    s.target_cases_h2,
    s.target_cases_h4,
    e2.endemic_threshold                                  as target_threshold_h2,
    e4.endemic_threshold                                  as target_threshold_h4,
    cast(current_timestamp as timestamp)                  as load_ts
from sequenced s
left join weather w using (rdhs, week_start)
left join sequenced e2 on e2.rdhs = s.rdhs and e2.week_start = s._lead_start_2 and s.target_cases_h2 is not null
left join sequenced e4 on e4.rdhs = s.rdhs and e4.week_start = s._lead_start_4 and s.target_cases_h4 is not null
