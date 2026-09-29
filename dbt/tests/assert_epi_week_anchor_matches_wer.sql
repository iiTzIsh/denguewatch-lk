-- dates seen on the WER listing page (add more as you verify them)
select * from (values ('2024-W01', date '2023-12-30'), ('2024-W18', date '2024-04-27'), ('2023-W52', date '2023-12-23'))
    as expected(epi_week_key, week_start)
where not exists (
    select 1 from {{ ref('dim_epi_week') }} d
    where d.epi_week_key = expected.epi_week_key and d.week_start = expected.week_start
)
