-- relationships: every fact row must point at a real week
SELECT f.* FROM gold.fact_weather_weekly f
LEFT JOIN gold.dim_epi_week e USING (epi_week_key)
WHERE e.epi_week_key IS NULL
