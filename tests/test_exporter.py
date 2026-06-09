from __future__ import annotations

import nbformat
import pytest

from danaleo.core.exporter import export_notebook
from danaleo.core.session_store import WorkspaceStore


def notebook_sources(raw: bytes) -> str:
    notebook = nbformat.reads(raw.decode("utf-8"), as_version=4)
    return "\n\n".join(cell.source for cell in notebook.cells)


def test_export_notebook_recreates_sessions_operations_selected_plots(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="n",
        sample_n=6,
        random_state=3,
    )

    base_id = workspace_store.active_session_id
    child_id = workspace_store.create_session("Sydney Cleanup", base_id)["active_session_id"]

    workspace_store.apply_session_operation(child_id, "filter_rows", {"query": "city == 'Sydney'"})
    workspace_store.apply_session_operation(child_id, "drop_missing", {"column": "income"})

    workspace_store.save_plot(
        child_id,
        "income",
        "histogram",
        local_query="age > 20",
        controls={"bins": 5},
        include_in_export=True,
        remark="Income distribution after filtering.",
        title="Filtered income",
    )
    workspace_store.save_plot(
        child_id,
        "segment",
        "bar_top_n",
        controls={"top_n": 3},
        include_in_export=False,
        title="Skipped segment plot",
    )

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "Danaleo EDA Export: customers.csv" in combined_sources
    assert "df = pd.read_csv" in combined_sources
    assert "df = pd.read_csv('customers.csv')" in combined_sources
    assert "df = df.sample(n=6, random_state=3).reset_index(drop=True)" in combined_sources
    assert "df_sydney_cleanup = df.copy()" in combined_sources
    assert "df_sydney_cleanup = df_sydney_cleanup.query(\"city == 'Sydney'\").copy()" in combined_sources
    assert "df_sydney_cleanup = df_sydney_cleanup.dropna(subset=['income']).copy()" in combined_sources
    assert "Income distribution after filtering." in combined_sources
    assert "Filtered income" in combined_sources
    assert "sns.histplot(" in combined_sources
    assert "def _plot" not in combined_sources
    assert "from danaleo" not in combined_sources
    assert "import danaleo" not in combined_sources
    assert "Skipped segment plot" not in combined_sources


def test_export_notebook_requires_loaded_workspace():
    workspace_store = WorkspaceStore()

    with pytest.raises(ValueError, match="Nothing to export"):
        export_notebook(workspace_store)


def test_export_replays_branch_creation_at_exact_time_not_after_future_parent_ops(
    csv_bytes: bytes,
):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id
    parent_id = workspace_store.create_session("Parent", base_id)["active_session_id"]

    workspace_store.apply_session_operation(parent_id, "drop_missing", {"column": "income"})
    child_id = workspace_store.create_session("Child After Missing Drop", parent_id)[
        "active_session_id"
    ]

    workspace_store.apply_session_operation(parent_id, "drop_column", {"column": "segment"})
    workspace_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    first_parent_op = "df_parent = df_parent.dropna(subset=['income']).copy()"
    child_copy = "df_child_after_missing_drop = df_parent.copy()"
    later_parent_op = "df_parent = df_parent.drop(columns=['segment']).copy()"
    child_op = "df_child_after_missing_drop = df_child_after_missing_drop.query('age > 30').copy()"

    assert first_parent_op in combined_sources
    assert child_copy in combined_sources
    assert later_parent_op in combined_sources
    assert child_op in combined_sources

    assert combined_sources.index(first_parent_op) < combined_sources.index(child_copy)
    assert combined_sources.index(child_copy) < combined_sources.index(later_parent_op)
    assert combined_sources.index(child_copy) < combined_sources.index(child_op)


