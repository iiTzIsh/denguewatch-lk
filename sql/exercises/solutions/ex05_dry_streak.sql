WITH f AS (
    SELECT city, epi_week_start, rainfall_mm_total < 10 AS dry,
           ROW_NUMBER() OVER (PARTITION BY city ORDER BY epi_week_start) AS rn_all
    FROM weather_weekly
),
d AS (
    SELECT city, rn_all - ROW_NUMBER() OVER (PARTITION BY city ORDER BY epi_week_start) AS grp
    FROM f WHERE dry
)
SELECT city, MAX(n) AS dry_weeks
FROM (SELECT city, grp, COUNT(*) AS n FROM d GROUP BY ALL)
GROUP BY city
