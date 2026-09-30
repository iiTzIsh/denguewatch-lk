-- The h2 target must be the cases of the SAME region's week that ends 14 days (+-3) later,
-- and cases_lag1 the week that ends 7 days (+-3) earlier. Guards against off-by-one / leakage bugs.
-- Returns failing rows.
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
