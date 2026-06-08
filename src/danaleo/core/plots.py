from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

PLOT_BG = "#10131c"
PANEL_BG = "#151a27"
TEXT = "#e8edf8"
MUTED = "#9aa7bd"
GRID = "#273042"
ACCENT = "#7c5cff"
ACCENT_2 = "#26d0ce"
PALETTE = [
    "#7c5cff",
    "#26d0ce",
    "#ff9f43",
    "#ff6384",
    "#5dade2",
    "#60d394",
    "#c084fc",
    "#f6c85f",
]

GROUPED_NUMERIC_TYPES = {"grouped_kde", "grouped_box", "grouped_violin"}


def _apply_local_query(df: pd.DataFrame, query: str | None) -> pd.DataFrame:
    query = (query or "").strip()
    if not query:
        return df

    result = df.query(query).copy()
    if result.empty:
        raise ValueError("Local plot query returned no rows")
    return result


def _as_json(fig: go.Figure) -> dict[str, Any]:
    return json.loads(fig.to_json())


def _kde(values: np.ndarray, points: int = 160, bw_adjust: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    values = values[~np.isnan(values)].astype(float)
    if len(values) < 2:
        raise ValueError("KDE needs at least two numeric values")

    std = float(values.std(ddof=1)) or 1.0
    bandwidth = 1.06 * std * (len(values) ** (-1 / 5)) * max(float(bw_adjust), 0.05)
    if bandwidth <= 0:
        bandwidth = std or 1.0

    x_min, x_max = float(values.min()), float(values.max())
    padding = (x_max - x_min) * 0.1 or 1.0
    xs = np.linspace(x_min - padding, x_max + padding, int(points))
    scaled = (xs[:, None] - values[None, :]) / bandwidth
    ys = np.exp(-0.5 * scaled**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))
    return xs, ys


