from __future__ import annotations

from collections import Counter
import re
from io import StringIO
from pathlib import Path
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
        # The source CSV is always loaded into `df`, so the root session must
        # keep that variable regardless of whether it was renamed or created
        # as a derived dataset such as a merge result.
        base = "df" if session.parent_id is None else _base_var_name(session.name)
        counts[base] += 1
        names[session.id] = base if counts[base] == 1 else f"{base}_{counts[base]}"

    return names


class _VariableAllocator:
    def __init__(self) -> None:
        self.used = {"df"}

    def new(self, label: str) -> str:
        stem = re.sub(r"\W+", "_", Path(label).stem).strip("_").lower() or "source"
        candidate = f"df_{stem}"
        index = 2
        while candidate in self.used:
            candidate = f"df_{stem}_{index}"
            index += 1
        self.used.add(candidate)
        return candidate

    def reserve(self, *names: str) -> None:
        self.used.update(names)


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


def _dataset_root(dataset):
    return min(dataset.sessions.values(), key=lambda session: session.created_time)


def _merge_chain_available(store: WorkspaceStore, dataset, visiting: set[str] | None = None) -> bool:
    provenance = dataset.provenance or {}
    if provenance.get("type") != "merge":
        return True

    visiting = set(visiting or ())
    if dataset.id in visiting:
        return False
    visiting.add(dataset.id)

    for side in ("left", "right"):
        source_dataset = store.datasets.get(provenance.get(f"{side}_dataset_id"))
        if not source_dataset or provenance.get(f"{side}_session_id") not in source_dataset.sessions:
            return False
        if not _merge_chain_available(store, source_dataset, visiting):
            return False
    return True


def _load_dataset_code(dataset, df_var: str) -> list[str]:
    code = [f"{df_var} = pd.read_csv({dataset.csv_name!r})"]
    info = dataset.sample_info
    if info and info.get("mode") == "n":
        code.append(
            f"{df_var} = {df_var}.sample(n={info['sample_n']}, "
            f"random_state={info['random_state']}).reset_index(drop=True)"
        )
    elif info and info.get("mode") == "frac":
        code.append(
            f"{df_var} = {df_var}.sample(frac={info['sample_frac']}, "
            f"random_state={info['random_state']}).reset_index(drop=True)"
        )
    return code


def _merge_code(output_var: str, left_var: str, right_var: str, provenance: dict[str, Any]) -> str:
    arguments = [
        left_var,
        right_var,
        f"how={provenance['how']!r}",
    ]
    if provenance["how"] != "cross":
        arguments.extend(
            [
                f"left_on={provenance.get('left_on', [])!r}",
                f"right_on={provenance.get('right_on', [])!r}",
            ]
        )
    arguments.append(f"suffixes={tuple(provenance.get('suffixes') or ['_left', '_right'])!r}")
    if provenance.get("validate"):
        arguments.append(f"validate={provenance['validate']!r}")
    return f"{output_var} = pd.merge({', '.join(arguments)})"


def _dataset_base_code(
    store: WorkspaceStore,
    dataset,
    df_var: str,
    allocator: _VariableAllocator,
) -> list[str]:
    provenance = dataset.provenance or {}
    if provenance.get("type") != "merge" or not _merge_chain_available(store, dataset):
        return _load_dataset_code(dataset, df_var)

    merge_time = _dataset_root(dataset).created_time
    left_dataset = store.datasets[provenance["left_dataset_id"]]
    right_dataset = store.datasets[provenance["right_dataset_id"]]
    left_var = allocator.new(f"{left_dataset.csv_name}_left")
    right_var = allocator.new(f"{right_dataset.csv_name}_right")
    code = _session_snapshot_code(
        store,
        left_dataset,
        provenance["left_session_id"],
        left_var,
        merge_time,
        allocator,
    )
    code.extend(
        _session_snapshot_code(
            store,
            right_dataset,
            provenance["right_session_id"],
            right_var,
            merge_time,
            allocator,
        )
    )
    code.append(_merge_code(df_var, left_var, right_var, provenance))
    return code


def _session_snapshot_code(
    store: WorkspaceStore,
    dataset,
    session_id: str,
    df_var: str,
    cutoff_time: int,
    allocator: _VariableAllocator,
) -> list[str]:
    session = dataset.sessions[session_id]
    if session.parent_id:
        code = _session_snapshot_code(
            store,
            dataset,
            session.parent_id,
            df_var,
            session.created_time,
            allocator,
        )
        code.append(f"{df_var} = {df_var}.copy()")
    else:
        code = _dataset_base_code(store, dataset, df_var, allocator)

    for operation in session.operations:
        if operation.operation_type == "created_session" or operation.time > cutoff_time:
            continue
        code.append(_operation_code(df_var, operation.operation_type, operation.params))
    return code


def _append_code_steps(cells: list[Any], steps: list[str]) -> None:
    for step in steps:
        if step.strip():
            cells.append(nbf.v4.new_code_cell(step))


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

    active_dataset = store.active_dataset
    rebuild_merge = bool(
        active_dataset
        and active_dataset.provenance
        and active_dataset.provenance.get("type") == "merge"
        and _merge_chain_available(store, active_dataset)
    )
    allocator = _VariableAllocator()
    if rebuild_merge:
        load_lines = _dataset_base_code(store, active_dataset, "df", allocator)
    else:
        load_lines = _load_dataset_code(active_dataset, "df")
    _append_code_steps(cells, load_lines)
    cells.append(nbf.v4.new_code_cell("df.head()"))

    sessions = sorted(store.sessions.values(), key=lambda s: s.created_time)
    var_by_session = _unique_var_names(sessions)
    allocator.reserve(*var_by_session.values())

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
                cells.append(nbf.v4.new_markdown_cell(f"## Session: {session.name}"))
                cells.append(nbf.v4.new_code_cell(_session_creation_code(session, var_by_session, store)))
        else:
            cells.append(nbf.v4.new_code_cell(_operation_code(df_var, op.operation_type, op.params)))

    export_plots = sorted(
        (
            plot
            for dataset in store.datasets.values()
            for plot in dataset.saved_plots.values()
            if plot.include_in_export
        ),
        key=lambda plot: plot.created_time,
    )
    plot_var_by_session = dict(var_by_session)

    for plot in export_plots:
        if plot.session_id not in plot_var_by_session:
            plot_dataset, plot_session = store._find_session(plot.session_id)
            plot_var = allocator.new(
                f"{Path(plot_dataset.csv_name).stem}_{plot_session.name}_plot"
            )
            snapshot_code = _session_snapshot_code(
                store,
                plot_dataset,
                plot.session_id,
                plot_var,
                store.time_counter,
                allocator,
            )
            _append_code_steps(cells, snapshot_code)
            plot_var_by_session[plot.session_id] = plot_var
        cells.append(nbf.v4.new_markdown_cell(f"## {plot.title}"))
        if plot.remark.strip():
            cells.append(nbf.v4.new_markdown_cell(plot.remark.strip()))
        cells.append(
            nbf.v4.new_code_cell(
                notebook_plot_code(
                    plot.plot_type,
                    plot_var_by_session[plot.session_id],
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
