-- GRAIN: one row per city + an 'unknown' member. city_sk = md5(city) -> stable keys.
select '-1' as city_sk, 'unknown' as city, 'Unknown' as district, 'Unknown' as province,
       cast(null as double) as latitude, cast(null as double) as longitude
union all
select md5(city), city, district, province, latitude, longitude
from {{ ref('stg_cities') }}
