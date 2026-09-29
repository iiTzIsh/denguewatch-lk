-- GRAIN: one row per RDHS region per ISO week (NDCU weekly updates).
-- Restatements: the NEXT week's PDF re-reports this week's number after delayed reports arrive.
--   cases_first_reported = number in this week's own PDF
--   cases_latest         = the revised number from next week's PDF if we have it, else the first report
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
