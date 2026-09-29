SELECT COUNT(*) AS weeks
FROM weather_weekly a JOIN weather_weekly b USING (epi_week_start)
WHERE a.city = 'colombo' AND b.city = 'kandy' AND a.rainfall_mm_total > b.rainfall_mm_total
