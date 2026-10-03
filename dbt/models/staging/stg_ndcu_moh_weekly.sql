-- High-risk MOH areas per NDCU ISO week (Mon-Sun), as printed on page 2 of the weekly update.
select
    iso_year,
    iso_week,
    printf('%d-W%02d', iso_year, iso_week) as iso_week_key,
    week_start,
    week_end,
    district,
    moh_key,
    moh_area,
    cases_prev_week,
    cases_this_week,
    source_file
from {{ source('silver', 'ndcu_moh_weekly_cases') }}
