-- Q1 Basic GROUP BY: total 2024 rainfall per city
SELECT city, ROUND(SUM(rainfall_mm_total), 0) AS rain_2024_mm
FROM weather_weekly
WHERE year(epi_week_end) = 2024
GROUP BY city
ORDER BY rain_2024_mm DESC;

-- Q2 CTE + ROW_NUMBER: the wettest week of each month, per city (Colombo shown)
WITH ranked AS (
    SELECT
        city,
        epi_week_start,
        rainfall_mm_total,
        ROW_NUMBER() OVER (
            PARTITION BY city, month(epi_week_end)     -- restart numbering for each city+month
            ORDER BY rainfall_mm_total DESC            -- wettest first
        ) AS rn
    FROM weather_weekly
)
SELECT city, epi_week_start, rainfall_mm_total
FROM ranked
WHERE rn = 1 AND city = 'colombo'
ORDER BY epi_week_start;

-- Q3 LAG: week-over-week rainfall change (a "lag feature" - same idea as the ML features later)
SELECT
    city,
    epi_week_start,
    rainfall_mm_total,
    LAG(rainfall_mm_total, 1) OVER (PARTITION BY city ORDER BY epi_week_start) AS rain_last_week,
    rainfall_mm_total
      - LAG(rainfall_mm_total, 1) OVER (PARTITION BY city ORDER BY epi_week_start) AS change_mm
FROM weather_weekly
WHERE city = 'kandy'
ORDER BY epi_week_start
LIMIT 8;

-- Q4 Rolling window: 4-week rolling rainfall (mosquitoes breed weeks after rain)
SELECT
    city,
    epi_week_start,
    rainfall_mm_total,
    ROUND(SUM(rainfall_mm_total) OVER (
        PARTITION BY city ORDER BY epi_week_start
        ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ), 1) AS rain_4wk_total
FROM weather_weekly
WHERE city = 'galle'
ORDER BY epi_week_start
LIMIT 8;

-- Q5 Data quality: partial weeks (fewer than 7 days) - expect only at the start/end of the range
SELECT city, epi_week_start, days_in_week
FROM weather_weekly
WHERE days_in_week < 7
ORDER BY city, epi_week_start;
