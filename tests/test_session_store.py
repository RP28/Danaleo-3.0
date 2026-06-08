from __future__ import annotations

import pytest

from danaleo.core.session_store import WorkspaceStore


def test_load_csv_creates_base_workspace(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_csv(csv_bytes, "customers.csv")

    assert workspace["ready"] is True
    assert workspace["csv_name"] == "customers.csv"
    assert workspace["active_session"]["name"] == "Base Session"
    assert workspace["active_session"]["overview"]["rows"] == 8
    assert {card["name"] for card in workspace["active_session"]["columns"]} == {"age", "income", "city", "segment", "flag"}


def test_sampling_options_record_how_data_was_reduced(csv_bytes: bytes):
    by_count = WorkspaceStore().load_csv(csv_bytes, "customers.csv", sample_mode="n", sample_n=3, random_state=7)
    assert by_count["active_session"]["overview"]["rows"] == 3
    assert by_count["sample_info"] == {"mode": "n", "sample_n": 3, "random_state": 7, "original_rows": 8}

    by_fraction = WorkspaceStore().load_csv(csv_bytes, "customers.csv", sample_mode="frac", sample_frac=0.5, random_state=7)
    assert by_fraction["active_session"]["overview"]["rows"] == 4
    assert by_fraction["sample_info"] == {"mode": "frac", "sample_frac": 0.5, "random_state": 7, "original_rows": 8}


def test_sessions_are_independent_copies(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    child_workspace = loaded_store.create_session("Analysis 1", base_id)
    child_id = child_workspace["active_session_id"]

    loaded_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})

    assert len(loaded_store.sessions[child_id].data) == 5
    assert len(loaded_store.sessions[base_id].data) == 8
    assert loaded_store.sessions[child_id].operations[-1].label == "Filter: age > 30"


def test_rename_session_updates_saved_plot_metadata(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    loaded_store.save_plot(base_id, "age", "histogram", controls={"bins": 4}, title="Age histogram")
    plot_id = next(iter(loaded_store.saved_plots))

    workspace = loaded_store.rename_session(base_id, "Cleaned baseline")

    assert workspace["active_session"]["name"] == "Cleaned baseline"
    assert loaded_store.saved_plots[plot_id].session_name == "Cleaned baseline"


def test_delete_session_removes_child_branch_and_branch_plots(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    child_id = loaded_store.create_session("Child", base_id)["active_session_id"]
    grandchild_id = loaded_store.create_session("Grandchild", child_id)["active_session_id"]

    loaded_store.save_plot(child_id, "age", "histogram", controls={"bins": 4}, title="Child plot")
    loaded_store.save_plot(grandchild_id, "age", "histogram", controls={"bins": 4}, title="Grandchild plot")
    loaded_store.set_active_session(grandchild_id)

    workspace = loaded_store.delete_session(child_id)

    assert [session["id"] for session in workspace["sessions"]] == [base_id]
    assert workspace["active_session_id"] == base_id
    assert workspace["saved_plots"] == []


def test_delete_protects_the_only_session_and_unknown_sessions(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    with pytest.raises(ValueError, match="Cannot delete the only session"):
        loaded_store.delete_session(base_id)
    with pytest.raises(ValueError, match="Session not found"):
        loaded_store.rename_session("missing", "New name")


def test_child_session_created_after_parent_operations_uses_current_snapshot_but_not_future_parent_changes(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    s1_id = loaded_store.create_session("s1", base_id)["active_session_id"]

    loaded_store.apply_session_operation(s1_id, "drop_missing", {"column": "income"})
    first_parent_operation = loaded_store.sessions[s1_id].operations[-1]
    branch_id = loaded_store.create_session("s1 branch 1", s1_id)["active_session_id"]

    assert loaded_store.sessions[branch_id].source_operation_id == first_parent_operation.id
    assert len(loaded_store.sessions[branch_id].data) == 7

    loaded_store.apply_session_operation(s1_id, "drop_column", {"column": "segment"})

    assert "segment" not in loaded_store.sessions[s1_id].data.columns
    assert "segment" in loaded_store.sessions[branch_id].data.columns
    assert len(loaded_store.sessions[branch_id].data) == 7


def test_session_summary_keeps_created_overview_separate_from_current_overview(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    child_id = loaded_store.create_session("Branch", base_id)["active_session_id"]

    loaded_store.apply_session_operation(child_id, "drop_column", {"column": "segment"})
    child_summary = next(session for session in loaded_store.workspace_summary()["sessions"] if session["id"] == child_id)

    assert child_summary["created_overview"]["columns"] == 5
    assert child_summary["overview"]["columns"] == 4
