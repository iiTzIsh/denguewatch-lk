-- versions of the same MOH area never overlap, so a point-in-time join finds at most one
select a.moh_key, a.valid_from, b.valid_from as overlaps_with
from {{ source('scd2', 'dim_region') }} a
join {{ source('scd2', 'dim_region') }} b
  on a.moh_key = b.moh_key and a.region_sk <> b.region_sk
 and a.valid_from < b.valid_to and b.valid_from < a.valid_to
