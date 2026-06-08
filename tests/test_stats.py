from __future__ import annotations

import pandas as pd
import pytest

from danaleo.core.stats import column_cards, column_stats, dataframe_overview, infer_kind


def test_dataframe_overview_and_column_cards():
    df = pd.DataFrame({"num": [1, 2, None], "cat": ["A", "B", "A"], "flag": [True, False, True]})

    overview = dataframe_overview(df)
    assert overview["rows"] == 3
    assert overview["columns"] == 3
    assert overview["memory_bytes"] > 0

    cards = {card["name"]: card for card in column_cards(df)}
    assert cards["num"]["kind"] == "numeric"
    assert cards["cat"]["kind"] == "categorical"
    assert cards["num"]["missing"] == 1


def test_column_stats_for_numeric_and_categorical_columns():
    df = pd.DataFrame({"num": [1, 2, 3, None], "cat": ["A", "B", "A", None]})

    numeric = column_stats(df, "num")
    assert numeric["kind"] == "numeric"
    assert numeric["stats"]["mean"] == pytest.approx(2.0)
    assert numeric["stats"]["median"] == pytest.approx(2.0)
    assert numeric["missing"] == 1

    categorical = column_stats(df, "cat")
    assert categorical["kind"] == "categorical"
    assert categorical["stats"]["top_values"][0] == {"value": "A", "count": 2}
    assert any(item["value"] == "<missing>" for item in categorical["stats"]["top_values"])


def test_column_stats_rejects_unknown_column():
    with pytest.raises(KeyError):
        column_stats(pd.DataFrame({"x": [1]}), "missing")


def test_infer_kind_handles_dates_and_booleans():
    assert infer_kind(pd.Series([True, False])) == "categorical"
    assert infer_kind(pd.Series(pd.to_datetime(["2026-01-01"]))) == "datetime"
