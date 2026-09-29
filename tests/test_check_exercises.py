from __future__ import annotations

import pandas as pd

from src.load.check_exercises import has_query, normalise


def test_has_query_ignores_comments():
    assert not has_query("-- EX01: select the wettest week\n\n")
    assert has_query("-- title\nSELECT 1")


def test_normalise_ignores_row_and_column_order():
    a = pd.DataFrame({"x": [1, 2], "y": ["b", "a"]})
    b = pd.DataFrame({"y": ["a", "b"], "x": [2, 1]})
    assert normalise(a).equals(normalise(b))
