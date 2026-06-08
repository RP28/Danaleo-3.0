from __future__ import annotations

import nbformat

from danaleo.core.exporter import export_notebook
from danaleo.core.session_store import WorkspaceStore


def test_export_notebook_recreates_sessions_operations_selected_plots(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv", sample_mode="n", sample_n=6, random_state=3)
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
    notebook = nbformat.reads(exported.decode("utf-8"), as_version=4)
    combined_sources = "\n\n".join(cell.source for cell in notebook.cells)

    assert "Danaleo EDA Export: customers.csv" in combined_sources
    assert "df = pd.read_csv" in combined_sources
    assert "df = df.sample(n=6, random_state=3).reset_index(drop=True)" in combined_sources
    assert "df_sydney_cleanup = df.copy()" in combined_sources
    assert "df_sydney_cleanup = df_sydney_cleanup.query(\"city == 'Sydney'\").copy()" in combined_sources
    assert "Income distribution after filtering." in combined_sources
    assert "Filtered income" in combined_sources
    assert "Skipped segment plot" not in combined_sources


def test_export_notebook_requires_loaded_workspace():
    workspace_store = WorkspaceStore()
    try:
        export_notebook(workspace_store)
    except ValueError as exc:
        assert "Nothing to export" in str(exc)
    else:
        raise AssertionError("Expected export_notebook to fail before upload")


def test_export_replays_branch_creation_at_exact_time_not_after_future_parent_ops(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    base_id = workspace_store.active_session_id
    parent_id = workspace_store.create_session("Parent", base_id)["active_session_id"]

    workspace_store.apply_session_operation(parent_id, "drop_missing", {"column": "income"})
    child_id = workspace_store.create_session("Child After Missing Drop", parent_id)["active_session_id"]
    workspace_store.apply_session_operation(parent_id, "drop_column", {"column": "segment"})
    workspace_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})

    exported = export_notebook(workspace_store)
    notebook = nbformat.reads(exported.decode("utf-8"), as_version=4)
    code_sources = [cell.source for cell in notebook.cells if cell.cell_type == "code"]
    combined_sources = "\n".join(code_sources)

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
