-- The high-risk MOH areas of a district can't have more cases than the whole district reported that week
-- (page 1 of the same PDF). Tolerance of 2 cases: in 5 weeks of 2026 Gampaha's MOH rows sum to exactly 1 more
-- than its page-1 total - a small inconsistency inside the source PDFs, documented in docs/ndcu_notes.md.
with moh as (
    select district, week_start, sum(cases_this_week) as moh_cases
    from {{ ref('stg_ndcu_moh_weekly') }}
    group by all
),
dist as (
    select district, week_start, sum(cases_this_week) as district_cases
    from {{ ref('stg_ndcu_weekly') }}
    group by all
)
select m.*, d.district_cases
from moh m
left join dist d using (district, week_start)
where d.district_cases is null or m.moh_cases > d.district_cases + 2
