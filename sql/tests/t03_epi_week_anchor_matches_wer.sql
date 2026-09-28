-- known facts from the WER listing page (add more as you verify them)
SELECT * FROM (VALUES ('2024-W01', DATE '2023-12-30'), ('2024-W18', DATE '2024-04-27'), ('2023-W52', DATE '2023-12-23'))
    AS expected(epi_week_key, week_start)
WHERE NOT EXISTS (
    SELECT 1 FROM gold.dim_epi_week d
    WHERE d.epi_week_key = expected.epi_week_key AND d.week_start = expected.week_start
)
