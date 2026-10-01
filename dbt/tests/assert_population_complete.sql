-- Census population is all-or-nothing: either not loaded yet (0 rows), or all 25 districts
-- summing to the national total printed in the Census 2024 Final Report (21,781,800).
-- Returns a row (= failure) otherwise.
with p as (select count(*) as n, coalesce(sum(population), 0) as total from {{ source('silver', 'district_population') }})
select * from p where not (n = 0 or (n = 25 and total = 21781800))
