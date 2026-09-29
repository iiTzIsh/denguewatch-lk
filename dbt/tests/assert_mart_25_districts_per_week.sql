-- 26 RDHS roll up to exactly 25 districts in every reported week
select iso_week_key, count(*) as districts
from {{ ref('mart_ndcu_monitoring') }}
group by 1
having count(*) <> 25
