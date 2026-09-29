-- Staging = light cleanup + consistent names. One row per district per epi week.
select
    district,
    epi_week_start,
    epi_week_end,
    rainfall_mm_total,
    temp_mean_c,
    temp_max_c,
    temp_min_c,
    days_in_week
from {{ source('silver', 'weather_weekly') }}
