select
    lower(trim(district))   as district,
    district_name,
    province,
    latitude,
    longitude
from {{ source('silver', 'dim_district') }}
