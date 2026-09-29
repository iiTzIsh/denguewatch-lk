-- every parsed NDCU week must contain all 26 RDHS regions
select iso_week_key, count(*) as regions
from {{ ref('stg_ndcu_weekly') }}
group by iso_week_key
having count(*) <> 26
