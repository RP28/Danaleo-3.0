from __future__ import annotations

import base64
import math
from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype


SUPPORTED_PLOT_TYPES = {
    "histogram",
    "kde",
    "box",
    "violin",
    "bar_top_n",
    "pie_top_n",
    "grouped_kde",
    "grouped_box",
    "grouped_violin",
}


def _as_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default

    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)

    return result


def _as_float(value: Any, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default

    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)

    return result


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _apply_local_query(df: pd.DataFrame, local_query: str) -> pd.DataFrame:
    query = str(local_query or "").strip()
    if not query:
        return df.copy()

    result = df.query(query).copy()
    if result.empty:
        raise ValueError("Local plot filter returned no rows")

    return result


def _require_column(df: pd.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise KeyError(f"Unknown column: {column}")


def _numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    _require_column(df, column)
    series = pd.to_numeric(df[column], errors="coerce").dropna()

    if series.empty:
        raise ValueError(f"Column {column!r} has no numeric values to plot")

    return series.astype(float)


def _category_series(df: pd.DataFrame, column: str) -> pd.Series:
    _require_column(df, column)
    series = df[column].astype("string").fillna("<missing>")
    series = series.replace("", "<empty>")
    return series


def _safe_title(value: str) -> str:
    return value.replace("_", " ").title()


def _format_axis_labels(ax: plt.Axes, rotation: int = 35) -> None:
    ax.tick_params(axis="x", labelrotation=rotation)
    for label in ax.get_xticklabels():
        label.set_ha("right")


def _encode_figure(fig: plt.Figure) -> dict[str, Any]:
    buffer = BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=145, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"image": f"data:image/png;base64,{encoded}"}


