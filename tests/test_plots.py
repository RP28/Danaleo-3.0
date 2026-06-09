from __future__ import annotations

import base64

import pandas as pd
import pytest

from danaleo.core.plots import build_figure, plotly_code


@pytest.fixture
def plot_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "value": [10, 12, 14, 15, 18, 19, 21, 24, 28, 30, 34, 36],
            "other": [36, 34, 30, 28, 24, 21, 19, 18, 15, 14, 12, 10],
            "group": ["A", "A", "B", "B", "A", "B", "A", "C", "C", "C", "B", "A"],
            "category": ["x", "x", "y", "z", "z", "z", "x", "y", "y", "y", None, "x"],
        }
    )


def assert_png_payload(payload: dict):
    assert payload["image"].startswith("data:image/png;base64,")
    encoded = payload["image"].split(",", 1)[1]
    raw = base64.b64decode(encoded)

    assert raw.startswith(b"\x89PNG")
    assert len(raw) > 1_000
    assert "column" in payload
    assert "plot_type" in payload
    assert "rows" in payload
    assert "controls" in payload


@pytest.mark.parametrize(
    ("plot_type", "column", "controls"),
    [
        ("histogram", "value", {"bins": 5, "show_kde": True}),
        ("kde", "value", {"points": 80, "bw_adjust": 1.0, "fill": True}),
        ("box", "value", {"show_outliers": True}),
        ("violin", "value", {}),
        ("bar_top_n", "group", {"top_n": 3}),
        ("pie_top_n", "group", {"top_n": 3}),
    ],
)
def test_build_figure_returns_browser_safe_png_preview(plot_df, plot_type, column, controls):
    payload = build_figure(plot_df, column, plot_type, controls=controls)

    assert_png_payload(payload)
    assert payload["column"] == column
    assert payload["plot_type"] == plot_type
    assert payload["rows"] == len(plot_df)


@pytest.mark.parametrize(
    "plot_type",
    ["grouped_kde", "grouped_box", "grouped_violin"],
)
def test_build_figure_supports_grouped_numeric_plots(plot_df, plot_type):
    payload = build_figure(
        plot_df,
        "value",
        plot_type,
        controls={"group_by": "group", "group_limit": 3},
    )

    assert_png_payload(payload)
    assert payload["column"] == "value"
    assert payload["plot_type"] == plot_type


@pytest.mark.parametrize(
    "plot_type",
    ["grouped_kde", "grouped_box", "grouped_violin"],
)
def test_grouped_plots_require_group_by_column(plot_df, plot_type):
    with pytest.raises(ValueError, match="Group by"):
        build_figure(plot_df, "value", plot_type, controls={})


@pytest.mark.parametrize(
    "plot_type",
    ["histogram", "kde", "box", "violin"],
)
def test_subplot_mode_compares_multiple_columns(plot_df, plot_type):
    payload = build_figure(
        plot_df,
        "value",
        plot_type,
        controls={
            "subplot_enabled": True,
            "subplot_columns": ["other"],
            "subplot_cols": 2,
        },
    )

    assert_png_payload(payload)
    assert payload["column"] == "value"
    assert payload["controls"]["subplot_enabled"] is True


def test_top_n_plots_work_for_numeric_columns_too(plot_df):
    bar_payload = build_figure(plot_df, "value", "bar_top_n", controls={"top_n": 5})
    pie_payload = build_figure(plot_df, "value", "pie_top_n", controls={"top_n": 5})

    assert_png_payload(bar_payload)
    assert_png_payload(pie_payload)
    assert bar_payload["column"] == "value"
    assert pie_payload["column"] == "value"


@pytest.mark.parametrize(
    ("plot_type", "controls"),
    [
        ("scatter", {"compare_with": "other", "group_by": "group", "alpha": 0.6}),
        ("hexbin", {"compare_with": "other", "gridsize": 18}),
        ("line", {"compare_with": "other", "sort_x": True, "show_markers": True}),
        ("correlation_heatmap", {"show_values": True}),
        ("missing_values", {"top_n": 8}),
    ],
)
def test_build_figure_supports_relationship_and_quality_plots(plot_df, plot_type, controls):
    payload = build_figure(plot_df, "value", plot_type, controls=controls)

    assert_png_payload(payload)
    assert payload["plot_type"] == plot_type


@pytest.mark.parametrize("plot_type", ["scatter", "hexbin", "line"])
def test_relationship_plots_require_comparison_column(plot_df, plot_type):
    with pytest.raises(ValueError, match="Compare with"):
        build_figure(plot_df, "value", plot_type)


def test_plot_visual_settings_are_preserved(plot_df):
    payload = build_figure(
        plot_df,
        "group",
        "bar_top_n",
        controls={
            "top_n": 3,
            "orientation": "horizontal",
            "sort_order": "ascending",
            "chart_title": "Custom title",
            "show_grid": False,
        },
    )

    assert_png_payload(payload)
    assert payload["controls"]["orientation"] == "horizontal"
    assert payload["controls"]["chart_title"] == "Custom title"


def test_build_figure_applies_local_query_without_changing_source(plot_df):
    original_rows = len(plot_df)

    payload = build_figure(
        plot_df,
        "value",
        "histogram",
        local_query="group == 'A'",
        controls={"bins": 3},
    )

    assert_png_payload(payload)
    assert payload["rows"] == 5
    assert len(plot_df) == original_rows


def test_build_figure_validates_inputs(plot_df):
    with pytest.raises(KeyError, match="Unknown column"):
        build_figure(plot_df, "missing", "histogram")

    with pytest.raises(ValueError, match="returned no rows"):
        build_figure(plot_df, "value", "histogram", local_query="value > 999")

    with pytest.raises(ValueError, match="Unsupported plot type"):
        build_figure(plot_df, "value", "unknown")


def test_subplot_rejects_unknown_column(plot_df):
    with pytest.raises(KeyError, match="Unknown column"):
        build_figure(
            plot_df,
            "value",
            "histogram",
            controls={
                "subplot_enabled": True,
                "subplot_columns": ["missing"],
            },
        )


def test_plotly_code_keeps_notebook_export_reproducible():
    code = plotly_code(
        "histogram",
        "df_branch",
        "value",
        "group == 'A'",
        {"bins": 8},
    )

    assert "from danaleo.core.plots import build_figure" in code
    assert "_danaleo_plot = build_figure(" in code
    assert "df_branch" in code
    assert "column='value'" in code
    assert "plot_type='histogram'" in code
    assert "local_query=\"group == 'A'\"" in code
    assert "controls={'bins': 8}" in code
    assert "display(Image(data=b64decode(_danaleo_png)))" in code
