{{ config(severity='warn') }}
-- known small gaps in the source (e.g. one region missing in 2026-W07) -> WARN, don't block the pipeline
select wer_week_key, count(*) as regions
from {{ ref('stg_wer_weekly') }}
group by 1
having count(*) <> 26
