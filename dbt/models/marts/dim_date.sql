-- GRAIN: one row per calendar day, 2006-2027.
-- The BRIDGE between week systems: each day -> its Sat->Fri epi week AND its Mon->Sun ISO week.  (docs/decisions/0001)
with days as (
    select cast(unnest(generate_series(date '2006-01-01', date '2027-12-31', interval 1 day)) as date) as date_day
)
select
    d.date_day,
    year(d.date_day)                                          as calendar_year,
    month(d.date_day)                                         as calendar_month,
    dayname(d.date_day)                                       as day_name,
    e.epi_week_key,
    printf('%d-W%02d', isoyear(d.date_day), weekofyear(d.date_day)) as iso_week_key,
    isoyear(d.date_day)                                       as iso_year,
    weekofyear(d.date_day)                                    as iso_week,
    cast(date_trunc('week', d.date_day) as date)              as iso_week_start      -- Monday
from days d
left join {{ ref('dim_epi_week') }} e
  on d.date_day between e.week_start and e.week_end
