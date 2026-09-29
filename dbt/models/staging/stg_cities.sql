select
    lower(trim(city))   as city,
    district,
    province,
    latitude,
    longitude
from {{ source('silver', 'dim_city') }}
