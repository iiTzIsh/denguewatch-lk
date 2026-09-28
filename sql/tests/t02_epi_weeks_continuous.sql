-- every week must start exactly 7 days after the previous one (no gaps/overlaps)
SELECT week_start, prev_start FROM (
    SELECT week_start, LAG(week_start) OVER (ORDER BY week_start) AS prev_start FROM gold.dim_epi_week
) WHERE prev_start IS NOT NULL AND week_start - prev_start <> 7
