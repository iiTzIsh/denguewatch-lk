-- The high-risk MOH areas of a district can't have more cases than the whole district reported that week
-- (page 1 of the same PDF). Tolerance of 2 cases: in 5 weeks of 2026 Gampaha's MOH rows sum to exactly 1 more
-- than its page-1 total - a small inconsistency inside the source PDFs, documented in docs/moh_regions.md.
-- KNOWN SOURCE EXCEPTION: 2026-W01 (29 Dec - 4 Jan). Its page-1 totals were counted over a special split
-- ("last 3 days in 2025 and first 4 days in 2026", per the PDF's own note); its MOH table was not: Colombo's
-- MOH rows add up to 756 vs 523 on page 1 (W02's report confirms both numbers). Kept as published.
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
