from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from danaleo.core.session_store import WorkspaceStore


def test_workspace_summary_before_upload_is_safe():
    workspace_store = WorkspaceStore()

    workspace = workspace_store.workspace_summary()

    assert workspace["ready"] is False
    assert workspace["csv_name"] is None
    assert workspace["active_session_id"] is None
    assert workspace["active_session"] is None
    assert workspace["sessions"] == []
    assert workspace["saved_plots"] == []


def test_load_csv_creates_base_workspace(csv_bytes: bytes):
    workspace_store = WorkspaceStore()

    workspace = workspace_store.load_csv(csv_bytes, "customers.csv")

    assert workspace["ready"] is True
    assert workspace["csv_name"] == "customers.csv"
    assert workspace["active_session"]["name"] == "Base Session"
    assert workspace["active_session"]["overview"]["rows"] == 8
    assert workspace["active_session"]["overview"]["columns"] == 5
    assert {card["name"] for card in workspace["active_session"]["columns"]} == {
        "age",
        "income",
        "city",
        "segment",
        "flag",
    }


def test_sampling_options_record_how_data_was_reduced(csv_bytes: bytes):
    by_count = WorkspaceStore().load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="n",
        sample_n=3,
        random_state=7,
    )

    assert by_count["active_session"]["overview"]["rows"] == 3
    assert by_count["sample_info"] == {
        "mode": "n",
        "sample_n": 3,
        "random_state": 7,
        "original_rows": 8,
    }

    by_fraction = WorkspaceStore().load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="frac",
        sample_frac=0.5,
        random_state=7,
    )

    assert by_fraction["active_session"]["overview"]["rows"] == 4
    assert by_fraction["sample_info"] == {
        "mode": "frac",
        "sample_frac": 0.5,
        "random_state": 7,
        "original_rows": 8,
    }


def test_sampling_is_ignored_when_it_would_not_reduce_rows(csv_bytes: bytes):
    too_large = WorkspaceStore().load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="n",
        sample_n=99,
    )
    assert too_large["active_session"]["overview"]["rows"] == 8
    assert too_large["sample_info"] is None

    zero_rows = WorkspaceStore().load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="n",
        sample_n=0,
    )
    assert zero_rows["active_session"]["overview"]["rows"] == 8
    assert zero_rows["sample_info"] is None

    full_fraction = WorkspaceStore().load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="frac",
        sample_frac=1,
    )
    assert full_fraction["active_session"]["overview"]["rows"] == 8
    assert full_fraction["sample_info"] is None


def test_require_session_validates_upload_and_session_id():
    workspace_store = WorkspaceStore()

    with pytest.raises(ValueError, match="Upload a CSV file first"):
        workspace_store.require_session("missing")

    workspace_store.load_csv(b"age\n1\n2\n", "small.csv")

    with pytest.raises(ValueError, match="Session not found"):
        workspace_store.require_session("missing")


def test_create_session_rejects_missing_parent_and_blank_name(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    with pytest.raises(ValueError, match="Session name is required"):
        loaded_store.create_session("   ", base_id)

    with pytest.raises(ValueError, match="Session not found"):
        loaded_store.create_session("Branch", "missing")


def test_sessions_are_independent_copies(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    child_workspace = loaded_store.create_session("Analysis 1", base_id)
    child_id = child_workspace["active_session_id"]

    loaded_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})

    assert len(loaded_store.sessions[child_id].data) == 5
    assert len(loaded_store.sessions[base_id].data) == 8
    assert loaded_store.sessions[child_id].operations[-1].label == "Filter: age > 30"


def test_child_session_created_after_parent_operations_uses_current_snapshot_but_not_future_parent_changes(
    loaded_store: WorkspaceStore,
):
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


