{{ config(severity='warn') }}
-- Cross-source check: NDCU's printed 2025 cumulative vs the WER 2025 weekly history.
-- A WER week counts toward 2025 if it ends in 2025 (WER's "2025 week 1" ran 21-27 Dec 2024).
-- The Sat-Fri vs Mon-Sun shift is ~300 cases, so allow the larger of 5% or 400 cases
-- (observed: within 4% from week 5 on; 5-7% in weeks 2-4 while totals are small).
with ndcu as (
    select year, iso_week, max(week_end) as week_end, sum(cum_prev_year) as ndcu_cum_2025
    from {{ source('silver', 'ndcu_weekly_cases') }}
    where year = 2026
    group by 1, 2
),
compared as (
    select n.iso_week, n.ndcu_cum_2025,
           (select sum(w.cases) from {{ ref('stg_wer_weekly') }} w
             where w.week_end >= date '2025-01-01' and w.week_end <= n.week_end - interval 1 year) as wer_cum_2025
    from ndcu n
)
select *, round(100.0 * (wer_cum_2025 - ndcu_cum_2025) / ndcu_cum_2025, 1) as diff_pct
from compared
where wer_cum_2025 is not null and ndcu_cum_2025 > 0
  and abs(wer_cum_2025 - ndcu_cum_2025) > greatest(0.05 * ndcu_cum_2025, 400)
