-- S1 Full history (every version of every MOH area)
SELECT moh_area, parent_moh_area, boundary_note, valid_from, valid_to, is_current
FROM gold.dim_region
ORDER BY moh_area, valid_from;

-- S2 Current view only (what dashboards usually want)
SELECT moh_area, district, parent_moh_area
FROM gold.dim_region
WHERE is_current
ORDER BY moh_area;

-- S3 "As of" query: what did the MOH list look like on 2025-06-15? (Kesbewa did not exist yet)
SELECT moh_area, boundary_note
FROM gold.dim_region
WHERE DATE '2025-06-15' >= valid_from AND DATE '2025-06-15' < valid_to
ORDER BY moh_area;

-- S4 Point-in-time JOIN: DEMO case counts join to the region version valid ON THAT WEEK
WITH demo_cases(moh_area, week_start, cases) AS (
    VALUES ('Piliyandala', DATE '2025-06-07', 40),   -- before split: Piliyandala incl. Kesbewa
           ('Piliyandala', DATE '2026-06-06', 22),   -- after split
           ('Kesbewa',     DATE '2026-06-06', 19)
)
SELECT c.moh_area, c.week_start, c.cases, r.boundary_note, r.region_sk
FROM demo_cases c
JOIN gold.dim_region r
  ON r.moh_area = c.moh_area
 AND c.week_start >= r.valid_from AND c.week_start < r.valid_to
ORDER BY c.week_start, c.moh_area;

-- S5 Roll new areas up to their parent -> comparable series across the split (the modelling trick)
WITH demo_cases(moh_area, week_start, cases) AS (
    VALUES ('Piliyandala', DATE '2025-06-07', 40),
           ('Piliyandala', DATE '2026-06-06', 22),
           ('Kesbewa',     DATE '2026-06-06', 19)
)
SELECT COALESCE(r.parent_moh_area, r.moh_area) AS comparable_area, c.week_start, SUM(c.cases) AS cases
FROM demo_cases c
JOIN gold.dim_region r
  ON r.moh_area = c.moh_area AND c.week_start >= r.valid_from AND c.week_start < r.valid_to
GROUP BY ALL
ORDER BY week_start;