def _kde_values(values: np.ndarray, points: int = 160, bw_adjust: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    clean = values[np.isfinite(values)]

    if clean.size < 2:
        raise ValueError("KDE needs at least two numeric values")

    if clean.size > 3000:
        positions = np.linspace(0, clean.size - 1, 3000).astype(int)
        clean = np.sort(clean)[positions]

    minimum = float(np.min(clean))
    maximum = float(np.max(clean))

    if math.isclose(minimum, maximum):
        minimum -= 0.5
        maximum += 0.5

    points = max(40, int(points))
    xs = np.linspace(minimum, maximum, points)

    std = float(np.std(clean, ddof=1)) if clean.size > 1 else 0.0
    bandwidth = 1.06 * std * (clean.size ** (-1 / 5)) if std > 0 else (maximum - minimum) / 20
    bandwidth = max(float(bandwidth) * max(float(bw_adjust), 0.05), 1e-9)

    z = (xs[:, None] - clean[None, :]) / bandwidth
    density = np.exp(-0.5 * z * z).mean(axis=1) / (bandwidth * math.sqrt(2 * math.pi))

    return xs, density


def _draw_histogram(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    series = _numeric_series(df, column)
    bins = _as_int(controls.get("bins"), 30, minimum=2, maximum=200)
    show_kde = _as_bool(controls.get("show_kde"), False)

    ax.hist(series.to_numpy(), bins=bins, density=show_kde, alpha=0.82)
    ax.set_title(f"Histogram — {column}")
    ax.set_xlabel(column)
    ax.set_ylabel("Density" if show_kde else "Count")

    if show_kde and len(series) >= 2:
        xs, density = _kde_values(
            series.to_numpy(),
            points=_as_int(controls.get("points"), 160, minimum=40, maximum=500),
            bw_adjust=_as_float(controls.get("bw_adjust"), 1.0, minimum=0.05, maximum=10),
        )
        ax.plot(xs, density, linewidth=2)


def _draw_kde(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    series = _numeric_series(df, column)
    xs, density = _kde_values(
        series.to_numpy(),
        points=_as_int(controls.get("points"), 160, minimum=40, maximum=500),
        bw_adjust=_as_float(controls.get("bw_adjust"), 1.0, minimum=0.05, maximum=10),
    )

    ax.plot(xs, density, linewidth=2)

    if _as_bool(controls.get("fill"), True):
        ax.fill_between(xs, density, alpha=0.25)

    ax.set_title(f"KDE — {column}")
    ax.set_xlabel(column)
    ax.set_ylabel("Density")


def _draw_box(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    series = _numeric_series(df, column)
    show_outliers = _as_bool(controls.get("show_outliers"), True)

    ax.boxplot(series.to_numpy(), vert=True, showfliers=show_outliers)
    ax.set_title(f"Box plot — {column}")
    ax.set_xticklabels([column])
    ax.set_ylabel(column)


def _draw_violin(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    series = _numeric_series(df, column)

    ax.violinplot(series.to_numpy(), showmeans=True, showmedians=True)
    ax.set_title(f"Violin plot — {column}")
    ax.set_xticks([1])
    ax.set_xticklabels([column])
    ax.set_ylabel(column)


def _top_n_data(df: pd.DataFrame, column: str, top_n: int, plot_type: str) -> tuple[list[str], list[float], str]:
    _require_column(df, column)
    series = df[column]

    if is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce").dropna()

        if numeric.empty:
            raise ValueError(f"Column {column!r} has no numeric values to plot")

        counts = numeric.value_counts(dropna=False).head(top_n)

        labels = [str(value) for value in counts.index.tolist()]
        values = [float(count) for count in counts.tolist()]
        y_label = "Count"

    else:
        counts = _category_series(df, column).value_counts(dropna=False).head(top_n)

        labels = [str(value) for value in counts.index.tolist()]
        values = [float(count) for count in counts.tolist()]
        y_label = "Count"

    if not values:
        raise ValueError(f"No values available for Top {top_n}")

    return labels, values, y_label


def _draw_top_n_bar(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    top_n = _as_int(controls.get("top_n"), 15, minimum=1, maximum=100)
    labels, values, y_label = _top_n_data(df, column, top_n, "bar_top_n")

    ax.bar(labels, values)
    ax.set_title(f"Top {len(values)} values — {column}")
    ax.set_xlabel(column)
    ax.set_ylabel(y_label)
    _format_axis_labels(ax)


def _draw_top_n_pie(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    top_n = _as_int(controls.get("top_n"), 15, minimum=1, maximum=100)
    labels, values, _ = _top_n_data(df, column, top_n, "pie_top_n")

    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title(f"Top {len(values)} values share — {column}")
    ax.axis("equal")


def _limited_groups(df: pd.DataFrame, group_column: str, limit: int) -> list[str]:
    groups = _category_series(df, group_column).value_counts(dropna=False).head(limit)
    return [str(group) for group in groups.index.tolist()]


def _draw_grouped_kde(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    group_column = str(controls.get("group_by") or "").strip()
    if not group_column:
        raise ValueError("Choose a categorical column in Group by")

    _require_column(df, group_column)
    limit = _as_int(controls.get("group_limit"), 8, minimum=1, maximum=30)
    groups = _limited_groups(df, group_column, limit)
    group_values = _category_series(df, group_column)

    for group in groups:
        sub_df = df[group_values == group]
        series = _numeric_series(sub_df, column)

        if len(series) < 2:
            continue

        xs, density = _kde_values(
            series.to_numpy(),
            points=_as_int(controls.get("points"), 160, minimum=40, maximum=500),
            bw_adjust=_as_float(controls.get("bw_adjust"), 1.0, minimum=0.05, maximum=10),
        )

        ax.plot(xs, density, linewidth=2, label=group)

        if _as_bool(controls.get("fill"), True):
            ax.fill_between(xs, density, alpha=0.12)

    ax.set_title(f"KDE — {column} by {group_column}")
    ax.set_xlabel(column)
    ax.set_ylabel("Density")
    ax.legend(fontsize=8)


def _grouped_numeric_values(df: pd.DataFrame, column: str, group_column: str, limit: int) -> tuple[list[str], list[np.ndarray]]:
    _require_column(df, group_column)
    group_values = _category_series(df, group_column)
    groups = _limited_groups(df, group_column, limit)

    labels: list[str] = []
    values: list[np.ndarray] = []

    for group in groups:
        sub_df = df[group_values == group]
        numeric = _numeric_series(sub_df, column).to_numpy()

        if numeric.size:
            labels.append(group)
            values.append(numeric)

    if not values:
        raise ValueError("No grouped numeric values available to plot")

    return labels, values


def _draw_grouped_box(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    group_column = str(controls.get("group_by") or "").strip()
    if not group_column:
        raise ValueError("Choose a categorical column in Group by")

    labels, values = _grouped_numeric_values(
        df,
        column,
        group_column,
        _as_int(controls.get("group_limit"), 8, minimum=1, maximum=30),
    )

    ax.boxplot(values, labels=labels, showfliers=_as_bool(controls.get("show_outliers"), True))
    ax.set_title(f"Box plot — {column} by {group_column}")
    ax.set_ylabel(column)
    _format_axis_labels(ax)


def _draw_grouped_violin(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    group_column = str(controls.get("group_by") or "").strip()
    if not group_column:
        raise ValueError("Choose a categorical column in Group by")

    labels, values = _grouped_numeric_values(
        df,
        column,
        group_column,
        _as_int(controls.get("group_limit"), 8, minimum=1, maximum=30),
    )

    ax.violinplot(values, showmeans=True, showmedians=True)
    ax.set_title(f"Violin plot — {column} by {group_column}")
    ax.set_ylabel(column)
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels)
    _format_axis_labels(ax)


def _draw_one(ax: plt.Axes, df: pd.DataFrame, column: str, plot_type: str, controls: dict[str, Any]) -> None:
    if plot_type == "histogram":
        _draw_histogram(ax, df, column, controls)
    elif plot_type == "kde":
        _draw_kde(ax, df, column, controls)
    elif plot_type == "box":
        _draw_box(ax, df, column, controls)
    elif plot_type == "violin":
        _draw_violin(ax, df, column, controls)
    elif plot_type == "bar_top_n":
        _draw_top_n_bar(ax, df, column, controls)
    elif plot_type == "pie_top_n":
        _draw_top_n_pie(ax, df, column, controls)
    elif plot_type == "grouped_kde":
        _draw_grouped_kde(ax, df, column, controls)
    elif plot_type == "grouped_box":
        _draw_grouped_box(ax, df, column, controls)
    elif plot_type == "grouped_violin":
        _draw_grouped_violin(ax, df, column, controls)
    else:
        raise ValueError(f"Unsupported plot type: {plot_type}")


def _subplot_columns(column: str, controls: dict[str, Any]) -> list[str]:
    raw_columns = controls.get("subplot_columns") or []

    if isinstance(raw_columns, str):
        raw_columns = [raw_columns]

    if not isinstance(raw_columns, list):
        raw_columns = []

    columns: list[str] = []
    for value in [column, *raw_columns]:
        if isinstance(value, str) and value and value not in columns:
            columns.append(value)

    limit = _as_int(controls.get("subplot_limit"), 12, minimum=2, maximum=30)
    return columns[:limit]


def _build_subplot_figure(
    df: pd.DataFrame,
    column: str,
    plot_type: str,
    controls: dict[str, Any],
) -> dict[str, Any]:
    columns = _subplot_columns(column, controls)

    if len(columns) < 2:
        raise ValueError("Choose at least two columns for subplot mode")

    cols_per_row = _as_int(controls.get("subplot_cols"), 2, minimum=1, maximum=4)
    rows = math.ceil(len(columns) / cols_per_row)

    fig, axes = plt.subplots(
        rows,
        cols_per_row,
        figsize=(5.8 * cols_per_row, 4.2 * rows),
        squeeze=False,
    )

    flat_axes = axes.ravel()

    for ax, subplot_column in zip(flat_axes, columns):
        _draw_one(ax, df, subplot_column, plot_type, {**controls, "subplot_enabled": False})

    for ax in flat_axes[len(columns):]:
        ax.axis("off")

    fig.suptitle(f"{_safe_title(plot_type)} subplots", fontsize=14)
    return _encode_figure(fig)


def build_figure(
    df: pd.DataFrame,
    column: str,
    plot_type: str,
    local_query: str = "",
    controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    controls = controls or {}
    plot_type = str(plot_type or "").strip()

    if plot_type not in SUPPORTED_PLOT_TYPES:
        raise ValueError(f"Unsupported plot type: {plot_type}")

    plot_df = _apply_local_query(df, local_query)
    _require_column(plot_df, column)

    if _as_bool(controls.get("subplot_enabled"), False):
        figure = _build_subplot_figure(plot_df, column, plot_type, controls)
    else:
        fig, ax = plt.subplots(figsize=(9.6, 5.8))
        _draw_one(ax, plot_df, column, plot_type, controls)
        figure = _encode_figure(fig)

    figure.update(
        {
            "column": column,
            "plot_type": plot_type,
            "rows": int(len(plot_df)),
            "controls": controls,
        }
    )

    return figure


def plotly_code(
    plot_type: str,
    df_var: str,
    column: str,
    local_query: str = "",
    controls: dict[str, Any] | None = None,
) -> str:
    """
    Notebook-export helper.

    The app preview uses matplotlib-rendered PNGs. Exported notebooks call the same
    build_figure function so every UI option, including numeric Top-N and subplots,
    is recreated consistently.
    """
    return (
        "from base64 import b64decode\n"
        "from IPython.display import Image, display\n"
        "from danaleo.core.plots import build_figure\n\n"
        f"_danaleo_plot = build_figure(\n"
        f"    {df_var},\n"
        f"    column={column!r},\n"
        f"    plot_type={plot_type!r},\n"
        f"    local_query={local_query!r},\n"
        f"    controls={controls or {}!r},\n"
        f")\n"
        "_danaleo_png = _danaleo_plot['image'].split(',', 1)[1]\n"
        "display(Image(data=b64decode(_danaleo_png)))"
    )