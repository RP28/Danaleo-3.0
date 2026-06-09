from __future__ import annotations

import pandas as pd
import pytest

from danaleo.core.stats import column_cards, column_stats, dataframe_overview, dataset_profile, infer_kind


def test_dataframe_overview_and_column_cards():
    df = pd.DataFrame(
        {
            "num": [1, 2, None],
            "cat": ["A", "B", "A"],
            "flag": [True, False, True],
        }
    )

    overview = dataframe_overview(df)

    assert overview["rows"] == 3
    assert overview["columns"] == 3
    assert overview["memory_bytes"] > 0
    assert overview["memory_mb"] >= 0

    cards = {card["name"]: card for card in column_cards(df)}

    assert cards["num"]["kind"] == "numeric"
    assert cards["cat"]["kind"] == "categorical"
    assert cards["flag"]["kind"] == "categorical"
    assert cards["num"]["missing"] == 1
    assert cards["num"]["unique"] == 2


def test_dataframe_overview_handles_empty_dataframe():
    df = pd.DataFrame({"num": [], "cat": []})

    overview = dataframe_overview(df)

    assert overview["rows"] == 0
    assert overview["columns"] == 2
    assert overview["memory_bytes"] >= 0
    assert overview["memory_mb"] >= 0


def test_dataset_profile_surfaces_quality_relationships_and_preview():
    df = pd.DataFrame(
        {
            "x": [1, 2, 2, None],
            "y": [2, 4, 4, None],
            "group": ["A", "B", "B", None],
        }
    )

    profile = dataset_profile(df)

    assert profile["rows"] == 4
    assert profile["numeric_columns"] == 2
    assert profile["categorical_columns"] == 1
    assert profile["missing_cells"] == 3
    assert profile["duplicate_rows"] == 1
    assert profile["high_missing"][0]["missing_pct"] == 25.0
    assert profile["top_correlations"][0] == {"left": "x", "right": "y", "value": 1.0}
    assert profile["preview_columns"] == ["x", "y", "group"]
    assert len(profile["preview"]) == 4


def test_dataset_profile_handles_empty_datetime_and_wide_dataframes():
    empty = dataset_profile(pd.DataFrame())
    assert empty["rows"] == 0
    assert empty["missing_pct"] == 0.0
    assert empty["preview"] == []

    data = {f"n{i}": [i, i + 1] for i in range(45)}
    data["when"] = pd.to_datetime(["2026-01-01", None])
    profile = dataset_profile(pd.DataFrame(data), preview_rows=1)

    assert profile["datetime_columns"] == 1
    assert profile["correlation_columns_analyzed"] == 40
    assert len(profile["preview_columns"]) == 12
    assert len(profile["preview"]) == 1


def test_column_stats_handles_all_missing_numeric_and_datetime_values():
    df = pd.DataFrame(
        {
            "numeric": pd.Series([None, None], dtype="float64"),
            "when": pd.to_datetime(["2026-01-01", None]),
        }
    )

    numeric = column_stats(df, "numeric")
    when = column_stats(df, "when")

    assert numeric["missing_pct"] == 100.0
    assert all(value is None for value in numeric["stats"].values())
    assert when["kind"] == "datetime"
    assert when["sample_values"] == ["2026-01-01 00:00:00"]


def test_column_stats_for_numeric_and_categorical_columns():
    df = pd.DataFrame({"num": [1, 2, 3, None], "cat": ["A", "B", "A", None]})

    numeric = column_stats(df, "num")

    assert numeric["name"] == "num"
    assert numeric["kind"] == "numeric"
    assert numeric["rows"] == 4
    assert numeric["non_null"] == 3
    assert numeric["missing"] == 1
    assert numeric["stats"]["mean"] == pytest.approx(2.0)
    assert numeric["stats"]["median"] == pytest.approx(2.0)
    assert numeric["stats"]["min"] == pytest.approx(1.0)
    assert numeric["stats"]["max"] == pytest.approx(3.0)

    categorical = column_stats(df, "cat")

    assert categorical["name"] == "cat"
    assert categorical["kind"] == "categorical"
    assert categorical["missing"] == 1
    top_values = {
        item["value"]: item["count"]
        for item in categorical["stats"]["top_values"]
    }
    assert top_values["A"] == 2
    assert top_values["B"] == 1
    assert categorical["missing"] == 1


def test_boolean_column_stats_are_categorical():
    df = pd.DataFrame({"flag": [True, False, True]})

    stats = column_stats(df, "flag")

    assert stats["kind"] == "categorical"
    values = {item["value"]: item["count"] for item in stats["stats"]["top_values"]}
    assert values["True"] == 2
    assert values["False"] == 1


def test_column_stats_rejects_unknown_column():
    with pytest.raises(KeyError, match="Unknown column"):
        column_stats(pd.DataFrame({"x": [1]}), "missing")


def test_infer_kind_handles_dates_booleans_and_numbers():
    assert infer_kind(pd.Series([True, False])) == "categorical"
    assert infer_kind(pd.Series([1, 2, 3])) == "numeric"
    assert infer_kind(pd.Series(pd.to_datetime(["2026-01-01"]))) == "datetime"
    assert infer_kind(pd.Series(["A", "B"])) == "categorical"
