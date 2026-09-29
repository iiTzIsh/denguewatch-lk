-- every week starts exactly 7 days after the previous one
select week_start, prev_start
from (select week_start, lag(week_start) over (order by week_start) as prev_start from {{ ref('dim_epi_week') }})
where prev_start is not null and week_start - prev_start <> 7
