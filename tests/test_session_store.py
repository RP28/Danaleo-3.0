from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from danaleo.core.session_store import WorkspaceStore


def project_bytes(manifest: dict, source: bytes = b"x\n1\n") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("source.csv", source)
    return buffer.getvalue()


def test_workspace_summary_before_upload_is_safe():
    workspace_store = WorkspaceStore()

    workspace = workspace_store.workspace_summary()

    assert workspace["ready"] is False
    assert workspace["active_dataset_id"] is None
    assert workspace["datasets"] == []
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


@pytest.mark.parametrize(
    ("source", "expected_delimiter"),
    [
        (b"name;amount;city\nAlice;12,50;Paris\nBob;9,25;Lyon\n", ";"),
        (b"name\tamount\tcity\nAlice\t12.5\tParis\n", "\t"),
        (b"name|amount|city\nAlice|12.5|Paris\n", "|"),
    ],
)
def test_load_csv_detects_common_delimiters(source: bytes, expected_delimiter: str):
    workspace = WorkspaceStore().load_csv(source, "export.csv")

    assert workspace["active_session"]["overview"]["columns"] == 3
    assert workspace["parse_info"]["delimiter"] == expected_delimiter


def test_load_csv_handles_excel_separator_directive_bom_and_common_encodings():
    excel = "sep=;\nname;city\nAlice;Zürich\n".encode("utf-8-sig")
    excel_workspace = WorkspaceStore().load_csv(excel, "excel.csv")
    assert excel_workspace["active_session"]["overview"]["rows"] == 1
    assert excel_workspace["active_session"]["overview"]["columns"] == 2
    assert excel_workspace["parse_info"] == {
        "delimiter": ";",
        "encoding": "utf-8-sig",
        "skiprows": 1,
    }

    utf16_workspace = WorkspaceStore().load_csv("name;city\nAlice;Zürich\n".encode("utf-16"), "utf16.csv")
    assert utf16_workspace["active_session"]["overview"]["columns"] == 2
    assert utf16_workspace["parse_info"]["encoding"] == "utf-16"

    windows_workspace = WorkspaceStore().load_csv("name,city\nAndré,Montréal\n".encode("cp1252"), "windows.csv")
    assert windows_workspace["active_session"]["overview"]["columns"] == 2
    assert windows_workspace["parse_info"]["encoding"] == "cp1252"


def test_load_csv_preserves_valid_quoted_single_column_files():
    workspace = WorkspaceStore().load_csv(b'"description, text"\n"hello, world"\n', "single.csv")

    assert workspace["active_session"]["overview"]["columns"] == 1
    assert workspace["active_session"]["overview"]["rows"] == 1


def test_load_csv_rejects_malformed_non_comma_files_instead_of_loading_one_column():
    with pytest.raises(ValueError, match="Could not parse delimited data file"):
        WorkspaceStore().load_csv(b'name;notes\nAlice;"unterminated\n', "broken.csv")


def test_project_round_trip_preserves_detected_csv_options():
    workspace_store = WorkspaceStore()
    original = workspace_store.load_csv("sep=;\nname;city\nAlice;Paris\n".encode("utf-16"), "excel.csv")

    restored_store = WorkspaceStore()
    restored = restored_store.import_project(workspace_store.export_project())

    assert restored["parse_info"] == original["parse_info"]
    assert restored["active_session"]["overview"]["columns"] == 2
    assert restored["active_session"]["overview"]["rows"] == 1


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

    with pytest.raises(ValueError, match="Upload a data file first"):
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


def test_create_session_defaults_to_active_parent_and_activation_validates(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    child = loaded_store.create_session("Child")

    assert child["active_session"]["parent_id"] == base_id
    with pytest.raises(ValueError, match="Session not found"):
        loaded_store.set_active_session("missing")


def test_sessions_are_independent_copies(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    child_workspace = loaded_store.create_session("Analysis 1", base_id)
    child_id = child_workspace["active_session_id"]

    loaded_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})

    assert len(loaded_store.sessions[child_id].data) == 5
    assert len(loaded_store.sessions[base_id].data) == 8
    assert loaded_store.sessions[child_id].operations[-1].label == "Filter: age > 30"


def test_drop_duplicates_is_recorded_in_session_history():
    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_csv(b"x,y\n1,A\n1,A\n2,B\n", "duplicates.csv")
    session_id = workspace["active_session_id"]

    next_workspace = workspace_store.apply_session_operation(session_id, "drop_duplicates", {})

    assert next_workspace["active_session"]["overview"]["rows"] == 2
    assert next_workspace["active_session"]["operations"][-1]["label"] == "Drop duplicate rows"


