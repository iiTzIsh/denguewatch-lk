# ADR 0001 — Two week systems (epi weeks vs ISO weeks)

**Date:** 29 Sep 2026 · **Status:** accepted

## Context
- WER (Epidemiology Unit) reports **epidemiological weeks, Saturday → Friday** (2024-W01 = 2023-12-30 → 2024-01-05).
- NDCU weekly updates report **ISO weeks, Monday → Sunday** (2026-W37 = 2026-09-07 → 2026-09-13).
- The two are offset by 2 days, so a case count can't be moved from one week system to the other without guessing.
- Weather is **daily**, so it can be aggregated to either system exactly.

## Decision
1. Each dengue fact keeps its **native week** (never re-bucketed): `fact_dengue_ndcu_weekly` on ISO weeks; the WER fact (later) on epi weeks.
2. A daily **`dim_date`** maps every date to both `epi_week_key` and `iso_week_key` — the bridge between systems.
3. Weather is published in **both** grains (`fact_weather_weekly` = epi, `fact_weather_iso_weekly` = ISO) from the same daily silver data.
4. Marts join dengue to weather **within the same week system**.

## Consequences
- No invented numbers: every figure stays in the week it was reported in.
- Two weekly weather facts (cheap: computed from daily data).
- The forecasting model (Phase 4) trains on the WER/epi-week series; the live monitoring view uses NDCU/ISO weeks.
