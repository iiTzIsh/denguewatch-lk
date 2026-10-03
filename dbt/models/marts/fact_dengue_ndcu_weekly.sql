-- Grain: one row per RDHS region per ISO week (NDCU weekly updates).
-- The next week's PDF restates this week's count once delayed reports arrive:
--   cases_first_reported = count in this week's own PDF
--   cases_latest         = restated count from next week's PDF if available, else the first report
with n as (select * from {{ ref('stg_ndcu_weekly') }})
select
    n.rdhs,
    md5(n.district)                                      as district_sk,
    n.iso_week_key,
    n.week_start,
    n.week_end,
    n.cases_this_week                                    as cases_first_reported,
    coalesce(nxt.cases_prev_week, n.cases_this_week)     as cases_latest,
    coalesce(nxt.cases_prev_week <> n.cases_this_week, false) as is_restated,
    nxt.iso_week_key is not null                         as has_next_week_report,
    n.cum_this_year,
    n.source_file,
    cast(current_timestamp as timestamp)                 as load_ts
from n
left join n as nxt
  on nxt.rdhs = n.rdhs
 and nxt.week_start = n.week_start + 7
