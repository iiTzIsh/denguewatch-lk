-- MODEL: gold.fact_weather_weekly
-- GRAIN: one row per city per epi week
-- KEYS:  city_sk -> gold.dim_city, epi_week_key -> gold.dim_epi_week
CREATE OR REPLACE TABLE gold.fact_weather_weekly AS
SELECT
    COALESCE(c.city_sk, '-1')       AS city_sk,         -- unmatched city -> 'unknown' member
    e.epi_week_key,
    w.rainfall_mm_total,
    w.temp_mean_c,
    w.temp_max_c,
    w.temp_min_c,
    w.days_in_week,
    w.days_in_week = 7              AS is_complete_week,
    CAST(current_timestamp AS TIMESTAMP) AS load_ts     -- lineage: when this row was built (local time)
FROM main.weather_weekly w
LEFT JOIN gold.dim_city     c ON w.city = c.city
LEFT JOIN gold.dim_epi_week e ON w.epi_week_start = e.week_start;
