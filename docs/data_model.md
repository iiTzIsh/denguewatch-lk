# Data model (gold layer) — current state

```mermaid
erDiagram
    dim_district ||--o{ fact_weather_weekly : district_sk
    dim_epi_week ||--o{ fact_weather_weekly : epi_week_key
    dim_district {
        varchar district_sk PK "md5(district); '-1' = unknown"
        varchar district
        varchar district_name
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
        varchar district_sk FK
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
| Silver | `weather_daily`, `weather_weekly`, `dim_district` (reference) | DuckDB `main` schema |
| Gold (dbt) | `dim_epi_week`, `dim_district`, `fact_weather_weekly`, `dim_region` (SCD2, Python) | DuckDB `gold` schema |

ML training table: `gold.mart_ml_features` (RDHS x WER week) - see [ml_features.md](ml_features.md).