def test_rename_session_updates_saved_plot_metadata(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    loaded_store.save_plot(
        base_id,
        "age",
        "histogram",
        controls={"bins": 4},
        title="Age histogram",
    )
    plot_id = next(iter(loaded_store.saved_plots))

    workspace = loaded_store.rename_session(base_id, "Cleaned baseline")

    assert workspace["active_session"]["name"] == "Cleaned baseline"
    assert loaded_store.saved_plots[plot_id].session_name == "Cleaned baseline"


def test_delete_session_removes_child_branch_and_branch_plots(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    child_id = loaded_store.create_session("Child", base_id)["active_session_id"]
    grandchild_id = loaded_store.create_session("Grandchild", child_id)["active_session_id"]

    loaded_store.save_plot(child_id, "age", "histogram", controls={"bins": 4}, title="Child plot")
    loaded_store.save_plot(
        grandchild_id,
        "age",
        "histogram",
        controls={"bins": 4},
        title="Grandchild plot",
    )

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


def test_session_summary_keeps_created_overview_separate_from_current_overview(
    loaded_store: WorkspaceStore,
):
    base_id = loaded_store.active_session_id

    child_id = loaded_store.create_session("Branch", base_id)["active_session_id"]
    loaded_store.apply_session_operation(child_id, "drop_column", {"column": "segment"})

    child_summary = next(
        session
        for session in loaded_store.workspace_summary()["sessions"]
        if session["id"] == child_id
    )

    assert child_summary["created_overview"]["columns"] == 5
    assert child_summary["overview"]["columns"] == 4


def test_reload_csv_resets_previous_sessions_and_plots(csv_bytes: bytes):
    workspace_store = WorkspaceStore()

    first = workspace_store.load_csv(csv_bytes, "customers.csv")
    base_id = first["active_session_id"]

    workspace_store.create_session("Old branch", base_id)
    workspace_store.save_plot(base_id, "age", "histogram", controls={"bins": 4})

    second = workspace_store.load_csv(b"x,y\n1,A\n2,B\n", "new.csv")

    assert second["csv_name"] == "new.csv"
    assert second["active_session"]["overview"]["rows"] == 2
    assert len(second["sessions"]) == 1
    assert second["saved_plots"] == []


def test_delete_plot_removes_only_the_requested_saved_plot(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    loaded_store.save_plot(base_id, "age", "histogram", controls={"bins": 4}, title="Age")
    loaded_store.save_plot(base_id, "income", "histogram", controls={"bins": 4}, title="Income")
    first_plot_id = next(iter(loaded_store.saved_plots))

    workspace = loaded_store.delete_plot(first_plot_id)

    assert first_plot_id not in loaded_store.saved_plots
    assert len(workspace["saved_plots"]) == 1


def test_project_export_import_replays_operations_without_duplicate_session_data(
    loaded_store: WorkspaceStore,
):
    base_id = loaded_store.active_session_id
    branch_id = loaded_store.create_session("Branch", base_id)["active_session_id"]
    loaded_store.apply_session_operation(branch_id, "drop_missing", {"column": "income"})
    source_operation_id = loaded_store.sessions[branch_id].operations[-1].id
    child_id = loaded_store.create_session("Child", branch_id)["active_session_id"]
    loaded_store.apply_session_operation(branch_id, "drop_column", {"column": "segment"})
    loaded_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})
    loaded_store.save_plot(child_id, "age", "histogram", controls={"bins": 4}, title="Child ages")

    exported = loaded_store.export_project()
    with ZipFile(BytesIO(exported)) as archive:
        names = set(archive.namelist())
        manifest = archive.read("manifest.json").decode("utf-8")

    assert names == {"manifest.json", "source.csv"}
    assert "\"data\"" not in manifest

    restored_store = WorkspaceStore()
    workspace = restored_store.import_project(exported)

    restored_branch = restored_store.sessions[branch_id]
    restored_child = restored_store.sessions[child_id]

    assert workspace["csv_name"] == "customers.csv"
    assert restored_child.source_operation_id == source_operation_id
    assert len(restored_branch.data) == 7
    assert "segment" not in restored_branch.data.columns
    assert len(restored_child.data) == 5
    assert "segment" in restored_child.data.columns
    assert workspace["saved_plots"][0]["title"] == "Child ages"
    assert workspace["saved_plots"][0]["figure"]["image"].startswith("data:image/png;base64,")