def test_imputation_is_recorded_and_replayed_by_progress_export():
    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_csv(b"value,label\n1,A\n,B\n3,\n", "missing.csv")
    session_id = workspace["active_session_id"]

    imputed = workspace_store.apply_session_operation(
        session_id,
        "impute_missing",
        {"column": "value", "method": "mean"},
    )

    assert imputed["active_session"]["operations"][-1]["label"] == "Impute value: Mean"
    assert workspace_store.sessions[session_id].data["value"].tolist() == [1.0, 2.0, 3.0]

    restored_store = WorkspaceStore()
    restored = restored_store.import_project(workspace_store.export_project())
    assert restored["active_session"]["profile"]["missing_cells"] == 1
    assert restored_store.require_session().data["value"].tolist() == [1.0, 2.0, 3.0]


def test_transformations_are_recorded_and_replayed_by_progress_export():
    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_csv(b"value,label\n1,A\n2,B\n3,A\n", "transform.csv")
    session_id = workspace["active_session_id"]

    workspace_store.apply_session_operation(
        session_id,
        "transform_column",
        {"column": "label", "method": "one_hot"},
    )
    transformed = workspace_store.apply_session_operation(
        session_id,
        "transform_column",
        {"column": "value", "method": "min_max"},
    )

    assert transformed["active_session"]["operations"][-1]["label"] == "Transform value: Min Max"
    assert workspace_store.sessions[session_id].data.columns.tolist() == ["value", "label_A", "label_B"]

    restored_store = WorkspaceStore()
    restored_store.import_project(workspace_store.export_project())
    restored = restored_store.require_session().data
    assert restored.columns.tolist() == ["value", "label_A", "label_B"]
    assert restored["value"].tolist() == [0.0, 0.5, 1.0]


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

    child_id = loaded_store.create_session("Child", base_id)["active_session_id"]
    with pytest.raises(ValueError, match="Cannot delete every session"):
        loaded_store.delete_session(base_id)
    assert child_id in loaded_store.sessions


