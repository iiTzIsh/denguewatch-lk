-- gold total must match silver daily total (weekly rounding allowed: 0.05 mm per week)
with gold_t as (
    select c.city, sum(f.rainfall_mm_total) as gold_mm, count(*) as weeks
    from {{ ref('fact_weather_weekly') }} f join {{ ref('dim_city') }} c using (city_sk)
    group by 1
),
silver_t as (select city, sum(rainfall_mm) as silver_mm from {{ source('silver', 'weather_daily') }} group by 1)
select g.city, g.gold_mm, s.silver_mm
from gold_t g join silver_t s using (city)
where abs(g.gold_mm - s.silver_mm) > 0.05 * g.weeks
