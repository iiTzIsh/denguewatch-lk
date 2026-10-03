-- every MOH area (business key) has exactly one current SCD2 row
select moh_key
from {{ source('scd2', 'dim_region') }}
group by moh_key
having sum(case when is_current then 1 else 0 end) <> 1
