SELECT city, epi_week_start, rainfall_mm_total
FROM weather_weekly
WHERE year(epi_week_end) = 2024
QUALIFY ROW_NUMBER() OVER (PARTITION BY city ORDER BY rainfall_mm_total DESC) = 1
