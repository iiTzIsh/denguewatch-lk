# MOH areas and the SCD Type 2 region table

## Where the data comes from

Page 2 of every NDCU weekly update PDF has **"Table 2: High risk MOH areas"**: each listed MOH area, its district, and its cases for last week and this week.

`src/transform/ndcu_moh_parse.py` reads that table and writes one CSV per PDF to `data/parsed/ndcu_moh/`. The load step then copies it into silver as `ndcu_moh_weekly_cases`.

| Result (37 PDFs, 2026-W01 → W37) | |
|---|---|
| Rows | 2,591 (MOH area × week) |
| Different MOH areas | 236 (each under exactly one district in every week) |
| PDFs quarantined | 0 |

**Only high-risk areas are listed.** If an area isn't listed, it wasn't high-risk that week. It doesn't mean zero cases.

### How the parser reads it
The table layout changes between weeks: font size, letter-spaced text, and header variants like "Week 23 Week 24". So the parser doesn't use fixed positions:

- It finds the table by its title.
- It finds each column group from its "MOH Area" header.
- It finds the case columns from the two "Week" headers.
- Spaced-out names are joined, and only digits inside a count column count as numbers.

The early-2026 PDFs (weeks 1–15) add more variations, all handled and covered by tests:

| Printed as | Weeks | Read as |
|---|---|---|
| "Hambantota" / "Distrcit" on two lines | W02 | Hambantota district heading |
| "Hambantota Distrcit", "Hambanthota District", "Rathnapura District" | W01, W05 | spelling variants, matched to the district (logged) |
| "Hambantota" (no "District"), "Hambanota" | W08–W09, W19–W20 | bare district heading |
| "RatnapuraDistrict", "MataraDistrict" (no space) | W24–W30 | district heading |
| "SABARAGAMUWA" alone, "NOTHERN" / "PROVINCE" | W02, W33 | province heading |
| "CMC", "CMC Colombo" | all | Colombo Municipal Council sub-heading (Colombo) |
| "Gangawata" / "Korale" | W02 | one MOH name on two lines |
| empty "last week" cell (Katana) | W01 | area new to the list: last week = empty |
| "Week 52, Week 01" | W01 | week 1 follows week 52 |

**The parser is strict.** A row without numbers that isn't a known heading or table label stops the whole PDF (quarantine) instead of being skipped. The first version skipped unknown labels, so in weeks where a heading was printed in an unusual way, the MOH areas below it were silently filed under the **previous** district. For example, Katuwana ended up under Matara in W19–W20 because "Hambantota" was printed without "District". This affected the Hambantota rows of W05, W08, W09, W19 and W20; making the parser strict exposed it, and all are fixed.

**Same area, two spellings.** `reference/moh_aliases.csv` lists 13 spelling variants of the same area in the same district (e.g. "Pyagala" / "Payagala", "Udawalwa" / "Udawalawa"), so each area has one key. Look-alike names in different districts (Ambalangoda / Balangoda) are different areas and stay separate.

**Parser versions.** Each CSV records the `parser_version` that made it. After a parser fix the version goes up, and older CSVs are parsed again automatically on the next run.

### Checks
Every PDF is checked before loading. A PDF that fails is quarantined to `data/quarantine/ndcu_moh/` and never loaded. The checks:

- The header weeks must be (W−1, W) for report week W.
- Every district name must be known.
- No MOH area appears twice.
- Every count is between 0 and 5,000.

After loading, dbt checks that the MOH areas in a district never add up to more than the district total for that week (with a tolerance of 2). Gampaha goes over by 1 case in 5 weeks, an inconsistency in the source itself.

**Known exception: 2026-W01 (29 Dec – 4 Jan).** Here the MOH table doesn't add up to page 1: Colombo's MOH areas total 756 against 523 on page 1, and Gampaha, Kandy and Puttalam are also over. Page 1 notes that week 1 was counted over a special split ("last 3 days in 2025 and first 4 days in 2026"), and the MOH table apparently wasn't. W02's report prints both numbers the same way, so this isn't a parsing error. The data is kept as published, and the check skips this one week, with the reason written in the test.

## SCD2: `gold.dim_region`

One row per **version** of an MOH area. Key: `moh_key` (lowercase letters and digits only, so "Bope Poddala" and "Bope-Poddala" are the same area).

| Column | Rule |
|---|---|
| `district` | The district NDCU prints the area under. It changes only if the **same new district is printed in 3 reports in a row**. |
| `parent_moh_area` | For newer areas that were split from an older one (`reference/moh_parents.csv`). |
| `boundary_note` | The first week NDCU reported the area. |
| `valid_from` / `valid_to` | The week a version was **first observed**. The current version has `valid_to = 9999-12-31`. |

**We never invent dates.** Official split dates aren't published. So an area's history starts at the first week we saw it (the earliest weekly PDF loaded), not at the date it was created.

**Why "3 reports in a row":** a real move shows up week after week, while a misprint or misread doesn't. One-off differences are logged as warnings and not applied, and the fact table flags them with `printed_district_differs`. With the strict parser, **no MOH area changes district in the 37 weeks of 2026**, so every area has exactly one version. *(Correction: an earlier version of this page blamed NDCU for printing Katuwana under Matara. It was our parser misreading a heading; see above.)*

**Late reports.** NDCU uploaded the 2026 W18 and W20 reports months late; they appear on page 2 of the archive, next to weeks 1–15. The downloader follows every archive page, and when a report for an older week arrives, `dim_region` is **rebuilt from silver**. That is safe because every version comes from the stored weekly observations, and the keys are deterministic, so the rebuild reproduces history exactly, plus the late week. `gold.dim_region_weeks` records which weeks have been applied.

**Parent areas are unverified.** `reference/moh_parents.csv` comes from the lk_dengue project's mapping, and it isn't an official source:

| Area | Split from |
|---|---|
| Egodauyana | Moratuwa |
| Gothatuwa | Kolonnawa |
| Kesbewa | Piliyandala |
| Madampe | Chilaw |
| Millaniya | Agalawatta |

The dashboard labels this column "(unverified)".

**Point-in-time join.** `gold.fact_dengue_moh_weekly` joins each week to the version that was valid then (`valid_from <= week_start < valid_to`). If an area changes district later, old weeks still show the old version.

**Incremental.** Each run applies only the weeks newer than the last one already applied. The table is never rebuilt, because rebuilding it would lose the history. Snapshots that arrive out of order are rejected.

## Where you see it

- **Dashboard:** the "High-risk MOH areas" expander for the selected week.
- **API:** `GET /moh/hotspots?week=2026-W37&top=10`
- **dbt tests:**
  - `assert_scd2_one_current_row`
  - `assert_scd2_no_overlapping_versions`
  - `assert_ndcu_moh_within_district_total`
  - not-null and relationship tests on the fact table
- **Unit tests:**
  - `tests/test_ndcu_moh.py`: the parser, using the 3 sample PDFs
  - `tests/test_scd2.py`: SCD2 logic on synthetic fixtures in `tests/fixtures/moh_snapshots/`
