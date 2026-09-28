-- J7 (Day 1 answer) wettest city per province in 2024
WITH city_rain AS (
    SELECT c.province, w.city, SUM(w.rainfall_mm) AS rain_mm
    FROM weather_daily w JOIN dim_city c USING (city)
    WHERE year(w.date) = 2024
    GROUP BY ALL
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY province ORDER BY rain_mm DESC) AS rn
    FROM city_rain
)
SELECT province, city, ROUND(rain_mm, 0) AS rain_mm FROM ranked WHERE rn = 1 ORDER BY rain_mm DESC;

-- J8 (Day 1 answer) weeks where Colombo got more rain than Kandy (self-join)
SELECT a.epi_week_start, a.rainfall_mm_total AS colombo_mm, b.rainfall_mm_total AS kandy_mm
FROM weather_weekly a
JOIN weather_weekly b ON a.epi_week_start = b.epi_week_start
WHERE a.city = 'colombo' AND b.city = 'kandy' AND a.rainfall_mm_total > b.rainfall_mm_total
ORDER BY a.epi_week_start
LIMIT 8;

-- W1 ROW_NUMBER vs RANK vs DENSE_RANK (rounded to 10 mm so ties appear)
SELECT
    city,
    epi_week_start,
    ROUND(rainfall_mm_total, -1) AS rain_10mm,
    ROW_NUMBER() OVER w AS row_num,     -- 1,2,3,4  always unique
    RANK()       OVER w AS rnk,         -- 1,2,2,4  ties share, then GAP
    DENSE_RANK() OVER w AS dense_rnk    -- 1,2,2,3  ties share, NO gap
FROM weather_weekly
WHERE city = 'colombo'
WINDOW w AS (ORDER BY ROUND(rainfall_mm_total, -1) DESC)
QUALIFY row_num <= 10;

-- W2 QUALIFY (DuckDB/Snowflake shortcut): top 3 wettest weeks per city, no CTE needed
SELECT city, epi_week_start, rainfall_mm_total
FROM weather_weekly
QUALIFY ROW_NUMBER() OVER (PARTITION BY city ORDER BY rainfall_mm_total DESC) <= 3
ORDER BY city, rainfall_mm_total DESC;

-- W3 LAG vs LEAD: LAG = past (safe ML feature). LEAD = future (only for TARGETS - using it as a feature = LEAKAGE)
SELECT
    epi_week_start,
    rainfall_mm_total,
    LAG(rainfall_mm_total, 2)  OVER (ORDER BY epi_week_start) AS rain_2wk_ago,   -- feature
    LEAD(rainfall_mm_total, 2) OVER (ORDER BY epi_week_start) AS rain_in_2wk     -- target-style
FROM weather_weekly
WHERE city = 'galle'
ORDER BY epi_week_start
LIMIT 6;

-- W4 Running total: cumulative 2024 rainfall per city (ROWS UNBOUNDED PRECEDING)
SELECT
    city,
    epi_week_start,
    rainfall_mm_total,
    ROUND(SUM(rainfall_mm_total) OVER (
        PARTITION BY city ORDER BY epi_week_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ), 0) AS rain_ytd_mm
FROM weather_weekly
WHERE city = 'jaffna'
ORDER BY epi_week_start
LIMIT 6;

-- W5 Share of total: each week's % of that city's yearly rain (window with NO ORDER BY = whole partition)
SELECT
    city,
    epi_week_start,
    rainfall_mm_total,
    ROUND(100 * rainfall_mm_total / SUM(rainfall_mm_total) OVER (PARTITION BY city), 1) AS pct_of_year
FROM weather_weekly
QUALIFY ROW_NUMBER() OVER (PARTITION BY city ORDER BY rainfall_mm_total DESC) = 1
ORDER BY pct_of_year DESC;

-- W6 NTILE: split each city's weeks into 4 groups (quartiles) - 4 = wettest 25%
SELECT city, quartile, COUNT(*) AS weeks, ROUND(MIN(rainfall_mm_total), 1) AS min_mm, ROUND(MAX(rainfall_mm_total), 1) AS max_mm
FROM (
    SELECT city, rainfall_mm_total,
           NTILE(4) OVER (PARTITION BY city ORDER BY rainfall_mm_total) AS quartile
    FROM weather_weekly
)
WHERE city = 'kandy'
GROUP BY ALL
ORDER BY quartile;

-- W7 Z-score anomaly: weeks > 2 standard deviations above the city's mean (the endemic-channel idea!)
WITH stats AS (
    SELECT *,
           AVG(rainfall_mm_total)         OVER (PARTITION BY city) AS mean_mm,
           STDDEV_SAMP(rainfall_mm_total) OVER (PARTITION BY city) AS sd_mm
    FROM weather_weekly
)
SELECT city, epi_week_start, rainfall_mm_total,
       ROUND(mean_mm + 2 * sd_mm, 1)                     AS threshold_mm,
       ROUND((rainfall_mm_total - mean_mm) / sd_mm, 2)   AS z_score
FROM stats
WHERE rainfall_mm_total > mean_mm + 2 * sd_mm
ORDER BY z_score DESC;

-- W8 Gaps & islands (classic interview): streaks of consecutive "wet weeks" (> 50 mm)
WITH flagged AS (
    SELECT city, epi_week_start, rainfall_mm_total > 50 AS is_wet,
           ROW_NUMBER() OVER (PARTITION BY city ORDER BY epi_week_start) AS rn_all
    FROM weather_weekly
),
wet_only AS (
    SELECT *,
           rn_all - ROW_NUMBER() OVER (PARTITION BY city ORDER BY epi_week_start) AS island_id  -- same value = same streak
    FROM flagged
    WHERE is_wet
)
SELECT city, MIN(epi_week_start) AS streak_start, COUNT(*) AS wet_weeks_in_a_row
FROM wet_only
GROUP BY city, island_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY city ORDER BY COUNT(*) DESC) = 1   -- longest streak per city
ORDER BY wet_weeks_in_a_row DESC;
