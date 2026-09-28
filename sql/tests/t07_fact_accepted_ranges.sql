SELECT * FROM gold.fact_weather_weekly
WHERE rainfall_mm_total < 0 OR days_in_week NOT BETWEEN 1 AND 7 OR temp_min_c > temp_max_c
