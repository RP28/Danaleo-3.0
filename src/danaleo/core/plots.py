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


def _encode_figure(fig: plt.Figure) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _matplotlib_image(
    data: pd.DataFrame,
    column: str,
    plot_type: str,
    title_suffix: str,
    controls: dict[str, Any],
) -> str:
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
        values = _numeric_values(data, column)
        split_by = controls.get("split_by") or None
        if split_by and split_by in data.columns:
            grouped = []
            labels = []
            for label, frame in data.groupby(split_by, dropna=False):
                series = pd.to_numeric(frame[column], errors="coerce").dropna()
                if not series.empty:
                    grouped.append(series.to_numpy())
                    labels.append(str(label)[:28])
            if not grouped:
                raise ValueError("No numeric values after split")
            ax.boxplot(grouped, labels=labels, vert=True, patch_artist=True)
            ax.set_xticklabels(labels, rotation=35, ha="right")
        else:
            ax.boxplot(values.to_numpy(), vert=False, patch_artist=True)
        _style_axis(ax, f"Box plot: {column}{title_suffix}", column, None)
        return _encode_figure(fig)

    if plot_type == "violin":
        values = _numeric_values(data, column)
        split_by = controls.get("split_by") or None
        if split_by and split_by in data.columns:
            grouped = []
            labels = []
            for label, frame in data.groupby(split_by, dropna=False):
                series = pd.to_numeric(frame[column], errors="coerce").dropna()
                if not series.empty:
                    grouped.append(series.to_numpy())
                    labels.append(str(label)[:28])
            if not grouped:
                raise ValueError("No numeric values after split")
            ax.violinplot(grouped, showmeans=True, showmedians=True)
            ax.set_xticks(range(1, len(labels) + 1))
            ax.set_xticklabels(labels, rotation=35, ha="right")
        else:
            ax.violinplot(values.to_numpy(), showmeans=True, showmedians=True)
            ax.set_xticks([1])
            ax.set_xticklabels([column])
        _style_axis(ax, f"Violin plot: {column}{title_suffix}", None, column)
        return _encode_figure(fig)

    if plot_type == "bar_top_n":
        top_n = int(controls.get("top_n", 15))
        counts = data[column].astype("string").fillna("<missing>").value_counts().head(top_n)
        counts = counts.iloc[::-1]
        ax.barh(counts.index.astype(str), counts.values, color=ACCENT)
        _style_axis(ax, f"Top {top_n} labels: {column}{title_suffix}", "count", column)
        return _encode_figure(fig)

    if plot_type == "pie_top_n":
        top_n = int(controls.get("top_n", 10))
        counts = data[column].astype("string").fillna("<missing>").value_counts().head(top_n)
        ax.pie(counts.values, labels=counts.index.astype(str), autopct="%1.1f%%", textprops={"color": TEXT, "fontsize": 8})
        ax.set_title(f"Top {top_n} share: {column}{title_suffix}", color=TEXT, fontsize=13, pad=16, loc="left")
        return _encode_figure(fig)

    plt.close(fig)
    raise ValueError(f"Unsupported plot type: {plot_type}")


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

    if plot_type == "box":
        split_by = controls.get("split_by") or None
        if split_by and split_by in data.columns:
            fig = px.box(data, x=column, y=split_by, points="outliers")
        else:
            fig = px.box(data, x=column, points="outliers")
        fig.update_layout(title=f"Box plot: {column}{title_suffix}")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "violin":
        split_by = controls.get("split_by") or None
        if split_by and split_by in data.columns:
            fig = px.violin(data, x=column, y=split_by, box=True, points="outliers")
        else:
            fig = px.violin(data, y=column, box=True, points="outliers")
        fig.update_layout(title=f"Violin plot: {column}{title_suffix}")
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "bar_top_n":
        top_n = int(controls.get("top_n", 15))
        counts = data[column].astype("string").fillna("<missing>").value_counts().head(top_n)
        plot_df = pd.DataFrame({"label": counts.index.astype(str), "count": counts.values})
        fig = px.bar(plot_df, x="count", y="label", orientation="h")
        fig.update_layout(title=f"Top {top_n} labels: {column}{title_suffix}", yaxis={"categoryorder": "total ascending"})
        return _style(fig, data, column, plot_type, title_suffix, controls)

    if plot_type == "pie_top_n":
        top_n = int(controls.get("top_n", 10))
        counts = data[column].astype("string").fillna("<missing>").value_counts().head(top_n)
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
    return payload


def plotly_code(plot_type: str, df_var: str, column: str, local_query: str, controls: dict[str, Any]) -> str:
    source = df_var
    lines: list[str] = []
    if local_query:
        filtered_name = f"{df_var}_plot"
        lines.append(f"{filtered_name} = {df_var}.query({local_query!r})")
        source = filtered_name

    col = repr(column)
    if plot_type == "histogram":
        bins = int(controls.get("bins", 30))
        lines.append(f"fig = px.histogram({source}, x={col}, nbins={bins})")
    elif plot_type == "kde":
        points = int(controls.get("points", 160))
        bw_adjust = float(controls.get("bw_adjust", 1.0))
        lines.append(f"values = pd.to_numeric({source}[{col}], errors='coerce').dropna().to_numpy()")
        lines.append("std = values.std(ddof=1) if len(values) > 1 else 1.0")
        lines.append(f"bandwidth = max(1.06 * std * (len(values) ** (-1 / 5)) * {bw_adjust!r}, 0.000001)")
        lines.append("padding = ((values.max() - values.min()) * 0.1) or 1.0")
        lines.append(f"xs = np.linspace(values.min() - padding, values.max() + padding, {points})")
        lines.append("scaled = (xs[:, None] - values[None, :]) / bandwidth")
        lines.append("ys = np.exp(-0.5 * scaled**2).sum(axis=1) / (len(values) * bandwidth * np.sqrt(2 * np.pi))")
        lines.append("fig = go.Figure(go.Scatter(x=xs, y=ys, fill='tozeroy'))")
    elif plot_type == "box":
        split_by = controls.get("split_by") or None
        if split_by:
            lines.append(f"fig = px.box({source}, x={col}, y={split_by!r}, points='outliers')")
        else:
            lines.append(f"fig = px.box({source}, x={col}, points='outliers')")
    elif plot_type == "violin":
        split_by = controls.get("split_by") or None
        if split_by:
            lines.append(f"fig = px.violin({source}, x={col}, y={split_by!r}, box=True, points='outliers')")
        else:
            lines.append(f"fig = px.violin({source}, y={col}, box=True, points='outliers')")
    elif plot_type == "bar_top_n":
        top_n = int(controls.get("top_n", 15))
        lines.append(f"counts = {source}[{col}].astype('string').fillna('<missing>').value_counts().head({top_n})")
        lines.append("plot_df = pd.DataFrame({'label': counts.index.astype(str), 'count': counts.values})")
        lines.append("fig = px.bar(plot_df, x='count', y='label', orientation='h')")
    elif plot_type == "pie_top_n":
        top_n = int(controls.get("top_n", 10))
        lines.append(f"counts = {source}[{col}].astype('string').fillna('<missing>').value_counts().head({top_n})")
        lines.append("plot_df = pd.DataFrame({'label': counts.index.astype(str), 'count': counts.values})")
        lines.append("fig = px.pie(plot_df, names='label', values='count')")
    else:
        lines.append(f"# Unsupported plot type: {plot_type}")
    lines.append("fig.show()")
    return "\n".join(lines)
