# Data model (gold layer) — current state

```mermaid
erDiagram
    dim_city ||--o{ fact_weather_weekly : city_sk
    dim_epi_week ||--o{ fact_weather_weekly : epi_week_key
    dim_city {
        varchar city_sk PK "md5(city); '-1' = unknown"
        varchar city
        varchar district
        varchar province
        double latitude
        double longitude
    }
    dim_epi_week {
        varchar epi_week_key PK "e.g. 2024-W18"
        int epi_year
        int week_number
        date week_start "Saturday"
        date week_end "Friday"
        varchar season
    }
    fact_weather_weekly {
        varchar city_sk FK
        varchar epi_week_key FK
        double rainfall_mm_total
        double temp_mean_c
        double temp_max_c
        double temp_min_c
        int days_in_week
        bool is_complete_week
        timestamp load_ts
    }
```

| Layer | Tables | Where |
|---|---|---|
| Bronze | raw CSV / HTML / PDF | `data/bronze/` |
| Silver | `weather_daily`, `weather_weekly`, `dim_city` (reference) | DuckDB `main` schema |
| Gold | `dim_epi_week`, `dim_city`, `fact_weather_weekly` | DuckDB `gold` schema |

Later: `dim_city` becomes `dim_region` (SCD2), and `fact_dengue_weekly` joins the same dimensions.