def test_export_sanitizes_duplicate_session_variable_names(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id

    workspace_store.create_session("My Session!", base_id)
    workspace_store.create_session("My Session?", base_id)

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "df_my_session = df.copy()" in combined_sources
    assert "df_my_session_2 = df.copy()" in combined_sources


def test_export_replays_replace_values_and_drop_missing_operations(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id

    workspace_store.apply_session_operation(
        base_id,
        "replace_values",
        {"column": "segment", "old_value": "A", "new_value": "Alpha"},
    )
    workspace_store.apply_session_operation(
        base_id,
        "drop_missing",
        {"column": "income"},
    )

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "df['segment'] = df['segment'].replace('A', 'Alpha')" in combined_sources
    assert "df = df.dropna(subset=['income']).copy()" in combined_sources


def test_export_replays_typed_and_multiple_replacements():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"value,flag\n1,true\n2,false\n", "typed.csv")
    base_id = workspace_store.active_session_id
    workspace_store.apply_session_operation(
        base_id,
        "replace_values",
        {"column": "value", "old_value": "1, 2", "new_value": "10, 20", "multiple": True},
    )
    workspace_store.apply_session_operation(
        base_id,
        "replace_values",
        {"column": "flag", "old_value": "true", "new_value": "false", "multiple": False},
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "df['value'] = df['value'].replace([1, 2], [10, 20])" in combined_sources
    assert "df['flag'] = df['flag'].replace(True, False)" in combined_sources


def test_export_replacement_with_missing_value_compiles():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"value\n1\n2\n", "missing.csv")
    workspace_store.apply_session_operation(
        workspace_store.active_session_id,
        "replace_values",
        {"column": "value", "old_value": "1", "new_value": "null"},
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    operation_cell = next(cell.source for cell in notebook.cells if ".replace(1, pd.NA)" in cell.source)

    compile(operation_cell, "<replace-missing>", "exec")


def test_export_replays_drop_duplicates_operation():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"x,y\n1,A\n1,A\n2,B\n", "duplicates.csv")
    workspace_store.apply_session_operation(
        workspace_store.active_session_id,
        "drop_duplicates",
        {},
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "df = df.drop_duplicates().copy()" in combined_sources


def test_export_describes_dataset_level_plot_scope(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    workspace_store.save_plot(
        workspace_store.active_session_id,
        "age",
        "correlation_heatmap",
        title="Pearson correlation heatmap",
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "Scope: **full dataset**" in combined_sources
    assert "Column: `age`" not in combined_sources


def test_export_includes_group_and_subplot_plot_context(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id

    workspace_store.save_plot(
        base_id,
        "age",
        "histogram",
        controls={
            "bins": 4,
            "group_by": "segment",
            "subplot_enabled": True,
            "subplot_columns": ["income"],
        },
        title="Age and income",
        remark="Grouped and subplot export check",
        include_in_export=True,
    )

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "Age and income" in combined_sources
    assert "Grouped and subplot export check" in combined_sources
    assert "Group by: `segment`" in combined_sources
    assert "Subplot columns: `age`, `income`" in combined_sources
    assert "sns.histplot(" in combined_sources


def test_exported_notebook_plot_code_uses_only_standalone_libraries(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    base_id = workspace_store.active_session_id
    workspace_store.save_plot(
        base_id,
        "age",
        "scatter",
        controls={"compare_with": "income", "group_by": "segment"},
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    code_sources = "\n\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")

    assert "danaleo.core" not in code_sources
    assert "import danaleo" not in code_sources
    assert "import pandas as pd" in code_sources
    assert "import numpy as np" in code_sources
    assert "import matplotlib.pyplot as plt" in code_sources
    assert "import seaborn as sns" in code_sources
    assert "def _plot" not in code_sources
    assert "sns.scatterplot(" in code_sources
    for cell in notebook.cells:
        if cell.cell_type == "code":
            compile(cell.source, "<exported-notebook-cell>", "exec")


def test_exported_plot_cells_do_not_define_plotting_helpers(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    base_id = workspace_store.active_session_id
    workspace_store.save_plot(base_id, "age", "histogram", controls={"bins": 12})
    workspace_store.save_plot(
        base_id,
        "age",
        "correlation_heatmap",
        controls={"show_values": True},
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    code_sources = [cell.source for cell in notebook.cells if cell.cell_type == "code"]

    assert not any(source.lstrip().startswith("def ") for source in code_sources)
    assert any("sns.histplot(" in source for source in code_sources)
    assert any("sns.heatmap(" in source for source in code_sources)


def test_export_without_saved_plots_has_no_selected_plots_section(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "# Selected plots" not in combined_sources
    assert "sns." not in combined_sources
