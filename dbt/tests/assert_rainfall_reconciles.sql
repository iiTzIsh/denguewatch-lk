-- gold total must match the silver daily total (0.05 mm per week allowed for rounding)
with gold_t as (
    select d.district, sum(f.rainfall_mm_total) as gold_mm, count(*) as weeks
    from {{ ref('fact_weather_weekly') }} f join {{ ref('dim_district') }} d using (district_sk)
    group by 1
),
silver_t as (select district, sum(rainfall_mm) as silver_mm from {{ source('silver', 'weather_daily') }} group by 1)
select g.district, g.gold_mm, s.silver_mm
from gold_t g join silver_t s using (district)
where abs(g.gold_mm - s.silver_mm) > 0.05 * g.weeks
