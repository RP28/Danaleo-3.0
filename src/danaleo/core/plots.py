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
    "scatter",
    "hexbin",
    "line",
    "correlation_heatmap",
    "missing_values",
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


def _apply_axis_style(ax: plt.Axes, controls: dict[str, Any]) -> None:
    if _as_bool(controls.get("show_grid"), True):
        ax.grid(True, alpha=0.18, linestyle="--")
        ax.set_axisbelow(True)

    if _as_bool(controls.get("log_x"), False):
        ax.set_xscale("log")
    if _as_bool(controls.get("log_y"), False):
        ax.set_yscale("log")

    title = str(controls.get("chart_title") or "").strip()
    if title:
        ax.set_title(title)


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

    sort_order = str(controls.get("sort_order") or "descending")
    pairs = list(zip(labels, values))
    if sort_order == "ascending":
        pairs.sort(key=lambda item: item[1])
    elif sort_order == "descending":
        pairs.sort(key=lambda item: item[1], reverse=True)
    labels, values = map(list, zip(*pairs))

    if str(controls.get("orientation") or "vertical") == "horizontal":
        ax.barh(labels, values)
        ax.set_xlabel(y_label)
        ax.set_ylabel(column)
    else:
        ax.bar(labels, values)
        ax.set_xlabel(column)
        ax.set_ylabel(y_label)
        _format_axis_labels(ax)
    ax.set_title(f"Top {len(values)} values — {column}")


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


def _comparison_column(df: pd.DataFrame, controls: dict[str, Any]) -> str:
    column = str(controls.get("compare_with") or "").strip()
    if not column:
        raise ValueError("Choose a numeric column in Compare with")
    _require_column(df, column)
    return column


def _paired_numeric(df: pd.DataFrame, x_column: str, y_column: str) -> pd.DataFrame:
    paired = pd.DataFrame(
        {
            x_column: pd.to_numeric(df[x_column], errors="coerce"),
            y_column: pd.to_numeric(df[y_column], errors="coerce"),
        }
    ).dropna()
    if paired.empty:
        raise ValueError("The selected columns have no paired numeric values")
    return paired


