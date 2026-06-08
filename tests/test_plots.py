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
            "group": ["A", "A", "B", "B", "A", "B", "A", "C", "C", "C", "B", "A"],
        }
    )


def assert_png_payload(payload: dict):
    assert payload["renderer"] == "png"
    assert payload["image"].startswith("data:image/png;base64,")
    encoded = payload["image"].split(",", 1)[1]
    raw = base64.b64decode(encoded)
    assert raw.startswith(b"\x89PNG")
    assert len(raw) > 1_000


@pytest.mark.parametrize(
    ("plot_type", "column", "controls"),
    [
        ("histogram", "value", {"bins": 5, "show_kde": True}),
        ("kde", "value", {"points": 80, "bw_adjust": 1.0, "fill": True}),
        ("box", "value", {"split_by": "group"}),
        ("violin", "value", {"split_by": "group"}),
        ("bar_top_n", "group", {"top_n": 3}),
        ("pie_top_n", "group", {"top_n": 3}),
    ],
)
def test_build_figure_returns_browser_safe_png_preview(plot_df, plot_type, column, controls):
    payload = build_figure(plot_df, column, plot_type, controls=controls)
    assert_png_payload(payload)
    assert payload["data"]
    assert payload["layout"]


def test_build_figure_applies_local_query_without_changing_source(plot_df):
    original_rows = len(plot_df)
    payload = build_figure(plot_df, "value", "histogram", local_query="group == 'A'", controls={"bins": 3})

    assert_png_payload(payload)
    assert len(plot_df) == original_rows


def test_build_figure_validates_inputs(plot_df):
    with pytest.raises(ValueError, match="Column not found"):
        build_figure(plot_df, "missing", "histogram")
    with pytest.raises(ValueError, match="returned no rows"):
        build_figure(plot_df, "value", "histogram", local_query="value > 999")
    with pytest.raises(ValueError, match="Unsupported plot type"):
        build_figure(plot_df, "value", "unknown")


def test_plotly_code_keeps_notebook_export_reproducible():
    code = plotly_code("histogram", "df_branch", "value", "group == 'A'", {"bins": 8})

    assert "df_branch_plot = df_branch.query" in code
    assert "px.histogram" in code
    assert "nbins=8" in code
    assert code.endswith("fig.show()")
