SELECT epi_week_key, COUNT(*) AS n FROM gold.dim_epi_week GROUP BY 1 HAVING COUNT(*) > 1
