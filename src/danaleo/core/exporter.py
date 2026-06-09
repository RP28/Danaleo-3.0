from __future__ import annotations

from collections import Counter
import re
from io import StringIO
from typing import Any

import nbformat as nbf
import pandas as pd

from danaleo.core.operations import parse_scalar
from danaleo.core.plots import notebook_plot_code
from danaleo.core.session_store import WorkspaceStore


def _python_literal(value: Any) -> str:
    if value is pd.NA:
        return "pd.NA"
    if isinstance(value, list):
        return "[" + ", ".join(_python_literal(item) for item in value) + "]"
    return repr(value)


def _base_var_name(session_name: str) -> str:
    cleaned = re.sub(r"\W+", "_", session_name.strip()).strip("_").lower() or "session"
    if cleaned == "base_session":
        return "df"
    return f"df_{cleaned}"


def _unique_var_names(sessions) -> dict[str, str]:
    """Create stable, notebook-safe dataframe variable names for sessions."""
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}

    for session in sorted(sessions, key=lambda s: s.created_time):
        base = _base_var_name(session.name)
        counts[base] += 1
        names[session.id] = base if counts[base] == 1 else f"{base}_{counts[base]}"

    return names


def _operation_code(df_var: str, operation_type: str, params: dict[str, Any]) -> str:
    if operation_type == "filter_rows":
        return f"{df_var} = {df_var}.query({params.get('query', '')!r}).copy()"

    if operation_type == "drop_column":
        return f"{df_var} = {df_var}.drop(columns={[params.get('column', '')]!r}).copy()"

    if operation_type == "replace_values":
        col = params.get("column", "")
        if params.get("multiple", False):
            old_value = [parse_scalar(value) for value in str(params.get("old_value", "")).split(",")]
            new_value = [parse_scalar(value) for value in str(params.get("new_value", "")).split(",")]
        else:
            old_value = parse_scalar(str(params.get("old_value", "")))
            new_value = parse_scalar(str(params.get("new_value", "")))
        return f"{df_var}[{col!r}] = {df_var}[{col!r}].replace({_python_literal(old_value)}, {_python_literal(new_value)})"

    if operation_type == "drop_missing":
        col = params.get("column", "")
        return f"{df_var} = {df_var}.dropna(subset={[col]!r}).copy()"

    if operation_type == "drop_duplicates":
        return f"{df_var} = {df_var}.drop_duplicates().copy()"

    return f"# Operation not exported yet: {operation_type}"


def _session_creation_code(session, var_by_session: dict[str, str], store: WorkspaceStore) -> str:
    df_var = var_by_session[session.id]
    if not session.parent_id:
        return ""

    parent = store.sessions[session.parent_id]
    parent_var = var_by_session[parent.id]
    return f"{df_var} = {parent_var}.copy()"


def _plot_columns_text(plot) -> str:
    if plot.plot_type in {"correlation_heatmap", "missing_values"}:
        return "Scope: **full dataset**"

    controls = plot.controls or {}
    group_col = controls.get("group_by") or controls.get("split_by") or controls.get("hue") or controls.get("color_by")
    subplot_enabled = bool(controls.get("subplot_enabled") or controls.get("subplots"))
    subplot_columns = controls.get("subplot_columns") or []
    if isinstance(subplot_columns, str):
        subplot_columns = [subplot_columns]
    if not isinstance(subplot_columns, list):
        subplot_columns = []

    columns = []
    for value in [plot.column, *subplot_columns]:
        if isinstance(value, str) and value and value not in columns:
            columns.append(value)

    parts = []
    if subplot_enabled and len(columns) > 1:
        parts.append("Subplot columns: " + ", ".join(f"`{column}`" for column in columns))
    else:
        parts.append(f"Column: `{plot.column}`")

    if group_col:
        parts.append(f"Group by: `{group_col}`")

    return " · ".join(parts)


def export_notebook(store: WorkspaceStore) -> bytes:
    if not store.ready:
        raise ValueError("Nothing to export yet")

    nb = nbf.v4.new_notebook()
    cells: list[Any] = []

    cells.append(nbf.v4.new_markdown_cell(f"# Danaleo EDA Export: {store.csv_name or 'dataset'}"))
    cells.append(
        nbf.v4.new_code_cell(
            "import pandas as pd\n"
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "import seaborn as sns"
        )
    )

    cells.append(nbf.v4.new_markdown_cell("## Load data"))
    load_code = f"df = pd.read_csv({(store.csv_name or 'data.csv')!r})"
    if store.sample_info:
        info = store.sample_info
        if info.get("mode") == "n":
            load_code += f"\ndf = df.sample(n={info['sample_n']}, random_state={info['random_state']}).reset_index(drop=True)"
        elif info.get("mode") == "frac":
            load_code += f"\ndf = df.sample(frac={info['sample_frac']}, random_state={info['random_state']}).reset_index(drop=True)"
    load_code += "\ndf.head()"
    cells.append(nbf.v4.new_code_cell(load_code))

    sessions = sorted(store.sessions.values(), key=lambda s: s.created_time)
    var_by_session = _unique_var_names(sessions)

    events: list[tuple[int, int, str, Any, Any]] = []
    for session in sessions:
        events.append((session.created_time, 0, "session", session, None))
        for op in session.operations:
            if op.operation_type == "created_session":
                continue
            events.append((op.time, 1, "operation", session, op))

    for _, _, event_type, session, op in sorted(events, key=lambda item: (item[0], item[1])):
        df_var = var_by_session[session.id]
        if event_type == "session":
            if session.parent_id:
                parent_name = store.sessions[session.parent_id].name
                cells.append(
                    nbf.v4.new_markdown_cell(
                        f"## Session: {session.name}\n\nCreated from **{parent_name}** at this point in the workflow."
                    )
                )
                cells.append(nbf.v4.new_code_cell(_session_creation_code(session, var_by_session, store)))
            else:
                cells.append(nbf.v4.new_markdown_cell("## Session: Base Session"))
        else:
            cells.append(nbf.v4.new_code_cell(_operation_code(df_var, op.operation_type, op.params)))

    export_plots = [p for p in sorted(store.saved_plots.values(), key=lambda p: p.created_time) if p.include_in_export]
    if export_plots:
        cells.append(nbf.v4.new_markdown_cell("# Selected plots"))

    for plot in export_plots:
        cells.append(
            nbf.v4.new_markdown_cell(
                f"## {plot.title}\n\nSession: **{plot.session_name}** · {_plot_columns_text(plot)}"
            )
        )
        if plot.remark.strip():
            cells.append(nbf.v4.new_markdown_cell(plot.remark.strip()))
        cells.append(
            nbf.v4.new_code_cell(
                notebook_plot_code(
                    plot.plot_type,
                    var_by_session[plot.session_id],
                    plot.column,
                    plot.local_query,
                    plot.controls,
                )
            )
        )

    nb.cells = cells
    output = StringIO()
    nbf.write(nb, output)
    return output.getvalue().encode("utf-8")
