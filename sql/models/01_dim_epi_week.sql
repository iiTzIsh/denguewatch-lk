-- MODEL: gold.dim_epi_week
-- GRAIN: one row per Sri Lankan epidemiological week (Saturday -> Friday), 2006 to 2027
-- RULE:  epi year = year of the week's Tuesday (week has >= 4 days in that year).
--        Matches WER: 2024-W01 = 2023-12-30 -> 2024-01-05. Verify more years against WER listings.
CREATE OR REPLACE TABLE gold.dim_epi_week AS
WITH weeks AS (
    SELECT CAST(unnest(generate_series(DATE '2005-12-31', DATE '2027-12-25', INTERVAL 7 DAY)) AS DATE) AS week_start
),
labelled AS (
    SELECT
        week_start,
        week_start + 6          AS week_end,
        year(week_start + 3)    AS epi_year,
        month(week_start + 3)   AS mid_month
    FROM weeks
)
SELECT
    printf('%d-W%02d', epi_year,
           ROW_NUMBER() OVER (PARTITION BY epi_year ORDER BY week_start))   AS epi_week_key,
    epi_year,
    CAST(ROW_NUMBER() OVER (PARTITION BY epi_year ORDER BY week_start) AS INTEGER) AS week_number,
    week_start,
    week_end,
    CASE
        WHEN mid_month IN (12, 1, 2)       THEN 'NE monsoon'
        WHEN mid_month IN (3, 4)           THEN 'First inter-monsoon'
        WHEN mid_month BETWEEN 5 AND 9     THEN 'SW monsoon'
        ELSE                                    'Second inter-monsoon'
    END AS season
FROM labelled
ORDER BY week_start;
