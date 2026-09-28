-- MODEL: gold.dim_city
-- GRAIN: one row per city (+ one 'unknown' member so facts never have NULL keys)
-- KEY:   city_sk = md5(city) -> a hash key is STABLE: adding a new city never changes old keys
--        (ROW_NUMBER keys would shift when a new city sorts in between -> breaks history)
CREATE OR REPLACE TABLE gold.dim_city AS
SELECT '-1' AS city_sk, 'unknown' AS city, 'Unknown' AS district, 'Unknown' AS province,
       CAST(NULL AS DOUBLE) AS latitude, CAST(NULL AS DOUBLE) AS longitude
UNION ALL
SELECT md5(city), city, district, province, latitude, longitude
FROM main.dim_city;
