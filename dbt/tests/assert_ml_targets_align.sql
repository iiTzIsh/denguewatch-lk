-- target_cases_h2 must equal the same region's cases 14 (+-3) days later, and cases_lag1 those
-- 7 (+-3) days earlier; guards against off-by-one and leakage bugs.
with f as (select * from {{ ref('mart_ml_features') }})
select a.rdhs, a.week_start, 'target_h2' as check_name
from f a
join f b on b.rdhs = a.rdhs and date_diff('day', a.week_end, b.week_end) between 11 and 17
where a.target_cases_h2 is not null and a.target_cases_h2 <> b.cases
union all
select a.rdhs, a.week_start, 'lag1'
from f a
join f b on b.rdhs = a.rdhs and date_diff('day', b.week_end, a.week_end) between 4 and 10
where a.cases_lag1 is not null and a.cases_lag1 <> b.cases