def test_delete_non_active_session_preserves_active_session(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    first_id = loaded_store.create_session("First", base_id)["active_session_id"]
    second_id = loaded_store.create_session("Second", base_id)["active_session_id"]

    workspace = loaded_store.delete_session(first_id)

    assert workspace["active_session_id"] == second_id
    assert first_id not in loaded_store.sessions


def test_preview_plot_does_not_mutate_store_or_advance_time(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    initial_time = loaded_store.time_counter
    initial_plots = dict(loaded_store.saved_plots)

    figure = loaded_store.preview_plot(base_id, "age", "histogram", controls={"bins": 4})

    assert figure["plot_type"] == "histogram"
    assert loaded_store.time_counter == initial_time
    assert loaded_store.saved_plots == initial_plots


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


def test_loading_another_csv_preserves_previous_dataset_state(csv_bytes: bytes):
    workspace_store = WorkspaceStore()

    first = workspace_store.load_csv(csv_bytes, "customers.csv")
    first_dataset_id = first["active_dataset_id"]
    base_id = first["active_session_id"]

    workspace_store.create_session("Old branch", base_id)
    workspace_store.save_plot(base_id, "age", "histogram", controls={"bins": 4})

    second = workspace_store.load_csv(b"x,y\n1,A\n2,B\n", "new.csv")
    second_dataset_id = second["active_dataset_id"]

    assert second["csv_name"] == "new.csv"
    assert second["active_session"]["overview"]["rows"] == 2
    assert len(second["sessions"]) == 1
    assert second["saved_plots"] == []
    assert [dataset["csv_name"] for dataset in second["datasets"]] == ["customers.csv", "new.csv"]

    restored_first = workspace_store.set_active_dataset(first_dataset_id)
    assert restored_first["active_dataset_id"] == first_dataset_id
    assert len(restored_first["sessions"]) == 2
    assert len(restored_first["saved_plots"]) == 1

    restored_second = workspace_store.set_active_dataset(second_dataset_id)
    assert len(restored_second["sessions"]) == 1
    assert restored_second["saved_plots"] == []


def test_dataset_switching_and_cross_dataset_ids_keep_state_isolated():
    workspace_store = WorkspaceStore()
    first = workspace_store.load_csv(b"x\n1\n2\n", "first.csv")
    first_dataset_id = first["active_dataset_id"]
    first_session_id = first["active_session_id"]
    workspace_store.apply_session_operation(first_session_id, "filter_rows", {"query": "x > 1"})
    workspace_store.save_plot(first_session_id, "x", "histogram")
    first_plot_id = next(iter(workspace_store.saved_plots))

    second = workspace_store.load_csv(b"y\n10\n20\n30\n", "second.csv")
    second_dataset_id = second["active_dataset_id"]
    second_session_id = second["active_session_id"]
    workspace_store.create_session("Second branch", second_session_id)

    first_again = workspace_store.set_active_session(first_session_id)
    assert first_again["active_dataset_id"] == first_dataset_id
    assert first_again["active_session"]["overview"]["rows"] == 1
    assert len(first_again["saved_plots"]) == 1

    second_again = workspace_store.set_active_dataset(second_dataset_id)
    assert len(second_again["sessions"]) == 2
    assert second_again["saved_plots"] == []

    updated = workspace_store.update_plot(first_plot_id, remark="first only")
    assert updated["active_dataset_id"] == first_dataset_id
    assert updated["saved_plots"][0]["remark"] == "first only"


def test_delete_dataset_handles_active_inactive_final_and_unknown_datasets():
    workspace_store = WorkspaceStore()
    first = workspace_store.load_csv(b"x\n1\n", "first.csv")
    first_id = first["active_dataset_id"]
    second = workspace_store.load_csv(b"y\n2\n", "second.csv")
    second_id = second["active_dataset_id"]
    second_path = Path(workspace_store.csv_path)
    third = workspace_store.load_csv(b"z\n3\n", "third.csv")
    third_id = third["active_dataset_id"]

    after_inactive_delete = workspace_store.delete_dataset(second_id)
    assert not second_path.exists()
    assert after_inactive_delete["active_dataset_id"] == third_id
    assert [dataset["id"] for dataset in after_inactive_delete["datasets"]] == [first_id, third_id]

    after_active_delete = workspace_store.delete_dataset(third_id)
    assert after_active_delete["active_dataset_id"] == first_id

    empty = workspace_store.delete_dataset(first_id)
    assert empty["ready"] is False
    assert empty["datasets"] == []

    with pytest.raises(ValueError, match="Dataset not found"):
        workspace_store.delete_dataset("missing")
    with pytest.raises(ValueError, match="Dataset not found"):
        workspace_store.set_active_dataset("missing")


def test_batch_load_rolls_back_every_new_dataset_when_one_csv_fails():
    workspace_store = WorkspaceStore()
    original = workspace_store.load_csv(b"x\n1\n", "existing.csv")
    original_time = workspace_store.time_counter

    with pytest.raises(Exception):
        workspace_store.load_csv_batch(
            [
                (b"a\n1\n", "valid.csv"),
                (b'a,b\n1,"unterminated\n', "broken.csv"),
            ]
        )

    workspace = workspace_store.workspace_summary()
    assert workspace["active_dataset_id"] == original["active_dataset_id"]
    assert [dataset["csv_name"] for dataset in workspace["datasets"]] == ["existing.csv"]
    assert workspace_store.time_counter == original_time


def test_reset_releases_all_dataset_sources():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"x\n1\n", "first.csv")
    workspace_store.load_csv(b"y\n2\n", "second.csv")
    paths = [Path(dataset.csv_path) for dataset in workspace_store.datasets.values()]

    workspace_store.reset()

    assert not any(path.exists() for path in paths)
    assert workspace_store.workspace_summary()["ready"] is False


@pytest.mark.parametrize(
    ("how", "result_rows", "matched", "left_only", "right_only"),
    [
        ("inner", 2, 2, 0, 0),
        ("left", 3, 2, 1, 0),
        ("right", 3, 2, 0, 1),
        ("outer", 4, 2, 1, 1),
        ("cross", 9, 9, 0, 0),
    ],
)
def test_merge_preview_supports_join_types_without_mutating_active_dataset(
    how, result_rows, matched, left_only, right_only
):
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,left_value\n1,A\n2,B\n3,C\n", "left.csv")
    left_dataset_id = left["active_dataset_id"]
    left_session_id = left["active_session_id"]
    right = workspace_store.load_csv(b"id,right_value\n2,X\n3,Y\n4,Z\n", "right.csv")
    right_dataset_id = right["active_dataset_id"]

    preview = workspace_store.preview_merge(
        left_session_id,
        right["active_session_id"],
        how,
        ["id"],
        ["id"],
        ["_left", "_right"],
    )

    assert preview["result_rows"] == result_rows
    assert preview["matched_rows"] == matched
    assert preview["left_only_rows"] == left_only
    assert preview["right_only_rows"] == right_only
    assert workspace_store.active_dataset_id == right_dataset_id
    assert len(workspace_store.datasets) == 2
    assert len(workspace_store.datasets[left_dataset_id].sessions[left_session_id].data) == 3


def test_create_merge_makes_independent_derived_dataset_with_provenance():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,value\n1,A\n2,B\n3,C\n", "left.csv")
    left_id = left["active_dataset_id"]
    right = workspace_store.load_csv(b"customer_id,value\n2,X\n3,Y\n4,Z\n", "right.csv")
    right_id = right["active_dataset_id"]

    merged = workspace_store.create_merged_dataset(
        left["active_session_id"],
        right["active_session_id"],
        "outer",
        ["id"],
        ["customer_id"],
        ["_customer", "_order"],
        "one_to_one",
        "../combined",
    )
    merged_id = merged["active_dataset_id"]

    assert merged["csv_name"] == "combined.csv"
    assert merged["active_session"]["name"] == "Merged result"
    assert merged["active_session"]["overview"] == {
        **merged["active_session"]["overview"],
        "rows": 4,
        "columns": 4,
    }
    assert merged["datasets"][-1]["provenance"]["how"] == "outer"
    assert merged["datasets"][-1]["provenance"]["left_dataset_name"] == "left.csv"
    assert merged["datasets"][-1]["provenance"]["right_dataset_name"] == "right.csv"

    workspace_store.delete_dataset(left_id)
    workspace_store.delete_dataset(right_id)
    assert workspace_store.active_dataset_id == merged_id
    assert workspace_store.require_session().data["id"].notna().sum() == 3


def test_merge_supports_multiple_keys_and_session_snapshots():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(
        b"id,year,value\n1,2024,A\n1,2025,B\n2,2025,C\n",
        "left.csv",
    )
    left_branch = workspace_store.create_session("Filtered left", left["active_session_id"])[
        "active_session_id"
    ]
    workspace_store.apply_session_operation(left_branch, "filter_rows", {"query": "year == 2025"})
    right = workspace_store.load_csv(
        b"customer_id,year,score\n1,2024,10\n1,2025,20\n2,2025,30\n",
        "right.csv",
    )

    preview = workspace_store.preview_merge(
        left_branch,
        right["active_session_id"],
        "inner",
        ["id", "year"],
        ["customer_id", "year"],
        ["_left", "_right"],
        "one_to_one",
    )

    assert preview["result_rows"] == 2
    assert preview["matched_rows"] == 2


@pytest.mark.parametrize(
    ("left_on", "right_on", "suffixes", "validate", "message"),
    [
        ([], [], ["_left", "_right"], None, "Select at least one join key"),
        (["id"], ["id", "other"], ["_left", "_right"], None, "same count"),
        (["missing"], ["id"], ["_left", "_right"], None, "Left join key not found"),
        (["id"], ["missing"], ["_left", "_right"], None, "Right join key not found"),
        (["id", "id"], ["id", "other"], ["_left", "_right"], None, "only be selected once"),
        (["id"], ["id"], ["_same", "_same"], None, "different column suffixes"),
        (["id"], ["id"], ["_left", "_right"], "invalid", "Unsupported relationship"),
    ],
)
def test_merge_rejects_invalid_configuration(left_on, right_on, suffixes, validate, message):
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,other\n1,A\n2,B\n", "left.csv")
    right = workspace_store.load_csv(b"id,other\n1,X\n2,Y\n", "right.csv")

    with pytest.raises(ValueError, match=message):
        workspace_store.preview_merge(
            left["active_session_id"],
            right["active_session_id"],
            "inner",
            left_on,
            right_on,
            suffixes,
            validate,
        )


def test_merge_relationship_validation_and_unknown_inputs_are_rejected():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,value\n1,A\n1,B\n", "left.csv")
    right = workspace_store.load_csv(b"id,score\n1,10\n2,20\n", "right.csv")

    with pytest.raises(Exception, match="not a one-to-one merge"):
        workspace_store.preview_merge(
            left["active_session_id"],
            right["active_session_id"],
            "inner",
            ["id"],
            ["id"],
            ["_left", "_right"],
            "one_to_one",
        )
    with pytest.raises(ValueError, match="Unsupported join type"):
        workspace_store.preview_merge(
            left["active_session_id"],
            right["active_session_id"],
            "sideways",
            ["id"],
            ["id"],
            ["_left", "_right"],
        )
    with pytest.raises(ValueError, match="Session not found"):
        workspace_store.preview_merge(
            "missing",
            right["active_session_id"],
            "inner",
            ["id"],
            ["id"],
            ["_left", "_right"],
        )


def test_merge_dataset_detail_and_progress_round_trip_preserve_provenance():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,a\n1,A\n2,B\n", "left.csv")
    right = workspace_store.load_csv(b"id,b\n2,X\n3,Y\n", "right.csv")
    merged = workspace_store.create_merged_dataset(
        left["active_session_id"],
        right["active_session_id"],
        "outer",
        ["id"],
        ["id"],
        ["_left", "_right"],
        name="joined.csv",
    )
    merged_id = merged["active_dataset_id"]

    detail = workspace_store.dataset_detail(merged_id)
    assert detail["session_options"][0]["columns"] == ["id", "a", "b"]
    assert detail["provenance"]["diagnostics"]["result_rows"] == 3

    restored_store = WorkspaceStore()
    restored = restored_store.import_project(workspace_store.export_project())
    restored_merged = next(dataset for dataset in restored["datasets"] if dataset["id"] == merged_id)
    assert restored_merged["provenance"]["type"] == "merge"
    assert restored_merged["provenance"]["how"] == "outer"
    assert restored_store.datasets[merged_id].sessions[
        restored_merged["active_session_id"]
    ].data.shape == (3, 3)


def test_delete_plot_removes_only_the_requested_saved_plot(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id

    loaded_store.save_plot(base_id, "age", "histogram", controls={"bins": 4}, title="Age")
    loaded_store.save_plot(base_id, "income", "histogram", controls={"bins": 4}, title="Income")
    first_plot_id = next(iter(loaded_store.saved_plots))

    workspace = loaded_store.delete_plot(first_plot_id)

    assert first_plot_id not in loaded_store.saved_plots
    assert len(workspace["saved_plots"]) == 1


def test_update_plot_changes_only_supplied_fields_and_default_title(loaded_store: WorkspaceStore):
    base_id = loaded_store.active_session_id
    workspace = loaded_store.save_plot(base_id, "age", "histogram")
    plot = workspace["saved_plots"][0]

    assert plot["title"] == "Histogram — age"
    updated = loaded_store.update_plot(plot["id"], remark="reviewed")

    assert updated["saved_plots"][0]["remark"] == "reviewed"
    assert updated["saved_plots"][0]["include_in_export"] is True


def test_project_export_requires_ready_store_and_existing_source(loaded_store: WorkspaceStore):
    with pytest.raises(ValueError, match="Upload a data file"):
        WorkspaceStore().export_project()

    Path(loaded_store.csv_path).unlink()
    with pytest.raises(ValueError, match="Source data file"):
        loaded_store.export_project()


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({"format": "wrong", "version": 1, "sessions": [{}]}, "Unsupported"),
        ({"format": "danaleo.project", "version": 1, "sessions": []}, "does not contain any sessions"),
        (
            {
                "format": "danaleo.project",
                "version": 1,
                "sessions": [
                    {
                        "id": "child",
                        "name": "Child",
                        "parent_id": "missing",
                        "created_time": 1,
                        "operations": [],
                    }
                ],
            },
            "missing session",
        ),
    ],
)
def test_project_import_rejects_invalid_manifests(manifest, message):
    with pytest.raises(ValueError, match=message):
        WorkspaceStore().import_project(project_bytes(manifest))


