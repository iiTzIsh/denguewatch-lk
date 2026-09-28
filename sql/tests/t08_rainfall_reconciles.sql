-- reconciliation: gold total must match silver daily total (allow weekly rounding: 0.05 mm per week)
WITH gold_t AS (
    SELECT c.city, SUM(f.rainfall_mm_total) AS gold_mm, COUNT(*) AS weeks
    FROM gold.fact_weather_weekly f JOIN gold.dim_city c USING (city_sk) GROUP BY 1
),
silver_t AS (SELECT city, SUM(rainfall_mm) AS silver_mm FROM main.weather_daily GROUP BY 1)
SELECT g.city, g.gold_mm, s.silver_mm
FROM gold_t g JOIN silver_t s USING (city)
WHERE abs(g.gold_mm - s.silver_mm) > 0.05 * g.weeks