def _numeric_values(data: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(data[column], errors="coerce").dropna()
    if values.empty:
        raise ValueError(f"Column has no numeric values to plot: {column}")
    return values


def _column_from_controls(controls: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = controls.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _group_column(controls: dict[str, Any]) -> str | None:
    # group_by is the new flexible name. split_by is kept for older saved plots.
    return _column_from_controls(controls, "group_by", "split_by", "hue", "color_by")


def _group_limit(controls: dict[str, Any]) -> int:
    try:
        return max(1, min(int(controls.get("group_limit", 8)), 30))
    except Exception:
        return 8


def _require_columns(data: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"Column not found: {', '.join(missing)}")


def _grouped_numeric_frame(
    data: pd.DataFrame,
    value_col: str,
    group_col: str,
    controls: dict[str, Any],
) -> tuple[pd.DataFrame, list[str]]:
    _require_columns(data, [value_col, group_col])

    frame = data[[value_col, group_col]].copy()
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.dropna(subset=[value_col])
    if frame.empty:
        raise ValueError(f"Column has no numeric values to plot: {value_col}")

    frame["__group_label"] = frame[group_col].astype("string").fillna("Missing")
    frame["__group_label"] = frame["__group_label"].replace("", "Missing")

    limit = _group_limit(controls)
    group_order = frame["__group_label"].value_counts().head(limit).index.astype(str).tolist()
    frame = frame[frame["__group_label"].astype(str).isin(group_order)].copy()

    if frame.empty or not group_order:
        raise ValueError(f"No plottable groups found in: {group_col}")

    return frame, group_order


def _new_axes() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(9.2, 4.8), dpi=140)
    fig.patch.set_facecolor(PLOT_BG)
    ax.set_facecolor(PLOT_BG)
    return fig, ax


def _style_axis(ax: plt.Axes, title: str, xlabel: str | None = None, ylabel: str | None = None) -> None:
    ax.set_title(title, color=TEXT, fontsize=13, pad=16, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel, color=MUTED, labelpad=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, labelpad=10)
    ax.tick_params(colors=MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(True, axis="y", color=GRID, alpha=0.45, linewidth=0.8)


def _style_legend(ax: plt.Axes) -> None:
    legend = ax.legend(frameon=True, fontsize=8)
    if not legend:
        return
    legend.get_frame().set_facecolor(PANEL_BG)
    legend.get_frame().set_edgecolor(GRID)
    for text in legend.get_texts():
        text.set_color(TEXT)


def _encode_figure(fig: plt.Figure) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _matplotlib_grouped_kde(
    data: pd.DataFrame,
    value_col: str,
    group_col: str,
    title_suffix: str,
    controls: dict[str, Any],
) -> str:
    frame, group_order = _grouped_numeric_frame(data, value_col, group_col, controls)
    fig, ax = _new_axes()
    points = int(controls.get("points", 160))
    bw_adjust = float(controls.get("bw_adjust", 1.0))
    fill = bool(controls.get("fill", False))

    plotted = 0
    for idx, label in enumerate(group_order):
        values = frame.loc[frame["__group_label"].astype(str) == label, value_col].dropna().to_numpy()
        if len(values) < 2:
            continue
        xs, ys = _kde(values, points, bw_adjust)
        color = PALETTE[idx % len(PALETTE)]
        ax.plot(xs, ys, color=color, linewidth=2, label=f"{label} ({len(values)})")
        if fill:
            ax.fill_between(xs, ys, color=color, alpha=0.12)
        plotted += 1

    if plotted == 0:
        raise ValueError("Grouped KDE needs at least one group with two numeric values")

    _style_axis(ax, f"KDE by {group_col}: {value_col}{title_suffix}", value_col, "density")
    _style_legend(ax)
    return _encode_figure(fig)


def _matplotlib_grouped_box_or_violin(
    data: pd.DataFrame,
    value_col: str,
    group_col: str,
    plot_type: str,
    title_suffix: str,
    controls: dict[str, Any],
) -> str:
    frame, group_order = _grouped_numeric_frame(data, value_col, group_col, controls)
    fig, ax = _new_axes()

    grouped_values: list[np.ndarray] = []
    labels: list[str] = []
    for label in group_order:
        values = frame.loc[frame["__group_label"].astype(str) == label, value_col].dropna().to_numpy()
        if len(values):
            grouped_values.append(values)
            labels.append(str(label)[:28])

    if not grouped_values:
        raise ValueError("No numeric values after grouping")

    if plot_type in {"grouped_violin", "violin"}:
        parts = ax.violinplot(grouped_values, showmeans=True, showmedians=True)
        for idx, body in enumerate(parts.get("bodies", [])):
            body.set_facecolor(PALETTE[idx % len(PALETTE)])
            body.set_edgecolor(GRID)
            body.set_alpha(0.72)
        title = f"Violin by {group_col}: {value_col}{title_suffix}"
    else:
        box = ax.boxplot(grouped_values, labels=labels, vert=True, patch_artist=True)
        for idx, patch in enumerate(box.get("boxes", [])):
            patch.set_facecolor(PALETTE[idx % len(PALETTE)])
            patch.set_alpha(0.72)
        title = f"Box plot by {group_col}: {value_col}{title_suffix}"

    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    _style_axis(ax, title, group_col, value_col)
    return _encode_figure(fig)


def _matplotlib_image(
    data: pd.DataFrame,
    column: str,
    plot_type: str,
    title_suffix: str,
    controls: dict[str, Any],
) -> str:
    group_col = _group_column(controls)

    if plot_type == "grouped_kde":
        if not group_col:
            raise ValueError("Choose a categorical column in Group by")
        return _matplotlib_grouped_kde(data, column, group_col, title_suffix, controls)

    if plot_type in {"grouped_box", "grouped_violin"}:
        if not group_col:
            raise ValueError("Choose a categorical column in Group by")
        return _matplotlib_grouped_box_or_violin(data, column, group_col, plot_type, title_suffix, controls)

    fig, ax = _new_axes()

    if plot_type == "histogram":
        values = _numeric_values(data, column)
        bins = int(controls.get("bins", 30))
        ax.hist(values, bins=bins, color=ACCENT, alpha=0.82, edgecolor=PLOT_BG)
        _style_axis(ax, f"Histogram: {column}{title_suffix}", column, "count")
        if controls.get("show_kde", False):
            xs, ys = _kde(values.to_numpy(), bw_adjust=float(controls.get("bw_adjust", 1.0)))
            ax2 = ax.twinx()
            ax2.plot(xs, ys, color=ACCENT_2, linewidth=2)
            ax2.set_ylabel("density", color=MUTED)
            ax2.tick_params(colors=MUTED, labelsize=9)
            for spine in ax2.spines.values():
                spine.set_color(GRID)
        return _encode_figure(fig)

    if plot_type == "kde":
        values = _numeric_values(data, column)
        points = int(controls.get("points", 160))
        bw_adjust = float(controls.get("bw_adjust", 1.0))
        xs, ys = _kde(values.to_numpy(), points, bw_adjust)
        ax.plot(xs, ys, color=ACCENT, linewidth=2.2)
        if controls.get("fill", True):
            ax.fill_between(xs, ys, color=ACCENT, alpha=0.28)
        _style_axis(ax, f"KDE: {column}{title_suffix}", column, "density")
        return _encode_figure(fig)

    if plot_type == "box":
        if group_col and group_col in data.columns:
            return _matplotlib_grouped_box_or_violin(data, column, group_col, plot_type, title_suffix, controls)
        values = _numeric_values(data, column)
        ax.boxplot(values.to_numpy(), vert=False, patch_artist=True)
        _style_axis(ax, f"Box plot: {column}{title_suffix}", column, None)
        return _encode_figure(fig)

    if plot_type == "violin":
        if group_col and group_col in data.columns:
            return _matplotlib_grouped_box_or_violin(data, column, group_col, plot_type, title_suffix, controls)
        values = _numeric_values(data, column)
        ax.violinplot(values.to_numpy(), showmeans=True, showmedians=True)
        ax.set_xticks([1])
        ax.set_xticklabels([column])
        _style_axis(ax, f"Violin plot: {column}{title_suffix}", None, column)
        return _encode_figure(fig)

    if plot_type == "bar_top_n":
        top_n = int(controls.get("top_n", 15))
        counts = data[column].astype("string").fillna("").value_counts().head(top_n)
        counts = counts.iloc[::-1]
        ax.barh(counts.index.astype(str), counts.values, color=ACCENT)
        _style_axis(ax, f"Top {top_n} labels: {column}{title_suffix}", "count", column)
        return _encode_figure(fig)

    if plot_type == "pie_top_n":
        top_n = int(controls.get("top_n", 10))
        counts = data[column].astype("string").fillna("").value_counts().head(top_n)
        ax.pie(counts.values, labels=counts.index.astype(str), autopct="%1.1f%%", textprops={"color": TEXT, "fontsize": 8})
        ax.set_title(f"Top {top_n} share: {column}{title_suffix}", color=TEXT, fontsize=13, pad=16, loc="left")
        return _encode_figure(fig)

    plt.close(fig)
    raise ValueError(f"Unsupported plot type: {plot_type}")


def _plotly_grouped_kde(
    data: pd.DataFrame,
    value_col: str,
    group_col: str,
    controls: dict[str, Any],
    title_suffix: str,
) -> go.Figure:
    frame, group_order = _grouped_numeric_frame(data, value_col, group_col, controls)
    fig = go.Figure()
    points = int(controls.get("points", 160))
    bw_adjust = float(controls.get("bw_adjust", 1.0))
    fill = "tozeroy" if controls.get("fill", False) else None

    plotted = 0
    for label in group_order:
        values = frame.loc[frame["__group_label"].astype(str) == label, value_col].dropna().to_numpy()
        if len(values) < 2:
            continue
        xs, ys = _kde(values, points, bw_adjust)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill=fill, name=f"{label} ({len(values)})"))
        plotted += 1

    if plotted == 0:
        raise ValueError("Grouped KDE needs at least one group with two numeric values")

    fig.update_layout(
        title=f"KDE by {group_col}: {value_col}{title_suffix}",
        xaxis_title=value_col,
        yaxis_title="density",
    )
    return fig


