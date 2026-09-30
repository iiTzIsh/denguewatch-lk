# ADR 0002 — WER history from the `denguedatahub` R package (pinned)

**Date:** 30 Sep 2026 · **Status:** accepted

## Context
- The forecasting model needs **years** of weekly dengue history per region (incl. the 2017 epidemic).
- NDCU weekly PDFs give only ~20 weeks. The Epidemiology Unit website (WER PDFs, 2006–2024) has returned
  HTTP 500 since 28 Sep 2026.
- The open-source R package **denguedatahub** (Dr. Thiyanga S. Talagala, GPL-3) publishes `srilanka_weekly_data`,
  extracted from the **same WER reports** (`@source Weekly Epidemiological Reports, Epidemiology Unit`).

## Decision
Use `srilanka_weekly_data` as the WER history source, **pinned to commit `86d8070`** (2026-06-21), with:
- validation on load (known region names, whole non-negative numbers, no duplicates) → hard failures;
- small source gaps/irregular weeks → **warnings** (kept as reported, never "fixed" by guessing);
- a **cross-source check** against NDCU (2025 cumulative printed in NDCU PDFs vs WER week-by-week sums).
Our own WER scraper stays in the project; when the site returns, it can **re-verify** this dataset.

## Evidence (30 Sep 2026)
| Check | Result |
|---|---|
| Coverage | 2006-W52 → 2026-W20 (week ending 2026-05-17); 26 RDHS regions; 26,311 rows |
| 2017 epidemic present | 174,687 cases in 2017 |
| NDCU vs WER, 2025 cumulative (20 NDCU weeks) | WER within **~2–3.5%** of NDCU in 19 weeks; **7.1%** in NDCU week 32, where NDCU's own cumulative *drops* (34,316 → 33,436) — an NDCU-side anomaly |
| Week definitions | Sat→Fri epi weeks up to 2025; **Mon→Sun (ISO) in 2026**; 2009 W17 = 8 days, W22 = 6 days |
| Gaps | 2023-W52 missing; 2026-W07 has 25 of 26 regions |

## Consequences
- Phase 4 (ML) is unblocked.
- Weekly weather for WER weeks is computed over each week's **actual** start/end dates, so the week-definition
  change in 2026 is handled exactly.
- Credit denguedatahub + the Epidemiology Unit in the README and dashboard.
