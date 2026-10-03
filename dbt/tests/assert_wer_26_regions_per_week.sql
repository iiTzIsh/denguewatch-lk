{{ config(severity='warn') }}
-- warn only: the source has small known gaps (e.g. one region missing in 2026-W07)
select wer_week_key, count(*) as regions
from {{ ref('stg_wer_weekly') }}
group by 1
having count(*) <> 26
