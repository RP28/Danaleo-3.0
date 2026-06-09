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
    assert parse_scalar("  abc  ") == "abc"
    assert parse_scalar("1e3") == 1000.0


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

    spaced = apply_operation(
        df,
        "replace_values",
        {
            "column": "category",
            "old_value": " A, B ",
            "new_value": " Alpha, Beta ",
            "multiple": True,
        },
    )
    assert spaced["category"].tolist()[:3] == ["Alpha", "Beta", "Alpha"]

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


def test_replace_values_supports_nan_and_statistical_replacements():
    df = pd.DataFrame(
        {
            "value": [1.0, -999.0, 3.0, -999.0],
            "label": ["bad", "A", "A", "B"],
        }
    )

    missing = apply_operation(
        df,
        "replace_values",
        {"column": "value", "old_value": "-999", "replacement_method": "nan"},
    )
    mean = apply_operation(
        df,
        "replace_values",
        {"column": "value", "old_value": "-999", "replacement_method": "mean"},
    )
    median = apply_operation(
        df,
        "replace_values",
        {"column": "value", "old_value": "-999", "replacement_method": "median"},
    )
    mode = apply_operation(
        df,
        "replace_values",
        {"column": "label", "old_value": "bad", "replacement_method": "mode"},
    )

    assert missing["value"].isna().sum() == 2
    assert mean["value"].tolist() == [1.0, 2.0, 3.0, 2.0]
    assert median["value"].tolist() == [1.0, 2.0, 3.0, 2.0]
    assert mode["label"].tolist() == ["A", "A", "A", "B"]
    assert df["value"].tolist() == [1.0, -999.0, 3.0, -999.0]


def test_replace_values_validates_statistical_replacements():
    df = pd.DataFrame({"label": ["bad", "A"], "only": [1, 1]})

    with pytest.raises(ValueError, match="Unsupported replacement method"):
        apply_operation(
            df,
            "replace_values",
            {"column": "label", "old_value": "bad", "replacement_method": "magic"},
        )
    with pytest.raises(ValueError, match="requires a numeric column"):
        apply_operation(
            df,
            "replace_values",
            {"column": "label", "old_value": "bad", "replacement_method": "mean"},
        )
    with pytest.raises(ValueError, match="requires at least one remaining value"):
        apply_operation(
            df,
            "replace_values",
            {"column": "only", "old_value": "1", "replacement_method": "median"},
        )


def test_drop_duplicates_removes_exact_duplicate_rows():
    df = pd.DataFrame({"x": [1, 1, 2], "group": ["A", "A", "B"]})

    result = apply_operation(df, "drop_duplicates", {})

    assert result.to_dict(orient="records") == [{"x": 1, "group": "A"}, {"x": 2, "group": "B"}]
    assert len(df) == 3

    unchanged = apply_operation(result, "drop_duplicates", {})
    assert unchanged.equals(result)
    assert unchanged is not result


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("mean", [1.0, 3.0, 5.0, 3.0]),
        ("median", [1.0, 3.0, 5.0, 3.0]),
        ("mode", [1.0, 3.0, 5.0, 1.0]),
        ("constant", [1.0, 3.0, 5.0, 99.0]),
        ("forward_fill", [1.0, 3.0, 5.0, 5.0]),
        ("backward_fill", [1.0, 3.0, 5.0, None]),
        ("interpolate", [1.0, 3.0, 5.0, 5.0]),
    ],
)
def test_impute_missing_supports_common_methods(method, expected):
    df = pd.DataFrame({"value": [1.0, 3.0, 5.0, None]})
    params = {"column": "value", "method": method}
    if method == "constant":
        params["value"] = "99"

    if method == "backward_fill":
        with pytest.raises(ValueError, match="could not fill any values"):
            apply_operation(df, "impute_missing", params)
        return

    result = apply_operation(df, "impute_missing", params)

    assert result["value"].tolist() == expected
    assert df["value"].isna().sum() == 1


def test_impute_missing_supports_text_mode_and_directional_fill():
    df = pd.DataFrame({"label": [None, "A", None, "A", "B", None]})

    mode = apply_operation(df, "impute_missing", {"column": "label", "method": "mode"})
    forward = apply_operation(df, "impute_missing", {"column": "label", "method": "forward_fill"})
    backward = apply_operation(df, "impute_missing", {"column": "label", "method": "backward_fill"})

    assert mode["label"].tolist() == ["A", "A", "A", "A", "B", "A"]
    assert forward["label"].isna().sum() == 1
    assert backward["label"].isna().sum() == 1


