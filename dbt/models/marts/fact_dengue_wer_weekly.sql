-- Grain: one row per RDHS region per reported WER week (history for the forecasting model).
select
    s.rdhs,
    md5(s.district)                         as district_sk,
    s.wer_week_key,
    s.year,
    s.week,
    s.week_start,
    s.week_end,
    s.week_days,
    s.week_start_day = 'Saturday'           as is_standard_epi_week,   -- false for 2026 ISO weeks and 2009 quirks
    s.cases,
    s.source,
    cast(current_timestamp as timestamp)    as load_ts
from {{ ref('stg_wer_weekly') }} s
