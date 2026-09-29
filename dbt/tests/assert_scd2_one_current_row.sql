-- SCD2 rule: every MOH area has exactly one current row
select moh_area
from {{ source('scd2', 'dim_region') }}
group by moh_area
having sum(case when is_current then 1 else 0 end) <> 1
