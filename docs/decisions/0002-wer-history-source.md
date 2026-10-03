# ADR 0002: WER history from the `denguedatahub` R package (pinned)

Date: 30 Sep 2026. Status: accepted.

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
| NDCU vs WER, 2025 cumulative (37 NDCU weeks) | Within **~4%** from week 5 on; 5–7% in weeks 2–4 (2-day calendar shift on a small total). NDCU's own cumulative *drops* in week 32 (34,316 → 33,436), an NDCU-side anomaly. *(Corrected 1 Oct 2026: the first version of this check also counted WER's "2025 week 1" (21–27 Dec 2024), which made the gap look like 2–3.5%.)* |
| Week definitions | Sat→Fri epi weeks up to 2025; **Mon→Sun (ISO) in 2026**; 2009 W17 = 8 days, W22 = 6 days |
| Gaps | 2023-W52 missing; 2026-W07 has 25 of 26 regions |

## Consequences
- The forecasting model has a 2007-2026 training history, including the 2017 epidemic.
- Weekly weather for WER weeks is computed over each week's **actual** start/end dates, so the week-definition
  change in 2026 is handled exactly.
- Credit denguedatahub + the Epidemiology Unit in the README and dashboard.
