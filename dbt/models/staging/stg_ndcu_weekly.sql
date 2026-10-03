-- NDCU weekly dengue cases per RDHS region, mapped to district.
-- NDCU uses ISO weeks (Mon-Sun), not the Sat-Fri epi weeks used by WER.
select
    n.year,
    n.iso_week,
    printf('%d-W%02d', n.year, n.iso_week) as iso_week_key,
    n.week_start,
    n.week_end,
    n.rdhs,
    r.district,
    n.cases_this_week,
    n.cases_prev_week,
    n.cum_this_year,
    n.has_revised_value,
    n.source_file
from {{ source('silver', 'ndcu_weekly_cases') }} n
left join {{ source('silver', 'dim_rdhs') }} r using (rdhs)
