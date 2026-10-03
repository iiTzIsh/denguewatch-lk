"""WER history (denguedatahub) -> tidy + validated. Uses a tiny hand-made frame, no download."""

from __future__ import annotations

import pandas as pd
import pytest

from src.extract import wer_history as wh


def raw(rows):
    return pd.DataFrame(rows, columns=["year", "week", "start.date", "end.date", "district", "cases"])


def test_names_are_mapped_incl_aliases():
    df = wh.tidy(
        raw(
            [
                (2025.0, 1.0, "12/28/2024", "1/3/2025", "Colombo", 10.0),
                (2025.0, 1.0, "12/28/2024", "1/3/2025", "Kalmune", 2.0),  # source spelling
                (2025.0, 1.0, "12/28/2024", "1/3/2025", "NuwaraEliya", 0.0),
            ]
        )
    )
    assert df["rdhs"].tolist() == ["colombo", "kalmunai", "nuwara_eliya"]
    assert df["cases"].dtype == "int64" and (df["week_days"] == 7).all()
    assert (df["week_start_day"] == "Saturday").all()


def test_unknown_region_fails_loudly():
    with pytest.raises(wh.WERHistoryError, match="Atlantis"):
        wh.tidy(raw([(2025.0, 1.0, "12/28/2024", "1/3/2025", "Atlantis", 1.0)]))


@pytest.mark.parametrize("bad", [-1.0, 2.5, None])
def test_bad_case_values_fail(bad):
    with pytest.raises(wh.WERHistoryError, match="whole numbers"):
        wh.tidy(raw([(2025.0, 1.0, "12/28/2024", "1/3/2025", "Colombo", bad)]))


def test_duplicates_fail():
    r = (2025.0, 1.0, "12/28/2024", "1/3/2025", "Colombo", 1.0)
    with pytest.raises(wh.WERHistoryError, match="duplicate"):
        wh.tidy(raw([r, r]))


def test_iso_weeks_of_2026_are_kept_as_reported():
    df = wh.tidy(raw([(2026.0, 1.0, "12/29/2025", "1/4/2026", "Colombo", 5.0)]))
    assert df.loc[0, "week_start_day"] == "Monday" and df.loc[0, "week_days"] == 7