def test_project_import_rejects_missing_archive_members():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "danaleo.project", "version": 1, "sessions": [{}]}),
        )

    with pytest.raises(ValueError, match="missing required project data"):
        WorkspaceStore().import_project(buffer.getvalue())


def test_project_import_rejects_missing_source_operation():
    manifest = {
        "format": "danaleo.project",
        "version": 1,
        "sessions": [
            {"id": "base", "name": "Base", "parent_id": None, "created_time": 1, "operations": []},
            {
                "id": "child",
                "name": "Child",
                "parent_id": "base",
                "source_operation_id": "missing-operation",
                "created_time": 2,
                "operations": [],
            },
        ],
    }

    with pytest.raises(ValueError, match="missing operation"):
        WorkspaceStore().import_project(project_bytes(manifest))


def test_project_import_falls_back_active_session_and_skips_orphan_plots():
    manifest = {
        "format": "danaleo.project",
        "version": 1,
        "active_session_id": "missing",
        "sessions": [
            {"id": "base", "name": "Base", "parent_id": None, "created_time": 1, "operations": []}
        ],
        "saved_plots": [
            {
                "id": "orphan",
                "session_id": "missing",
                "column": "x",
                "plot_type": "histogram",
                "created_time": 2,
            }
        ],
    }

    workspace = WorkspaceStore().import_project(project_bytes(manifest))

    assert workspace["active_session_id"] == "base"
    assert workspace["saved_plots"] == []