def _plotly_grouped_box_or_violin(
    data: pd.DataFrame,
    value_col: str,
    group_col: str,
    plot_type: str,
    controls: dict[str, Any],
    title_suffix: str,
) -> go.Figure:
    frame, group_order = _grouped_numeric_frame(data, value_col, group_col, controls)
    category_orders = {"__group_label": group_order}
    points = "outliers" if controls.get("show_outliers", True) else False

    if plot_type in {"grouped_violin", "violin"}:
        fig = px.violin(
            frame,
            x="__group_label",
            y=value_col,
            color="__group_label",
            category_orders=category_orders,
            box=True,
            points=points,
        )
        fig.update_layout(title=f"Violin by {group_col}: {value_col}{title_suffix}")
    else:
        fig = px.box(
            frame,
            x="__group_label",
            y=value_col,
            color="__group_label",
            category_orders=category_orders,
            points=points,
        )
        fig.update_layout(title=f"Box plot by {group_col}: {value_col}{title_suffix}")

    fig.update_layout(xaxis_title=group_col, yaxis_title=value_col, showlegend=False)
    return fig


def build_figure(
    df: pd.DataFrame,
    column: str,
    plot_type: str,
    local_query: str | None = None,
    controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build both a notebook-friendly Plotly figure and a browser-safe PNG preview.

    The UI uses the PNG data URL. This avoids the blank-page crash caused by
    mounting react-plotly/plotly.js inside a React 19 build, while preserving
    Plotly metadata for future export and inspection.
    """
    if column not in df.columns:
        raise ValueError(f"Column not found: {column}")

    controls = controls or {}
    data = _apply_local_query(df, local_query)
    title_suffix = f" — local filter: {local_query}" if local_query else ""
    group_col = _group_column(controls)

    if plot_type == "histogram":
        bins = int(controls.get("bins", 30))
        fig = px.histogram(data, x=column, nbins=bins, marginal=controls.get("marginal") or None)
        if controls.get("show_kde", False):
            xs, ys = _kde(pd.to_numeric(data[column], errors="coerce").dropna().to_numpy())
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="KDE", yaxis="y2"))
            fig.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
        fig.update_layout(title=f"Histogram: {column}{title_suffix}")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "kde":
        points = int(controls.get("points", 160))
        bw_adjust = float(controls.get("bw_adjust", 1.0))
        xs, ys = _kde(pd.to_numeric(data[column], errors="coerce").dropna().to_numpy(), points, bw_adjust)
        fig = go.Figure(go.Scatter(x=xs, y=ys, fill="tozeroy" if controls.get("fill", True) else None))
        fig.update_layout(title=f"KDE: {column}{title_suffix}", xaxis_title=column, yaxis_title="density")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "grouped_kde":
        if not group_col:
            raise ValueError("Choose a categorical column in Group by")
        fig = _plotly_grouped_kde(data, column, group_col, controls, title_suffix)
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type in {"box", "grouped_box"}:
        if plot_type == "grouped_box" and not group_col:
            raise ValueError("Choose a categorical column in Group by")
        if group_col and group_col in data.columns:
            fig = _plotly_grouped_box_or_violin(data, column, group_col, plot_type, controls, title_suffix)
        else:
            fig = px.box(data, x=column, points="outliers")
            fig.update_layout(title=f"Box plot: {column}{title_suffix}")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type in {"violin", "grouped_violin"}:
        if plot_type == "grouped_violin" and not group_col:
            raise ValueError("Choose a categorical column in Group by")
        if group_col and group_col in data.columns:
            fig = _plotly_grouped_box_or_violin(data, column, group_col, plot_type, controls, title_suffix)
        else:
            fig = px.violin(data, y=column, box=True, points="outliers")
            fig.update_layout(title=f"Violin plot: {column}{title_suffix}")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "bar_top_n":
        top_n = int(controls.get("top_n", 15))
        counts = data[column].astype("string").fillna("").value_counts().head(top_n)
        plot_df = pd.DataFrame({"label": counts.index.astype(str), "count": counts.values})
        fig = px.bar(plot_df, x="count", y="label", orientation="h")
        fig.update_layout(title=f"Top {top_n} labels: {column}{title_suffix}", yaxis={"categoryorder": "total ascending"})
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "pie_top_n":
        top_n = int(controls.get("top_n", 10))
        counts = data[column].astype("string").fillna("").value_counts().head(top_n)
        plot_df = pd.DataFrame({"label": counts.index.astype(str), "count": counts.values})
        fig = px.pie(plot_df, names="label", values="count")
        fig.update_layout(title=f"Top {top_n} share: {column}{title_suffix}")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    raise ValueError(f"Unsupported plot type: {plot_type}")


def _style(
    fig: go.Figure,
    data: pd.DataFrame,
    column: str,
    plot_type: str,
    title_suffix: str,
    controls: dict[str, Any],
) -> dict[str, Any]:
    group_col = _group_column(controls)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        font={"color": TEXT},
        margin={"l": 54, "r": 28, "t": 58, "b": 48},
        height=480,
    )
    payload = _as_json(fig)
    payload["image"] = _matplotlib_image(data, column, plot_type, title_suffix, controls)
    payload["renderer"] = "png"
    payload["plot_meta"] = {
        "plot_type": plot_type,
        "primary_column": column,
        "group_by": group_col,
        "columns": [column, group_col] if group_col else [column],
    }
    return payload


def _plotly_grouped_frame_code(source: str, value_col: str, group_col: str, controls: dict[str, Any]) -> list[str]:
    limit = _group_limit(controls)
    return [
        f"plot_df = {source}[[{value_col!r}, {group_col!r}]].copy()",
        f"plot_df[{value_col!r}] = pd.to_numeric(plot_df[{value_col!r}], errors='coerce')",
        f"plot_df = plot_df.dropna(subset=[{value_col!r}])",
        f"plot_df['__group_label'] = plot_df[{group_col!r}].astype('string').fillna('Missing').replace('', 'Missing')",
        f"group_order = plot_df['__group_label'].value_counts().head({limit}).index.astype(str).tolist()",
        "plot_df = plot_df[plot_df['__group_label'].astype(str).isin(group_order)].copy()",
    ]


def plotly_code(plot_type: str, df_var: str, column: str, local_query: str, controls: dict[str, Any]) -> str:
    source = df_var
    lines: list[str] = []

    if local_query:
        filtered_name = f"{df_var}_plot"
        lines.append(f"{filtered_name} = {df_var}.query({local_query!r})")
        source = filtered_name

    col = repr(column)
    group_col = _group_column(controls)

    if plot_type == "histogram":
        bins = int(controls.get("bins", 30))
        lines.append(f"fig = px.histogram({source}, x={col}, nbins={bins})")
        if controls.get("show_kde", False):
            lines.append(f"values = pd.to_numeric({source}[{col}], errors='coerce').dropna().to_numpy()")
            lines.append("std = values.std(ddof=1) if len(values) > 1 else 1.0")
            lines.append("bandwidth = max(1.06 * std * (len(values) ** (-1 / 5)), 0.000001)")
            lines.append("padding = ((values.max() - values.min()) * 0.1) or 1.0")
            lines.append("xs = np.linspace(values.min() - padding, values.max() + padding, 160)")
            lines.append("scaled = (xs[:, None] - values[None, :]) / bandwidth")
            lines.append("ys = np.exp(-0.5 * scaled**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))")
            lines.append("fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', name='KDE', yaxis='y2'))")
            lines.append("fig.update_layout(yaxis2={'overlaying': 'y', 'side': 'right', 'showgrid': False})")

    elif plot_type == "kde":
        points = int(controls.get("points", 160))
        bw_adjust = float(controls.get("bw_adjust", 1.0))
        fill = "'tozeroy'" if controls.get("fill", True) else "None"
        lines.append(f"values = pd.to_numeric({source}[{col}], errors='coerce').dropna().to_numpy()")
        lines.append("std = values.std(ddof=1) if len(values) > 1 else 1.0")
        lines.append(f"bandwidth = max(1.06 * std * (len(values) ** (-1 / 5)) * {bw_adjust!r}, 0.000001)")
        lines.append("padding = ((values.max() - values.min()) * 0.1) or 1.0")
        lines.append(f"xs = np.linspace(values.min() - padding, values.max() + padding, {points})")
        lines.append("scaled = (xs[:, None] - values[None, :]) / bandwidth")
        lines.append("ys = np.exp(-0.5 * scaled**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))")
        lines.append(f"fig = go.Figure(go.Scatter(x=xs, y=ys, fill={fill}))")

    elif plot_type == "grouped_kde":
        if not group_col:
            lines.append("# Grouped KDE was requested, but no group column was saved.")
            lines.append("fig = go.Figure()")
        else:
            points = int(controls.get("points", 160))
            bw_adjust = float(controls.get("bw_adjust", 1.0))
            fill = "'tozeroy'" if controls.get("fill", False) else "None"
            lines.extend(_plotly_grouped_frame_code(source, column, group_col, controls))
            lines.append("fig = go.Figure()")
            lines.append("for group_name in group_order:")
            lines.append(f"    values = plot_df.loc[plot_df['__group_label'].astype(str) == group_name, {col}].dropna().to_numpy()")
            lines.append("    if len(values) < 2:")
            lines.append("        continue")
            lines.append("    std = values.std(ddof=1) if len(values) > 1 else 1.0")
            lines.append(f"    bandwidth = max(1.06 * std * (len(values) ** (-1 / 5)) * {bw_adjust!r}, 0.000001)")
            lines.append("    padding = ((values.max() - values.min()) * 0.1) or 1.0")
            lines.append(f"    xs = np.linspace(values.min() - padding, values.max() + padding, {points})")
            lines.append("    scaled = (xs[:, None] - values[None, :]) / bandwidth")
            lines.append("    ys = np.exp(-0.5 * scaled**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))")
            lines.append(f"    fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', fill={fill}, name=f'{{group_name}} ({{len(values)}})'))")
            lines.append(f"fig.update_layout(title='KDE by {group_col}: {column}', xaxis_title={col}, yaxis_title='density')")

    elif plot_type in {"box", "grouped_box"}:
        if group_col:
            lines.extend(_plotly_grouped_frame_code(source, column, group_col, controls))
            lines.append("fig = px.box(plot_df, x='__group_label', y=" + col + ", color='__group_label', category_orders={'__group_label': group_order}, points='outliers')")
            lines.append(f"fig.update_layout(xaxis_title={group_col!r}, yaxis_title={col}, showlegend=False)")
        else:
            lines.append(f"fig = px.box({source}, x={col}, points='outliers')")

    elif plot_type in {"violin", "grouped_violin"}:
        if group_col:
            lines.extend(_plotly_grouped_frame_code(source, column, group_col, controls))
            lines.append("fig = px.violin(plot_df, x='__group_label', y=" + col + ", color='__group_label', category_orders={'__group_label': group_order}, box=True, points='outliers')")
            lines.append(f"fig.update_layout(xaxis_title={group_col!r}, yaxis_title={col}, showlegend=False)")
        else:
            lines.append(f"fig = px.violin({source}, y={col}, box=True, points='outliers')")

    elif plot_type == "bar_top_n":
        top_n = int(controls.get("top_n", 15))
        lines.append(f"counts = {source}[{col}].astype('string').fillna('').value_counts().head({top_n})")
        lines.append("plot_df = pd.DataFrame({'label': counts.index.astype(str), 'count': counts.values})")
        lines.append("fig = px.bar(plot_df, x='count', y='label', orientation='h')")

    elif plot_type == "pie_top_n":
        top_n = int(controls.get("top_n", 10))
        lines.append(f"counts = {source}[{col}].astype('string').fillna('').value_counts().head({top_n})")
        lines.append("plot_df = pd.DataFrame({'label': counts.index.astype(str), 'count': counts.values})")
        lines.append("fig = px.pie(plot_df, names='label', values='count')")

    else:
        lines.append(f"# Unsupported plot type: {plot_type}")
        lines.append("fig = go.Figure()")

    lines.append("fig.show()")
    return "\n".join(lines)