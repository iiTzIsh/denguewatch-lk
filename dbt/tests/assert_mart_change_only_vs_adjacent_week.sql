-- 'change vs previous week' must be empty when the previous week wasn't reported (no comparing across gaps)
select m.district, m.iso_week_key
from {{ ref('mart_ndcu_monitoring') }} m
left join {{ ref('mart_ndcu_monitoring') }} p
  on p.district_sk = m.district_sk and p.week_start = m.week_start - 7
where p.district_sk is null and m.cases_change_vs_prev_week is not null
