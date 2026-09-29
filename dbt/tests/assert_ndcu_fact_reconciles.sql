-- first-reported cases in the fact must equal the silver totals, week by week
with f as (select iso_week_key, sum(cases_first_reported) as fact_cases from {{ ref('fact_dengue_ndcu_weekly') }} group by 1),
     s as (select iso_week_key, sum(cases_this_week) as silver_cases from {{ ref('stg_ndcu_weekly') }} group by 1)
select * from f full join s using (iso_week_key)
where f.fact_cases is distinct from s.silver_cases