def test_project_export_import_preserves_sampling_and_time_progression(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    original = workspace_store.load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="frac",
        sample_frac=0.5,
        random_state=11,
    )
    original_time = workspace_store.time_counter

    restored_store = WorkspaceStore()
    restored = restored_store.import_project(workspace_store.export_project())

    assert restored["sample_info"] == original["sample_info"]
    assert restored["active_session"]["overview"]["rows"] == 4
    assert restored_store.time_counter == original_time
    restored_store.create_session("After restore")
    assert restored_store.time_counter > original_time


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

    assert names == {
        "manifest.json",
        f"datasets/{loaded_store.active_dataset_id}/source.csv",
    }
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


def test_multi_dataset_project_round_trip_preserves_all_sources_and_active_states(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    first = workspace_store.load_csv(csv_bytes, "customers.csv", sample_mode="n", sample_n=4)
    first_dataset_id = first["active_dataset_id"]
    first_session_id = first["active_session_id"]
    workspace_store.save_plot(first_session_id, "age", "histogram", title="First ages")

    second = workspace_store.load_csv(b"value,label\n1,A\n2,B\n3,C\n", "values.csv")
    second_dataset_id = second["active_dataset_id"]
    second_base_id = second["active_session_id"]
    second_branch_id = workspace_store.create_session("Values branch", second_base_id)["active_session_id"]
    workspace_store.apply_session_operation(second_branch_id, "filter_rows", {"query": "value > 1"})

    exported = workspace_store.export_project()
    with ZipFile(BytesIO(exported)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        names = set(archive.namelist())

    assert manifest["version"] == 2
    assert manifest["active_dataset_id"] == second_dataset_id
    assert {dataset["id"] for dataset in manifest["datasets"]} == {first_dataset_id, second_dataset_id}
    assert names == {
        "manifest.json",
        f"datasets/{first_dataset_id}/source.csv",
        f"datasets/{second_dataset_id}/source.csv",
    }

    restored_store = WorkspaceStore()
    restored = restored_store.import_project(exported)
    assert restored["active_dataset_id"] == second_dataset_id
    assert restored["active_session_id"] == second_branch_id
    assert restored["active_session"]["overview"]["rows"] == 2
    assert len(restored["datasets"]) == 2

    restored_first = restored_store.set_active_dataset(first_dataset_id)
    assert restored_first["sample_info"]["sample_n"] == 4
    assert restored_first["saved_plots"][0]["title"] == "First ages"
    assert restored_first["active_session"]["overview"]["rows"] == 4


def test_v2_project_import_validates_datasets_sources_and_active_dataset_fallback():
    base_dataset = {
        "id": "first",
        "csv_name": "first.csv",
        "active_session_id": "base",
        "sessions": [
            {"id": "base", "name": "Base", "parent_id": None, "created_time": 1, "operations": []}
        ],
        "saved_plots": [],
    }

    def v2_bytes(datasets: list[dict], sources: dict[str, bytes]) -> bytes:
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": "danaleo.project",
                        "version": 2,
                        "active_dataset_id": "missing",
                        "datasets": datasets,
                    }
                ),
            )
            for path, source in sources.items():
                archive.writestr(path, source)
        return buffer.getvalue()

    restored = WorkspaceStore().import_project(
        v2_bytes([base_dataset], {"datasets/first/source.csv": b"x\n1\n"})
    )
    assert restored["active_dataset_id"] == "first"

    with pytest.raises(ValueError, match="missing required project data"):
        WorkspaceStore().import_project(v2_bytes([base_dataset], {}))
    with pytest.raises(ValueError, match="duplicate dataset ids"):
        WorkspaceStore().import_project(
            v2_bytes(
                [base_dataset, base_dataset],
                {"datasets/first/source.csv": b"x\n1\n"},
            )
        )
    with pytest.raises(ValueError, match="without an id"):
        WorkspaceStore().import_project(v2_bytes([{**base_dataset, "id": ""}], {}))
