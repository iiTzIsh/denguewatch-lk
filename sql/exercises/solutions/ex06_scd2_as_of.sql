SELECT moh_area, parent_moh_area
FROM gold.dim_region
WHERE DATE '2026-06-15' >= valid_from AND DATE '2026-06-15' < valid_to
