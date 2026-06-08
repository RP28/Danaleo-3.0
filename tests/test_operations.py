from __future__ import annotations

import pandas as pd
import pytest

from danaleo.core.operations import apply_operation, operation_label, parse_scalar


def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "x": [1, -2, 3, None],
            "category": ["A", "B", "A", "C"],
            "label": ["old", "old", "keep", None],
            "flag": [True, False, True, False],
        }
    )


def test_parse_scalar_supports_common_input_types():
    assert parse_scalar("12") == 12
    assert parse_scalar("-12") == -12
    assert parse_scalar("12.5") == 12.5
    assert parse_scalar("true") is True
    assert parse_scalar("FALSE") is False
    assert pd.isna(parse_scalar("null"))
    assert pd.isna(parse_scalar("none"))
    assert pd.isna(parse_scalar("nan"))
    assert parse_scalar("abc") == "abc"


def test_filter_rows_returns_copy_and_rejects_empty_query():
    df = sample_df()

    filtered = apply_operation(df, "filter_rows", {"query": "x > 0"})

    assert filtered["x"].tolist() == [1.0, 3.0]
    assert filtered is not df
    assert len(df) == 4

    with pytest.raises(ValueError, match="Filter query cannot be empty"):
        apply_operation(df, "filter_rows", {"query": ""})


def test_filter_rows_supports_backtick_column_names():
    df = pd.DataFrame({"Age Years": [18, 21, 35], "city": ["Sydney", "Perth", "Sydney"]})

    result = apply_operation(df, "filter_rows", {"query": "`Age Years` >= 21"})

    assert result["Age Years"].tolist() == [21, 35]


def test_filter_rows_rejects_filters_that_remove_everything():
    with pytest.raises(ValueError, match="returned no rows"):
        apply_operation(sample_df(), "filter_rows", {"query": "x > 999"})


def test_drop_column_and_missing_are_validated():
    df = sample_df()

    dropped = apply_operation(df, "drop_column", {"column": "label"})
    assert "label" not in dropped.columns
    assert "label" in df.columns

    no_missing = apply_operation(df, "drop_missing", {"column": "x"})
    assert no_missing["x"].isna().sum() == 0

    with pytest.raises(ValueError, match="Column not found"):
        apply_operation(df, "drop_column", {"column": "missing"})

    with pytest.raises(ValueError, match="Column not found"):
        apply_operation(df, "drop_missing", {"column": "missing"})

    with pytest.raises(ValueError, match="would remove all rows"):
        apply_operation(pd.DataFrame({"x": [None, None]}), "drop_missing", {"column": "x"})


def test_replace_values_supports_single_and_multiple_replacements():
    df = sample_df()

    single = apply_operation(
        df,
        "replace_values",
        {"column": "label", "old_value": "old", "new_value": "new"},
    )
    assert single["label"].tolist()[:2] == ["new", "new"]

    multiple = apply_operation(
        df,
        "replace_values",
        {
            "column": "category",
            "old_value": "A,B",
            "new_value": "Alpha,Beta",
            "multiple": True,
        },
    )
    assert multiple["category"].tolist()[:3] == ["Alpha", "Beta", "Alpha"]

    with pytest.raises(ValueError, match="same comma-separated count"):
        apply_operation(
            df,
            "replace_values",
            {
                "column": "category",
                "old_value": "A,B",
                "new_value": "Alpha",
                "multiple": True,
            },
        )


def test_replace_values_supports_boolean_values():
    df = sample_df()

    replaced = apply_operation(
        df,
        "replace_values",
        {"column": "flag", "old_value": "true", "new_value": "false"},
    )

    assert replaced["flag"].tolist() == [False, False, False, False]


def test_unsupported_operation_type_is_rejected():
    with pytest.raises(ValueError, match="Unsupported operation"):
        apply_operation(sample_df(), "explode_everything", {})


def test_operation_labels_are_human_readable():
    assert operation_label("filter_rows", {"query": "x > 0"}) == "Filter: x > 0"
    assert operation_label("drop_column", {"column": "x"}) == "Drop column: x"
    assert operation_label("replace_values", {"column": "x"}) == "Replace in x"
    assert operation_label("drop_missing", {"column": "x"}) == "Drop missing: x"
    assert operation_label("unknown_op", {}) == "Unknown Op"