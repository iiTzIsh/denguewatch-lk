SELECT city_sk, epi_week_key, COUNT(*) AS n FROM gold.fact_weather_weekly GROUP BY 1, 2 HAVING COUNT(*) > 1
