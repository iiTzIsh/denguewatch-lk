{{ config(severity='warn') }}
-- CROSS-SOURCE CHECK: two independent government sources should roughly agree.
-- Each NDCU weekly PDF prints last year's (2025) cumulative cases up to that week; WER history has 2025 week by week.
-- Weeks differ by ~2 days and the reporting systems differ, so allow 5% (observed: mostly 2-3%).
with ndcu as (
    select year, iso_week, max(week_end) as week_end, sum(cum_prev_year) as ndcu_cum_2025
    from {{ source('silver', 'ndcu_weekly_cases') }}
    where year = 2026
    group by 1, 2
),
compared as (
    select n.iso_week, n.ndcu_cum_2025,
           (select sum(w.cases) from {{ ref('stg_wer_weekly') }} w
             where w.year = 2025 and w.week_end <= n.week_end - interval 1 year) as wer_cum_2025
    from ndcu n
)
select *, round(100.0 * (wer_cum_2025 - ndcu_cum_2025) / ndcu_cum_2025, 1) as diff_pct
from compared
where wer_cum_2025 is not null and ndcu_cum_2025 > 0
  and abs(wer_cum_2025 - ndcu_cum_2025) > 0.05 * ndcu_cum_2025
