# NDCU source notes

Site: https://www.dengue.health.gov.lk/ — robots.txt allows everything except /wp-admin/ (checked 29 Sep 2026).

## Weekly Dengue Update PDFs
- Listed on the home page and on https://www.dengue.health.gov.lk/weekly-report/ (16 links seen on 29 Sep 2026: 2026 weeks 22–37).
- URL pattern `wp-content/uploads/<YYYY>/<MM>/Weekly-Dengue-Update-<YYYY>-Week-<NN>.pdf`, but **not consistent**
  (`Week-31-1.pdf`, lower-case `weekly-dengue-update-2026-week-23.pdf`) -> we discover links, never guess.
- **Weeks are ISO weeks, Monday -> Sunday** (Week 37 2026 = 07–13 Sep 2026). WER uses Saturday -> Friday epi weeks.
- Page 1, Table 1: cases per **RDHS** — 26 rows (25 districts; Ampara district split into Ampara + Kalmunai RDHS).
  Columns: prev-year week N-1, prev-year week N, this-year week N-1, this-year week N, cumulative prev year, cumulative this year.
- Cell quirks: `Nil` = 0; `71*` = revised after delayed reports; the PDF *table* layer splits some rows (Galle, Kegalle),
  the *text* layer does not -> parser reads text.
- Validation: parsed sum of week N must equal the printed `Total` row; all 26 regions present; header dates must match the ISO week.

## Reference
Open-source scraper used only to learn the structure: https://github.com/nuuuwan/lk_dengue (our parser is independent).
