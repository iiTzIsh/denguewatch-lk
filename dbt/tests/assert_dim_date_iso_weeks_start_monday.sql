-- every ISO week starts on a Monday, every epi week on a Saturday
select d.date_day
from {{ ref('dim_date') }} d
join {{ ref('dim_epi_week') }} e using (epi_week_key)
where dayname(d.iso_week_start) <> 'Monday' or dayname(e.week_start) <> 'Saturday'