def _draw_scatter(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    compare_with = _comparison_column(df, controls)
    marker_size = _as_float(controls.get("marker_size"), 28, minimum=4, maximum=300)
    alpha = _as_float(controls.get("alpha"), 0.72, minimum=0.05, maximum=1)
    group_column = str(controls.get("group_by") or "").strip()

    if group_column:
        _require_column(df, group_column)
        groups = _limited_groups(df, group_column, _as_int(controls.get("group_limit"), 8, 1, 30))
        group_values = _category_series(df, group_column)
        drawn = 0
        for group in groups:
            subset = df[group_values == group]
            try:
                paired = _paired_numeric(subset, column, compare_with)
            except ValueError:
                continue
            ax.scatter(paired[column], paired[compare_with], s=marker_size, alpha=alpha, label=group)
            drawn += 1
        if not drawn:
            raise ValueError("The selected groups have no paired numeric values")
        ax.legend(fontsize=8)
    else:
        paired = _paired_numeric(df, column, compare_with)
        ax.scatter(paired[column], paired[compare_with], s=marker_size, alpha=alpha)

    ax.set_title(f"{compare_with} vs {column}")
    ax.set_xlabel(column)
    ax.set_ylabel(compare_with)


def _draw_hexbin(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    compare_with = _comparison_column(df, controls)
    paired = _paired_numeric(df, column, compare_with)
    result = ax.hexbin(
        paired[column],
        paired[compare_with],
        gridsize=_as_int(controls.get("gridsize"), 30, minimum=8, maximum=100),
        mincnt=1,
        cmap="viridis",
    )
    ax.figure.colorbar(result, ax=ax, label="Count")
    ax.set_title(f"Density — {compare_with} vs {column}")
    ax.set_xlabel(column)
    ax.set_ylabel(compare_with)


def _draw_line(ax: plt.Axes, df: pd.DataFrame, column: str, controls: dict[str, Any]) -> None:
    compare_with = _comparison_column(df, controls)
    paired = _paired_numeric(df, column, compare_with)
    if _as_bool(controls.get("sort_x"), True):
        paired = paired.sort_values(column)
    ax.plot(
        paired[column],
        paired[compare_with],
        marker="o" if _as_bool(controls.get("show_markers"), True) else None,
        markersize=max(2, _as_float(controls.get("marker_size"), 20, 4, 300) / 5),
        alpha=_as_float(controls.get("alpha"), 0.8, 0.05, 1),
    )
    ax.set_title(f"{compare_with} over {column}")
    ax.set_xlabel(column)
    ax.set_ylabel(compare_with)


def _draw_correlation_heatmap(ax: plt.Axes, df: pd.DataFrame, _column: str, controls: dict[str, Any]) -> None:
    numeric = df.select_dtypes(include=[np.number])
    limit = _as_int(controls.get("correlation_limit"), 16, minimum=2, maximum=40)
    numeric = numeric.iloc[:, :limit]
    if numeric.shape[1] < 2:
        raise ValueError("Correlation heatmap needs at least two numeric columns")

    corr = numeric.corr()
    image = ax.imshow(corr.to_numpy(), vmin=-1, vmax=1, cmap="coolwarm")
    ax.figure.colorbar(image, ax=ax, label="Correlation")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns)
    ax.set_yticklabels(corr.columns)
    _format_axis_labels(ax, rotation=45)
    ax.set_title("Numeric correlation heatmap")

    if _as_bool(controls.get("show_values"), True) and len(corr.columns) <= 18:
        for row in range(len(corr.columns)):
            for col in range(len(corr.columns)):
                ax.text(col, row, f"{corr.iloc[row, col]:.2f}", ha="center", va="center", fontsize=7)


def _draw_missing_values(ax: plt.Axes, df: pd.DataFrame, _column: str, controls: dict[str, Any]) -> None:
    missing = (df.isna().mean() * 100).sort_values(ascending=True)
    if not _as_bool(controls.get("include_complete"), False):
        missing = missing[missing > 0]
    if missing.empty:
        missing = pd.Series([0.0], index=["No missing values"])
    limit = _as_int(controls.get("top_n"), 20, minimum=1, maximum=100)
    missing = missing.tail(limit)
    ax.barh([str(value) for value in missing.index], missing.to_numpy())
    ax.set_title("Missing values by column")
    ax.set_xlabel("Missing (%)")
    ax.set_ylabel("Column")
    ax.set_xlim(0, 100)


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
    elif plot_type == "scatter":
        _draw_scatter(ax, df, column, controls)
    elif plot_type == "hexbin":
        _draw_hexbin(ax, df, column, controls)
    elif plot_type == "line":
        _draw_line(ax, df, column, controls)
    elif plot_type == "correlation_heatmap":
        _draw_correlation_heatmap(ax, df, column, controls)
    elif plot_type == "missing_values":
        _draw_missing_values(ax, df, column, controls)
    else:
        raise ValueError(f"Unsupported plot type: {plot_type}")
    _apply_axis_style(ax, controls)


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


def _notebook_plot_lines(
    plot_type: str,
    column_expr: str,
    controls: dict[str, Any],
    indent: str = "",
) -> list[str]:
    ax = "_ax"
    df = "_plot_df"
    group_by = str(controls.get("group_by") or "")
    compare_with = str(controls.get("compare_with") or "")
    lines: list[str] = []

    if plot_type == "histogram":
        lines.append(
            f"sns.histplot(data={df}, x={column_expr}, bins={_as_int(controls.get('bins'), 30, 2, 200)}, "
            f"kde={_as_bool(controls.get('show_kde'), False)!r}, ax={ax})"
        )
    elif plot_type == "kde":
        lines.append(
            f"sns.kdeplot(data={df}, x={column_expr}, bw_adjust={_as_float(controls.get('bw_adjust'), 1.0, 0.05, 10)!r}, "
            f"fill={_as_bool(controls.get('fill'), True)!r}, ax={ax})"
        )
    elif plot_type == "box":
        lines.append(
            f"sns.boxplot(data={df}, y={column_expr}, showfliers={_as_bool(controls.get('show_outliers'), True)!r}, ax={ax})"
        )
    elif plot_type == "violin":
        lines.append(f"sns.violinplot(data={df}, y={column_expr}, inner='quartile', ax={ax})")
    elif plot_type in {"bar_top_n", "pie_top_n"}:
        lines.extend(
            [
                f"_counts = ({df}[{column_expr}].astype('string').fillna('<missing>').replace('', '<empty>')",
                f"           .value_counts().head({_as_int(controls.get('top_n'), 15, 1, 100)}).rename_axis('value').reset_index(name='count'))",
            ]
        )
        sort_order = str(controls.get("sort_order") or "descending")
        if sort_order in {"ascending", "descending"}:
            lines.append(f"_counts = _counts.sort_values('count', ascending={sort_order == 'ascending'!r})")
        if plot_type == "pie_top_n":
            lines.append(f"{ax}.pie(_counts['count'], labels=_counts['value'], autopct='%1.1f%%', startangle=90)")
            lines.append(f"{ax}.axis('equal')")
        elif str(controls.get("orientation") or "vertical") == "horizontal":
            lines.append(f"sns.barplot(data=_counts, x='count', y='value', ax={ax})")
        else:
            lines.append(f"sns.barplot(data=_counts, x='value', y='count', ax={ax})")
            lines.append(f"{ax}.tick_params(axis='x', labelrotation=35)")
    elif plot_type == "grouped_kde":
        lines.append(
            f"sns.kdeplot(data={df}, x={column_expr}, hue={group_by!r}, "
            f"bw_adjust={_as_float(controls.get('bw_adjust'), 1.0, 0.05, 10)!r}, "
            f"fill={_as_bool(controls.get('fill'), True)!r}, common_norm=False, ax={ax})"
        )
    elif plot_type in {"grouped_box", "grouped_violin"}:
        lines.append(
            f"_groups = {df}[{group_by!r}].astype('string').fillna('<missing>').value_counts()"
            f".head({_as_int(controls.get('group_limit'), 8, 1, 30)}).index"
        )
        lines.append(f"_grouped = {df}[{df}[{group_by!r}].astype('string').fillna('<missing>').isin(_groups)]")
        if plot_type == "grouped_box":
            lines.append(
                f"sns.boxplot(data=_grouped, x={group_by!r}, y={column_expr}, order=_groups, "
                f"showfliers={_as_bool(controls.get('show_outliers'), True)!r}, ax={ax})"
            )
        else:
            lines.append(f"sns.violinplot(data=_grouped, x={group_by!r}, y={column_expr}, order=_groups, inner='quartile', ax={ax})")
        lines.append(f"{ax}.tick_params(axis='x', labelrotation=35)")
    elif plot_type == "scatter":
        hue = f", hue={group_by!r}" if group_by else ""
        lines.append(
            f"sns.scatterplot(data={df}, x={column_expr}, y={compare_with!r}{hue}, "
            f"s={_as_float(controls.get('marker_size'), 28, 4, 300)!r}, "
            f"alpha={_as_float(controls.get('alpha'), 0.72, 0.05, 1)!r}, ax={ax})"
        )
    elif plot_type == "hexbin":
        lines.append(f"_paired = {df}[[{column_expr}, {compare_with!r}]].apply(pd.to_numeric, errors='coerce').dropna()")
        lines.append(
            f"_hexbin = {ax}.hexbin(_paired[{column_expr}], _paired[{compare_with!r}], "
            f"gridsize={_as_int(controls.get('gridsize'), 30, 8, 100)}, mincnt=1, cmap='viridis')"
        )
        lines.append(f"_fig.colorbar(_hexbin, ax={ax}, label='Count')")
    elif plot_type == "line":
        lines.append(f"_line_data = {df}[[{column_expr}, {compare_with!r}]].apply(pd.to_numeric, errors='coerce').dropna()")
        if _as_bool(controls.get("sort_x"), True):
            lines.append(f"_line_data = _line_data.sort_values({column_expr})")
        marker = "'o'" if _as_bool(controls.get("show_markers"), True) else "None"
        lines.append(
            f"sns.lineplot(data=_line_data, x={column_expr}, y={compare_with!r}, marker={marker}, "
            f"alpha={_as_float(controls.get('alpha'), 0.8, 0.05, 1)!r}, ax={ax})"
        )
    elif plot_type == "correlation_heatmap":
        lines.append(
            f"_corr = {df}.select_dtypes(include='number').iloc[:, :{_as_int(controls.get('correlation_limit'), 16, 2, 40)}].corr()"
        )
        lines.append(
            f"sns.heatmap(_corr, vmin=-1, vmax=1, cmap='coolwarm', "
            f"annot={_as_bool(controls.get('show_values'), True)!r}, fmt='.2f', ax={ax})"
        )
    elif plot_type == "missing_values":
        lines.append(f"_missing = ({df}.isna().mean() * 100).sort_values()")
        if not _as_bool(controls.get("include_complete"), False):
            lines.append("_missing = _missing[_missing > 0]")
        lines.append("_missing = pd.Series({'No missing values': 0.0}) if _missing.empty else _missing")
        lines.append(f"_missing = _missing.tail({_as_int(controls.get('top_n'), 20, 1, 100)})")
        lines.append(f"sns.barplot(x=_missing.values, y=_missing.index, orient='h', ax={ax})")
        lines.append(f"{ax}.set_xlim(0, 100)")
        lines.append(f"{ax}.set_xlabel('Missing (%)')")
    else:
        raise ValueError(f"Unsupported plot type: {plot_type}")

    if _as_bool(controls.get("show_grid"), True) and plot_type != "correlation_heatmap":
        lines.append(f"{ax}.grid(True, alpha=0.18, linestyle='--')")
    if _as_bool(controls.get("log_x"), False):
        lines.append(f"{ax}.set_xscale('log')")
    if _as_bool(controls.get("log_y"), False):
        lines.append(f"{ax}.set_yscale('log')")
    if str(controls.get("chart_title") or "").strip():
        lines.append(f"{ax}.set_title({str(controls['chart_title']).strip()!r})")

    return [indent + line for line in lines]


def notebook_plot_code(
    plot_type: str,
    df_var: str,
    column: str,
    local_query: str = "",
    controls: dict[str, Any] | None = None,
) -> str:
    """Return concise, package-independent seaborn/matplotlib code for one plot."""
    controls = controls or {}
    query = str(local_query or "").strip()
    lines = [f"_plot_df = {df_var}.query({query!r}).copy()" if query else f"_plot_df = {df_var}.copy()"]

    if _as_bool(controls.get("subplot_enabled"), False):
        columns = _subplot_columns(column, controls)
        cols_per_row = _as_int(controls.get("subplot_cols"), 2, 1, 4)
        rows = math.ceil(len(columns) / cols_per_row)
        lines.extend(
            [
                f"_columns = {columns!r}",
                f"_fig, _axes = plt.subplots({rows}, {cols_per_row}, figsize=({5.8 * cols_per_row!r}, {4.2 * rows!r}), squeeze=False)",
                "for _ax, _column in zip(_axes.ravel(), _columns):",
            ]
        )
        lines.extend(_notebook_plot_lines(plot_type, "_column", controls, indent="    "))
        lines.extend(
            [
                "for _ax in _axes.ravel()[len(_columns):]:",
                "    _ax.axis('off')",
                "_fig.tight_layout()",
                "plt.show()",
            ]
        )
    else:
        lines.append("_fig, _ax = plt.subplots(figsize=(9.6, 5.8))")
        lines.extend(_notebook_plot_lines(plot_type, repr(column), controls))
        lines.extend(["_fig.tight_layout()", "plt.show()"])

    return "\n".join(lines)


def plotly_code(
    plot_type: str,
    df_var: str,
    column: str,
    local_query: str = "",
    controls: dict[str, Any] | None = None,
) -> str:
    """Backward-compatible alias for the package-independent notebook code generator."""
    return notebook_plot_code(plot_type, df_var, column, local_query, controls)
