"""Census 2024 population: parsed numbers must pass the report's own printed checks, or nothing is written."""
from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from src.load import duckdb_load
from src.reference import build_population as bp

DISTRICTS = pd.read_csv(bp.REFERENCE_DIR / "districts.csv")


def table_lines(total_ok: bool = True, drop: str | None = None) -> list[str]:
    """Fake Table 3.2 text: 23 districts share the remainder so the sum matches the report total."""
    fixed = {"gampaha": 2_436_142, "mullaitivu": 122_619}
    others = [d for d in DISTRICTS["district"] if d not in fixed]
    rest = bp.CHECKS["total"] - sum(fixed.values()) - (0 if total_ok else 5)
    each, extra = divmod(rest, len(others))
    pops = {**fixed, **{d: each + (extra if i == 0 else 0) for i, d in enumerate(others)}}
    lines = ["Table 3.2: Distribution of Population by Province and District, 2024", "District Population %"]
    for code, name in zip(DISTRICTS["district"], DISTRICTS["district_name"], strict=True):
        if code != drop:
            lines.append(f"{name} {pops[code]:,} 4.5")
    lines.append(f"Sri Lanka {bp.CHECKS['total']:,} 100.0")
    return lines


def test_valid_table_passes():
    df = bp.validate(bp.parse_lines(table_lines()))
    assert len(df) == 25 and df["population"].sum() == 21_781_800
    assert df.set_index("district").loc["nuwara_eliya", "population"] > 0        # two-word name parsed


def test_wrong_total_rejected():
    with pytest.raises(bp.PopulationError, match="sum to"):
        bp.validate(bp.parse_lines(table_lines(total_ok=False)))


def test_missing_district_rejected():
    with pytest.raises(bp.PopulationError, match="not found"):
        bp.validate(bp.parse_lines(table_lines(drop="kegalle")))


def test_missing_pdf_exit_code(tmp_path):
    assert bp.main(pdf_path=tmp_path / "nope.pdf", out_csv=tmp_path / "out.csv") == 2


def test_loader_with_and_without_csv(tmp_path):
    con = duckdb.connect()
    assert duckdb_load.load_population(con, tmp_path / "missing.csv") == 0       # table exists, empty
    csv = tmp_path / "pop.csv"
    bp.validate(bp.parse_lines(table_lines())).to_csv(csv, index=False)
    assert duckdb_load.load_population(con, csv) == 25
    assert con.execute("SELECT sum(population) FROM district_population").fetchone()[0] == 21_781_800


def test_census_spelling_moneragala_and_toc_ignored():
    lines = [ln.replace("Monaragala", "Moneragala") for ln in table_lines()]
    df = bp.validate(bp.parse_lines(lines))
    assert "monaragala" in set(df["district"])
