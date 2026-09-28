-- J1 INNER JOIN: add district + province to weekly weather (only matching rows)
SELECT w.city, c.district, c.province, w.epi_week_start, w.rainfall_mm_total
FROM weather_weekly w
INNER JOIN dim_city c ON w.city = c.city
ORDER BY w.epi_week_start, w.city
LIMIT 6;

-- J2 JOIN + GROUP BY: 2024 rainfall per province
SELECT c.province, COUNT(DISTINCT c.city) AS cities, ROUND(SUM(w.rainfall_mm_total), 0) AS rain_mm
FROM weather_weekly w
JOIN dim_city c USING (city)
WHERE year(w.epi_week_end) = 2024
GROUP BY c.province
ORDER BY rain_mm DESC;

-- J3 LEFT JOIN: every city in the reference, even with NO weather data (matara -> NULL)
SELECT c.city, c.province, COUNT(w.city) AS weeks_of_data
FROM dim_city c
LEFT JOIN weather_weekly w ON c.city = w.city
GROUP BY c.city, c.province
ORDER BY weeks_of_data;

-- J4 Anti-join: reference cities with no weather yet (to-do list for the extractor)
SELECT c.city
FROM dim_city c
WHERE NOT EXISTS (SELECT 1 FROM weather_daily w WHERE w.city = c.city);

-- J5 CTE chain: each city's 2024 total vs the national average of cities
WITH city_totals AS (
    SELECT city, SUM(rainfall_mm) AS rain_mm
    FROM weather_daily
    WHERE year(date) = 2024
    GROUP BY city
),
avg_all AS (
    SELECT AVG(rain_mm) AS avg_mm FROM city_totals
)
SELECT t.city,
       ROUND(t.rain_mm, 0)                 AS rain_mm,
       ROUND(t.rain_mm - a.avg_mm, 0)      AS vs_avg_mm,
       CASE WHEN t.rain_mm > a.avg_mm THEN 'wetter' ELSE 'drier' END AS label
FROM city_totals t
CROSS JOIN avg_all a                        -- avg_all has 1 row, so this just attaches it to every row
ORDER BY rain_mm DESC;

-- J6 GRAIN TRAP: joining daily (1 row/day) to weekly (1 row/week) on city only = row explosion
SELECT
    (SELECT COUNT(*) FROM weather_daily WHERE city = 'colombo')                AS daily_rows,
    (SELECT COUNT(*) FROM weather_daily d
       JOIN weather_weekly w ON d.city = w.city WHERE d.city = 'colombo')     AS wrong_join_rows,
    (SELECT COUNT(*) FROM weather_daily d
       JOIN weather_weekly w ON d.city = w.city
        AND d.date BETWEEN w.epi_week_start AND w.epi_week_end
       WHERE d.city = 'colombo')                                               AS correct_join_rows;
