-- GRAIN: one row per city per epi week
select
    coalesce(c.city_sk, '-1')             as city_sk,
    e.epi_week_key,
    w.rainfall_mm_total,
    w.temp_mean_c,
    w.temp_max_c,
    w.temp_min_c,
    w.days_in_week,
    w.days_in_week = 7                    as is_complete_week,
    cast(current_timestamp as timestamp)  as load_ts
from {{ ref('stg_weather_weekly') }} w
left join {{ ref('dim_city') }}     c on w.city = c.city
left join {{ ref('dim_epi_week') }} e on w.epi_week_start = e.week_start