def test_impute_missing_validates_column_method_and_dtype():
    df = pd.DataFrame({"label": ["A", None], "complete": [1, 2], "empty": [None, None]})

    with pytest.raises(ValueError, match="Column not found"):
        apply_operation(df, "impute_missing", {"column": "missing", "method": "mode"})
    with pytest.raises(ValueError, match="Unsupported imputation method"):
        apply_operation(df, "impute_missing", {"column": "label", "method": "magic"})
    with pytest.raises(ValueError, match="requires a numeric column"):
        apply_operation(df, "impute_missing", {"column": "label", "method": "mean"})
    with pytest.raises(ValueError, match="has no missing values"):
        apply_operation(df, "impute_missing", {"column": "complete", "method": "mean"})
    with pytest.raises(ValueError, match="requires at least one non-missing value"):
        apply_operation(df, "impute_missing", {"column": "empty", "method": "mode"})
    with pytest.raises(ValueError, match="requires a replacement value"):
        apply_operation(df, "impute_missing", {"column": "label", "method": "constant"})


def test_transform_column_supports_one_hot_and_ordinal_encoding():
    df = pd.DataFrame({"category": ["low", "high", None, "low"], "keep": [1, 2, 3, 4]})

    one_hot = apply_operation(df, "transform_column", {"column": "category", "method": "one_hot"})
    ordinal = apply_operation(
        df,
        "transform_column",
        {"column": "category", "method": "ordinal", "order": "low, high"},
    )
    sorted_ordinal = apply_operation(
        df,
        "transform_column",
        {"column": "category", "method": "ordinal"},
    )

    assert one_hot.columns.tolist() == ["keep", "category_high", "category_low"]
    assert one_hot["category_high"].tolist() == [0, 1, 0, 0]
    assert one_hot["category_low"].tolist() == [1, 0, 0, 1]
    assert ordinal["category"].tolist() == [0, 1, pd.NA, 0]
    assert sorted_ordinal["category"].tolist() == [1, 0, pd.NA, 1]
    assert df.columns.tolist() == ["category", "keep"]


def test_transform_column_supports_numeric_scaling():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, None]})

    min_max = apply_operation(df, "transform_column", {"column": "value", "method": "min_max"})
    standardized = apply_operation(
        df,
        "transform_column",
        {"column": "value", "method": "standardize"},
    )

    assert min_max["value"].tolist()[:3] == [0.0, 0.5, 1.0]
    assert min_max["value"].isna().sum() == 1
    assert standardized["value"].mean() == pytest.approx(0)
    assert standardized["value"].std(ddof=0) == pytest.approx(1)
    assert standardized["value"].isna().sum() == 1


def test_transform_column_validates_methods_types_orders_and_output_collisions():
    df = pd.DataFrame(
        {
            "category": ["low", "high"],
            "category_low": [1, 0],
            "constant": [5, 5],
            "empty": [None, None],
        }
    )

    with pytest.raises(ValueError, match="Column not found"):
        apply_operation(df, "transform_column", {"column": "missing", "method": "one_hot"})
    with pytest.raises(ValueError, match="Unsupported transformation method"):
        apply_operation(df, "transform_column", {"column": "category", "method": "magic"})
    with pytest.raises(ValueError, match="requires a numeric column"):
        apply_operation(df, "transform_column", {"column": "category", "method": "min_max"})
    with pytest.raises(ValueError, match="at least two distinct"):
        apply_operation(df, "transform_column", {"column": "constant", "method": "standardize"})
    with pytest.raises(ValueError, match="must include every non-missing value"):
        apply_operation(
            df,
            "transform_column",
            {"column": "category", "method": "ordinal", "order": "low"},
        )
    with pytest.raises(ValueError, match="cannot contain duplicates"):
        apply_operation(
            df,
            "transform_column",
            {"column": "category", "method": "ordinal", "order": "low, low, high"},
        )
    with pytest.raises(ValueError, match="already exist"):
        apply_operation(df, "transform_column", {"column": "category", "method": "one_hot"})
    with pytest.raises(ValueError, match="requires at least one non-missing value"):
        apply_operation(df, "transform_column", {"column": "empty", "method": "one_hot"})
    with pytest.raises(ValueError, match="requires at least one non-missing value"):
        apply_operation(df, "transform_column", {"column": "empty", "method": "ordinal"})


def test_unsupported_operation_type_is_rejected():
    with pytest.raises(ValueError, match="Unsupported operation"):
        apply_operation(sample_df(), "explode_everything", {})


def test_operation_labels_are_human_readable():
    assert operation_label("filter_rows", {"query": "x > 0"}) == "Filter: x > 0"
    assert operation_label("drop_column", {"column": "x"}) == "Drop column: x"
    assert operation_label("replace_values", {"column": "x"}) == "Replace in x"
    assert operation_label("drop_missing", {"column": "x"}) == "Drop missing: x"
    assert operation_label("drop_duplicates", {}) == "Drop duplicate rows"
    assert operation_label("impute_missing", {"column": "x", "method": "forward_fill"}) == "Impute x: Forward Fill"
    assert operation_label("transform_column", {"column": "x", "method": "min_max"}) == "Transform x: Min Max"
    assert operation_label("unknown_op", {}) == "Unknown Op"
