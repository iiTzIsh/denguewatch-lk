-- Census population is all-or-nothing: 0 rows, or all 25 districts summing to the
-- Census 2024 Final Report national total (21,781,800).
with p as (select count(*) as n, coalesce(sum(population), 0) as total from {{ source('silver', 'district_population') }})
select * from p where not (n = 0 or (n = 25 and total = 21781800))
