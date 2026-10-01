-- GRAIN: one row per high-risk MOH area per NDCU week.
-- POINT-IN-TIME join to the SCD2 region dimension: each week links to the version of the MOH area that was
-- valid THAT week (valid_from <= week < valid_to), so history stays correct when an area changes later.
select
    r.region_sk,
    m.moh_key,
    r.moh_area,
    r.parent_moh_area,
    md5(r.district)                               as district_sk,      -- district as recorded in the dimension
    m.iso_week_key,
    m.week_start,
    m.week_end,
    m.cases_this_week,
    m.cases_prev_week,                                                  -- as printed (may be revised later)
    m.cases_this_week - m.cases_prev_week         as change_vs_prev_week,
    m.district <> r.district                      as printed_district_differs,   -- one-off misprints (see scd2.py)
    m.source_file,
    cast(current_timestamp as timestamp)          as load_ts
from {{ ref('stg_ndcu_moh_weekly') }} m
left join {{ source('scd2', 'dim_region') }} r
       on r.moh_key = m.moh_key
      and m.week_start >= r.valid_from
      and m.week_start <  r.valid_to
