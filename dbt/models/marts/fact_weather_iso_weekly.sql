-- Grain: one row per district per ISO week (Mon-Sun); same daily data as fact_weather_weekly.
select
    md5(w.district)                         as district_sk,
    d.iso_week_key,
    min(d.iso_week_start)                   as week_start,
    round(sum(w.rainfall_mm), 1)            as rainfall_mm_total,
    round(avg(w.temp_mean_c), 1)            as temp_mean_c,
    max(w.temp_max_c)                       as temp_max_c,
    min(w.temp_min_c)                       as temp_min_c,
    count(*)                                as days_in_week,
    count(*) = 7                            as is_complete_week
from {{ source('silver', 'weather_daily') }} w
join {{ ref('dim_date') }} d on w.date = d.date_day
group by all
