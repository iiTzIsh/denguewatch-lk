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

-- CASES = WER history (2006 -> its last week) + NDCU weekly updates AFTER that, so the model can forecast
-- from the newest data. NDCU (latest, restated counts) uses the same 26 regions and Mon->Sun weeks as
-- 2026 WER. Known gap: in the 3 overlapping 2026 weeks NDCU is 5-11% higher than WER (2025 cumulative:
-- 2-3.5%) - kept as-is and tagged in case_source, never silently rescaled.
with wer as (
    select rdhs, district, wer_week_key, year, week, week_start, week_end, cases, 'WER' as case_source
    from {{ ref('stg_wer_weekly') }}
    where district is not null
),

ndcu as (
    select
        s.rdhs, s.district, s.iso_week_key as wer_week_key, s.year, s.iso_week as week,
        s.week_start, s.week_end, f.cases_latest as cases, 'NDCU' as case_source
    from {{ ref('stg_ndcu_weekly') }} s
    join {{ ref('fact_dengue_ndcu_weekly') }} f using (rdhs, week_start)
    where s.district is not null
      and s.week_start > (select max(week_end) from wer)
),

cases as (
    select * from wer
    union all by name
    select * from ndcu
),

-- ENDEMIC CHANNEL ("what is normal for this region at this time of year")
-- For an anchor date A: all weeks of the same region that ended within +-17 days of A minus 1..5 years
-- (up to 5 years x 5 weeks = 25 values, all strictly in the past). Computed for three anchors:
--   offset 0  -> this week          (feature + monitoring)
--   offset 14 -> the week 2 weeks on (outbreak threshold for the h=2 forecast)
--   offset 28 -> the week 4 weeks on (outbreak threshold for the h=4 forecast)
-- Threshold = exp(mean(log(cases+1)) + 2 SD) - 1, at least 10 cases, needs >= 10 past values.
-- Log scale because counts are skewed; the 10-case floor stops tiny regions "breaking out" at 3 cases.
-- Backtest 2014-2025: flags ~8% of weeks overall, ~60% in the 2017 epidemic, 0-2% in quiet years.
anchors as (
    select c.rdhs, c.week_start, c.week_end + to_days(o.offset_days) as anchor_end, o.offset_days
    from cases c
    cross join (values (0), (14), (28)) as o(offset_days)
),

endemic_long as (
    select
        a.rdhs,
        a.week_start,
        a.offset_days,
        avg(p.cases)                   as mean_cases,
        stddev_samp(p.cases)           as sd_cases,
        avg(ln(p.cases + 1))           as mean_log,
        stddev_samp(ln(p.cases + 1))   as sd_log,
        count(p.cases)                 as n_values
    from anchors a
    join cases p
        on p.rdhs = a.rdhs
       and p.week_end between a.anchor_end - interval 1837 day and a.anchor_end - interval 347 day
       and (date_diff('day', p.week_end, a.anchor_end) + 17) % 364 <= 34
    group by a.rdhs, a.week_start, a.offset_days
),

endemic as (
    select
        rdhs,
        week_start,
        max(mean_cases) filter (where offset_days = 0)   as endemic_mean_5y,
        max(sd_cases)   filter (where offset_days = 0)   as endemic_sd_5y,
        max(n_values)   filter (where offset_days = 0)   as endemic_n_values,
        {% for (name, off) in [('endemic_threshold', 0), ('target_threshold_h2', 14), ('target_threshold_h4', 28)] %}
        max(case when n_values >= 10 then greatest(exp(mean_log + 2 * sd_log) - 1, 10) end)
            filter (where offset_days = {{ off }})       as {{ name }}{{ "," if not loop.last }}
        {% endfor %}
    from endemic_long
    group by rdhs, week_start
),

sequenced as (
    select
        c.*,
        e.endemic_mean_5y,
        e.endemic_sd_5y,
        e.endemic_n_values,
        e.endemic_threshold,
        e.target_threshold_h2,
        e.target_threshold_h4,
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
             then lead(c.cases, 4) over w end                                          as target_cases_h4
    from cases c
    left join endemic e using (rdhs, week_start)
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
    s.wer_week_key,                                       -- week key (WER, or NDCU ISO week after WER ends)
    s.case_source,
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
    s.endemic_n_values,
    s.endemic_threshold,
    w.rain_w0_mm, w.rain_w1_mm, w.rain_w2_mm, w.rain_w3_mm,
    w.rain_w4_7_mm, w.rain_w8_11_mm, w.rain_w12_15_mm,
    w.rainy_days_4w,
    w.temp_mean_4w_c,
    w.temp_min_4w_c,
    s.target_cases_h2,
    s.target_cases_h4,
    s.target_threshold_h2,                                -- known in advance (history only), so the
    s.target_threshold_h4,                                -- latest week has one too -> used by alerts
    cast(current_timestamp as timestamp)                  as load_ts
from sequenced s
left join weather w using (rdhs, week_start)
