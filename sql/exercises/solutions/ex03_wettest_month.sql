WITH m AS (
    SELECT city, month(date) AS month, SUM(rainfall_mm) AS rain_mm
    FROM weather_daily WHERE year(date) = 2024 GROUP BY ALL
)
SELECT city, month, ROUND(rain_mm, 1) AS rain_mm,
       ROUND(100 * rain_mm / SUM(rain_mm) OVER (PARTITION BY city), 1) AS pct_of_year
FROM m
QUALIFY ROW_NUMBER() OVER (PARTITION BY city ORDER BY rain_mm DESC) = 1
