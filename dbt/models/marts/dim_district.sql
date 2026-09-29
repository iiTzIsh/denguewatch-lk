-- GRAIN: one row per district (25) + an 'unknown' member. district_sk = md5(district) -> stable keys.
select '-1' as district_sk, 'unknown' as district, 'Unknown' as district_name, 'Unknown' as province,
       cast(null as double) as latitude, cast(null as double) as longitude
union all
select md5(district), district, district_name, province, latitude, longitude
from {{ ref('stg_districts') }}
