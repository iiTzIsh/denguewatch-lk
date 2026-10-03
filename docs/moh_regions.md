# MOH areas and the SCD Type 2 region dimension

## Source

Page 2 of each NDCU weekly update, "Table 2: High risk MOH areas", lists each high-risk Medical Officer of Health
area with its district and its cases for last week and this week. An area that is not listed was not high-risk
that week; it does not mean zero cases.

`src/transform/ndcu_moh_parse.py` writes one CSV per PDF to `data/parsed/ndcu_moh/`, loaded into silver as
`ndcu_moh_weekly_cases`. For 2026 weeks 1-37: 37 PDFs, 2,591 rows, 236 MOH areas, none quarantined.

## Parsing

The layout varies between weeks (font size, letter-spaced text, header variants), so rows are rebuilt from word
positions: the table is located by its title, column groups by their "MOH Area" headers and count columns by the
two "Week" headers. Variants handled, each covered by a test:

| Printed as | Weeks | Read as |
|---|---|---|
| "Hambantota" / "Distrcit" on two lines | W02 | district heading |
| "Hambantota Distrcit", "Hambanthota District", "Rathnapura District" | W01, W05 | district heading (spelling variant, logged) |
| "Hambantota" or "Hambanota" without "District" | W08-W09, W19-W20 | district heading |
| "RatnapuraDistrict" (no space) | W24-W30 | district heading |
| "SABARAGAMUWA" alone, "NOTHERN" / "PROVINCE" | W02, W33 | province heading |
| "CMC", "CMC Colombo" | all | Colombo Municipal Council, part of Colombo district |
| "Gangawata" / "Korale" | W02 | one MOH name over two lines |
| empty "last week" cell | W01 | area new to the list; last week is NULL |
| "Week 52", "Week 01" | W01 | week 1 follows week 52 |

The parser is strict: a row without counts that is not a known heading or table label quarantines the PDF instead
of being skipped, because skipping an unrecognised heading would file the following rows under the previous
district. Other checks: header weeks must be (W-1, W), every district must be known, no area may appear twice and
counts must be between 0 and 5,000.

Each CSV records the `parser_version` that produced it; when the parsing rules change, older CSVs are parsed again
on the next run.

`reference/moh_aliases.csv` maps 13 spelling variants of the same area in the same district (for example "Pyagala"
and "Payagala") to one key. Similar names in different districts (Ambalangoda, Balangoda) are separate areas.

After loading, dbt checks that the MOH areas of a district never add up to more than the district total for the
week, with a tolerance of 2 cases (Gampaha is 1 case over in five weeks in the source). 2026-W01 is excluded: its
page-1 totals were counted over a special split of the year boundary and its MOH table was not (Colombo's MOH rows
add up to 756 against 523 on page 1, and the W02 report repeats both figures).

## `gold.dim_region`

One row per version of an MOH area. The natural key `moh_key` keeps only lowercase letters and digits, so
"Bope Poddala" and "Bope-Poddala" are the same area.

| Column | Rule |
|---|---|
| `district` | district the area is printed under; a change is applied only after 3 consecutive reports |
| `parent_moh_area` | older area it was split from (`reference/moh_parents.csv`) |
| `boundary_note` | first week the area was reported |
| `valid_from`, `valid_to` | week a version was first observed; the current version ends on 9999-12-31 |

- **Observed dates only.** Official split dates are not published, so history starts at the first week an area
  appears in the loaded reports.
- **Change detection.** A change in a tracked column closes the current version and opens a new one. In the 37
  weeks of 2026 no area changed district, so every area has one version; one-off differences are logged and
  flagged in the fact table (`printed_district_differs`).
- **Incremental with rebuild on late reports.** Each run merges only weeks newer than the last applied week. If a
  report for an earlier week arrives (NDCU uploaded 2026 weeks 18 and 20 months late), the dimension is rebuilt
  from silver. This is deterministic because every version comes from stored observations and the surrogate key is
  `md5(moh_key | valid_from)`. `gold.dim_region_weeks` records the applied weeks.
- **Point-in-time join.** `gold.fact_dengue_moh_weekly` joins each week to the version valid at the time
  (`valid_from <= week_start < valid_to`).

Parent areas come from the lk_dengue project's mapping and are not official; the dashboard marks them unverified:

| Area | Split from |
|---|---|
| Egodauyana | Moratuwa |
| Gothatuwa | Kolonnawa |
| Kesbewa | Piliyandala |
| Madampe | Chilaw |
| Millaniya | Agalawatta |

## Tests

- dbt: `assert_scd2_one_current_row`, `assert_scd2_no_overlapping_versions`,
  `assert_ndcu_moh_within_district_total`, plus not-null and relationship tests on the fact table.
- pytest: `tests/test_ndcu_moh.py` (parser, on three real PDFs and the heading variants) and `tests/test_scd2.py`
  (merge mechanics, point-in-time lookup, late-report rebuild).
