-- Grain: one row per district (25) plus an 'unknown' member. district_sk = md5(district) for stable keys.
select '-1' as district_sk, 'unknown' as district, 'Unknown' as district_name, 'Unknown' as province,
       cast(null as double) as latitude, cast(null as double) as longitude
union all
select md5(district), district, district_name, province, latitude, longitude
from {{ ref('stg_districts') }}
