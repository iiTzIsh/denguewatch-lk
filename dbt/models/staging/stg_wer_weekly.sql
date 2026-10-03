-- WER history per RDHS region and reported week, mapped to district.
-- Weeks keep their reported start/end dates because the week definition changed in 2026.
select
    w.year,
    w.week,
    printf('%d-W%02d', w.year, w.week)   as wer_week_key,
    w.week_start,
    w.week_end,
    w.week_days,
    w.week_start_day,
    w.rdhs,
    r.district,
    w.cases,
    w.source
from {{ source('silver', 'wer_weekly_cases') }} w
left join {{ source('silver', 'dim_rdhs') }} r using (rdhs)
