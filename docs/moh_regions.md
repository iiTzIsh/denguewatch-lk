# MOH areas and the SCD Type 2 region table

## Where the data comes from

Page 2 of every NDCU weekly update PDF has **"Table 2: High risk MOH areas"**: each listed MOH area, its district, and its cases for last week and this week.

`src/transform/ndcu_moh_parse.py` reads that table and writes one CSV per PDF to `data/parsed/ndcu_moh/`. The load step then copies it into silver as `ndcu_moh_weekly_cases`.

| Result (20 PDFs, 2026-W16 → W37) | |
|---|---|
| Rows | 1,819 (MOH area × week) |
| Different MOH areas | 233 |
| PDFs quarantined | 0 |

**Only high-risk areas are listed.** If an area isn't listed, it wasn't high-risk that week. It doesn't mean zero cases.

### How the parser reads it
The table layout changes between weeks: font size, letter-spaced text, and header variants like "Week 23 Week 24". So the parser doesn't use fixed positions:

- It finds the table by its title.
- It finds each column group from its "MOH Area" header.
- It finds the case columns from the two "Week" headers.
- Spaced-out names are joined, and only digits inside a count column count as numbers.

### Checks
Every PDF is checked before loading. A PDF that fails is quarantined to `data/quarantine/ndcu_moh/` and never loaded. The checks:

- The header weeks must be (W−1, W) for report week W.
- Every district name must be known.
- No MOH area appears twice.
- Every count is between 0 and 5,000.

After loading, dbt checks that the MOH areas in a district never add up to more than the district total for that week (with a tolerance of 2). One district goes over: Gampaha, by 1 case, in 5 weeks. This inconsistency is in the source itself.

## SCD2: `gold.dim_region`

One row per **version** of an MOH area. Key: `moh_key` (lowercase letters and digits only, so "Bope Poddala" and "Bope-Poddala" are the same area).

| Column | Rule |
|---|---|
| `district` | The district NDCU prints the area under. It changes only if the **same new district is printed in 2 reports in a row**. |
| `parent_moh_area` | For newer areas that were split from an older one (`reference/moh_parents.csv`). |
| `boundary_note` | The first week NDCU reported the area. |
| `valid_from` / `valid_to` | The week a version was **first observed**. The current version has `valid_to = 9999-12-31`. |

**We never invent dates.** Official split dates aren't published. So an area's history starts at the first week we saw it (2026-04-13 is the first PDF we have), not at the date it was created.

**Why "2 reports in a row":** in 2026-W19 only, NDCU printed Katuwana under Matara. In every other week it's under Hambantota. A one-off misprint like this is logged as a warning and not applied. A real move would show up week after week. The fact table keeps the printed district and flags these rows with `printed_district_differs` (1 row out of 1,819).

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
