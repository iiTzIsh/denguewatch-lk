-- A district's high-risk MOH areas cannot exceed the district total on page 1 of the same PDF.
-- Tolerance of 2: in 5 weeks of 2026 Gampaha's MOH rows sum to 1 more than page 1 (docs/moh_regions.md).
-- Source exception 2026-W01: page 1 used a special 2025/2026 day split but the MOH table did not
-- (Colombo 756 vs 523; confirmed by W02's report). Kept as published.
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
where (d.district_cases is null or m.moh_cases > d.district_cases + 2)
  and m.week_start <> date '2025-12-29'          -- 2026-W01, see above
