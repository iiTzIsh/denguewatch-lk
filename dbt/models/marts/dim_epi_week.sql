-- GRAIN: one row per Sri Lankan epi week (Sat -> Fri), 2006-2027
-- RULE:  epi year = year of the week's Tuesday (>= 4 days in that year). Checked against WER dates in tests/.
with weeks as (
    select cast(unnest(generate_series(date '2005-12-31', date '2027-12-25', interval 7 day)) as date) as week_start
),
labelled as (
    select
        week_start,
        week_start + 6        as week_end,
        year(week_start + 3)  as epi_year,
        month(week_start + 3) as mid_month
    from weeks
)
select
    printf('%d-W%02d', epi_year, row_number() over (partition by epi_year order by week_start)) as epi_week_key,
    epi_year,
    cast(row_number() over (partition by epi_year order by week_start) as integer)           as week_number,
    week_start,
    week_end,
    case
        when mid_month in (12, 1, 2)   then 'NE monsoon'
        when mid_month in (3, 4)       then 'First inter-monsoon'
        when mid_month between 5 and 9 then 'SW monsoon'
        else                                'Second inter-monsoon'
    end as season
from labelled
