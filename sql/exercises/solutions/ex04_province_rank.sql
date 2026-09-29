SELECT c.province, ROUND(SUM(w.rainfall_mm), 0) AS rain_mm,
       DENSE_RANK() OVER (ORDER BY SUM(w.rainfall_mm) DESC) AS rnk
FROM weather_daily w JOIN dim_city c USING (city)
WHERE year(w.date) = 2024
GROUP BY c.province
