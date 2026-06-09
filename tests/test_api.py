from __future__ import annotations

from fastapi.testclient import TestClient

from danaleo.core.session_store import store
from danaleo.server.app import app


def upload_csv(client: TestClient, csv_bytes: bytes, filename: str = "customers.csv") -> dict:
    response = client.post(
        "/api/upload",
        files={"file": (filename, csv_bytes, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_workspace_before_upload():
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/workspace").json()["ready"] is False


def test_api_returns_400_before_upload_for_workspace_actions():
    client = TestClient(app)

    create = client.post("/api/sessions", json={"name": "Branch", "parent_id": "missing"})
    assert create.status_code == 400
    assert "Upload a CSV file first" in create.json()["detail"]

    activate = client.post("/api/sessions/activate", json={"session_id": "missing"})
    assert activate.status_code == 400
    assert "Upload a CSV file first" in activate.json()["detail"]

    export_response = client.get("/api/export/notebook")
    assert export_response.status_code == 400
    assert "Nothing to export yet" in export_response.json()["detail"]

    progress_response = client.get("/api/progress/download")
    assert progress_response.status_code == 400
    assert "Upload a CSV" in progress_response.json()["detail"]


def test_upload_rejects_non_csv_file(csv_bytes: bytes):
    client = TestClient(app)

    response = client.post(
        "/api/upload",
        files={"file": ("customers.txt", csv_bytes, "text/plain")},
    )

    assert response.status_code == 400
    assert "CSV" in response.json()["detail"]


def test_upload_rejects_malformed_csv_and_accepts_uppercase_extension():
    client = TestClient(app)

    malformed = client.post(
        "/api/upload",
        files={"file": ("broken.csv", b'a,b\n1,"unterminated\n', "text/csv")},
    )
    assert malformed.status_code == 400

    uppercase = client.post(
        "/api/upload",
        files={"file": ("VALID.CSV", b"x\n1\n", "text/csv")},
    )
    assert uppercase.status_code == 200


def test_upload_with_sampling_modes(csv_bytes: bytes):
    client = TestClient(app)

    sampled = client.post(
        "/api/upload",
        data={"sample_mode": "n", "sample_n": "3", "random_state": "7"},
        files={"file": ("customers.csv", csv_bytes, "text/csv")},
    )

    assert sampled.status_code == 200
    assert sampled.json()["active_session"]["overview"]["rows"] == 3
    assert sampled.json()["sample_info"] == {
        "mode": "n",
        "sample_n": 3,
        "random_state": 7,
        "original_rows": 8,
    }

    fractional = client.post(
        "/api/upload",
        data={"sample_mode": "frac", "sample_frac": "0.5", "random_state": "9"},
        files={"file": ("customers.csv", csv_bytes, "text/csv")},
    )
    assert fractional.status_code == 200
    assert fractional.json()["active_session"]["overview"]["rows"] == 4


def test_multi_csv_upload_activation_deletion_and_progress_round_trip(csv_bytes: bytes):
    client = TestClient(app)
    uploaded = client.post(
        "/api/upload",
        files=[
            ("file", ("customers.csv", csv_bytes, "text/csv")),
            ("file", ("values.csv", b"value\n1\n2\n3\n", "text/csv")),
        ],
    )

    assert uploaded.status_code == 200
    workspace = uploaded.json()
    assert [dataset["csv_name"] for dataset in workspace["datasets"]] == [
        "customers.csv",
        "values.csv",
    ]
    assert workspace["csv_name"] == "values.csv"
    first_id, second_id = [dataset["id"] for dataset in workspace["datasets"]]

    activated = client.post("/api/datasets/activate", json={"dataset_id": first_id})
    assert activated.status_code == 200
    assert activated.json()["csv_name"] == "customers.csv"

    progress = client.get("/api/progress/download")
    assert progress.status_code == 200
    assert progress.headers["content-disposition"].endswith('filename="danaleo_workspace.danaleo"')

    removed = client.delete(f"/api/datasets/{second_id}")
    assert removed.status_code == 200
    assert [dataset["id"] for dataset in removed.json()["datasets"]] == [first_id]

    client.post("/api/workspace/reset")
    restored = client.post(
        "/api/progress/load",
        files={"file": ("workspace.danaleo", progress.content, "application/zip")},
    )
    assert restored.status_code == 200
    assert len(restored.json()["datasets"]) == 2
    assert restored.json()["active_dataset_id"] == first_id

    invalid_activate = client.post("/api/datasets/activate", json={"dataset_id": "missing"})
    invalid_delete = client.delete("/api/datasets/missing")
    assert invalid_activate.status_code == 400
    assert invalid_delete.status_code == 400


def test_multi_csv_upload_is_atomic_when_any_file_is_invalid(csv_bytes: bytes):
    client = TestClient(app)
    existing = upload_csv(client, b"x\n1\n", "existing.csv")

    response = client.post(
        "/api/upload",
        files=[
            ("file", ("valid.csv", csv_bytes, "text/csv")),
            ("file", ("broken.csv", b'a,b\n1,"unterminated\n', "text/csv")),
        ],
    )

    assert response.status_code == 400
    workspace = client.get("/api/workspace").json()
    assert workspace["active_dataset_id"] == existing["active_dataset_id"]
    assert [dataset["csv_name"] for dataset in workspace["datasets"]] == ["existing.csv"]


def test_merge_api_preview_create_detail_and_error_paths():
    client = TestClient(app)
    left = upload_csv(client, b"id,a\n1,A\n2,B\n3,C\n", "left.csv")
    right = upload_csv(client, b"customer_id,b\n2,X\n3,Y\n4,Z\n", "right.csv")
    payload = {
        "left_session_id": left["active_session_id"],
        "right_session_id": right["active_session_id"],
        "how": "outer",
        "left_on": ["id"],
        "right_on": ["customer_id"],
        "suffixes": ["_left", "_right"],
        "validate": "one_to_one",
        "name": "customer_orders",
    }

    detail = client.get(f"/api/datasets/{left['active_dataset_id']}")
    assert detail.status_code == 200
    assert detail.json()["session_options"][0]["columns"] == ["id", "a"]

    preview = client.post("/api/merges/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["result_rows"] == 4
    assert preview.json()["matched_rows"] == 2

    created = client.post("/api/merges", json=payload)
    assert created.status_code == 200
    assert created.json()["csv_name"] == "customer_orders.csv"
    assert len(created.json()["datasets"]) == 3
    assert created.json()["datasets"][-1]["provenance"]["type"] == "merge"

    bad_detail = client.get("/api/datasets/missing")
    bad_merge = client.post("/api/merges/preview", json={**payload, "left_on": ["missing"]})
    assert bad_detail.status_code == 400
    assert bad_merge.status_code == 400
    assert "Left join key not found" in bad_merge.json()["detail"]


def test_api_end_to_end_workspace_flow(csv_bytes: bytes):
    client = TestClient(app)

    workspace = upload_csv(client, csv_bytes)
    base_id = workspace["active_session_id"]

    created = client.post("/api/sessions", json={"name": "Branch 1", "parent_id": base_id})
    assert created.status_code == 200
    branch_id = created.json()["active_session_id"]

    renamed = client.patch(f"/api/sessions/{branch_id}", json={"name": "Renamed Branch"})
    assert renamed.status_code == 200
    assert renamed.json()["active_session"]["name"] == "Renamed Branch"

    activated = client.post("/api/sessions/activate", json={"session_id": base_id})
    assert activated.status_code == 200
    assert activated.json()["active_session_id"] == base_id

    stats = client.get(f"/api/sessions/{base_id}/columns/age/stats")
    assert stats.status_code == 200
    assert stats.json()["kind"] == "numeric"

    operated = client.post(
        f"/api/sessions/{branch_id}/operations",
        json={"operation_type": "filter_rows", "params": {"query": "age > 30"}},
    )
    assert operated.status_code == 200

    branch = next(session for session in operated.json()["sessions"] if session["id"] == branch_id)
    assert branch["overview"]["rows"] == 5
    assert operated.json()["active_session_id"] == base_id

    preview = client.post(
        "/api/plots/preview",
        json={
            "session_id": branch_id,
            "column": "age",
            "plot_type": "histogram",
            "controls": {"bins": 4},
        },
    )
    assert preview.status_code == 200
    assert preview.json()["image"].startswith("data:image/png;base64,")

    saved = client.post(
        "/api/plots/save",
        json={
            "session_id": branch_id,
            "column": "age",
            "plot_type": "histogram",
            "controls": {"bins": 4},
            "include_in_export": True,
            "remark": "Looks good",
            "title": "Age preview",
        },
    )
    assert saved.status_code == 200

    plot = saved.json()["saved_plots"][0]
    assert plot["title"] == "Age preview"

    updated_plot = client.patch(
        f"/api/plots/{plot['id']}",
        json={"include_in_export": False, "remark": "Skip it"},
    )
    assert updated_plot.status_code == 200
    assert updated_plot.json()["saved_plots"][0]["include_in_export"] is False
    assert updated_plot.json()["saved_plots"][0]["remark"] == "Skip it"

    progress_response = client.get("/api/progress/download")
    assert progress_response.status_code == 200
    assert progress_response.headers["content-disposition"].endswith(
        'filename="customers.danaleo"'
    )

    reset = client.post("/api/workspace/reset")
    assert reset.status_code == 200
    assert reset.json()["ready"] is False

    restored = client.post(
        "/api/progress/load",
        files={
            "file": (
                "customers.danaleo",
                progress_response.content,
                "application/vnd.danaleo.project+zip",
            )
        },
    )
    assert restored.status_code == 200
    assert restored.json()["active_session_id"] == base_id
    assert restored.json()["saved_plots"][0]["title"] == "Age preview"

    deleted_plot = client.delete(f"/api/plots/{plot['id']}")
    assert deleted_plot.status_code == 200
    assert deleted_plot.json()["saved_plots"] == []

    export_response = client.get("/api/export/notebook")
    assert export_response.status_code == 200
    assert export_response.headers["content-disposition"].endswith(
        'filename="customers_eda.ipynb"'
    )
    assert b"Danaleo EDA Export" in export_response.content

    deleted = client.delete(f"/api/sessions/{branch_id}")
    assert deleted.status_code == 200
    assert len(deleted.json()["sessions"]) == 1
    assert deleted.json()["saved_plots"] == []


def test_api_returns_400_for_invalid_session_actions(csv_bytes: bytes):
    client = TestClient(app)
    upload_csv(client, csv_bytes)

    response = client.patch("/api/sessions/missing", json={"name": "Nope"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Session not found"

    base_id = store.active_session_id

    response = client.delete(f"/api/sessions/{base_id}")
    assert response.status_code == 400
    assert "Cannot delete the only session" in response.json()["detail"]

    response = client.get(f"/api/sessions/{base_id}/columns/missing/stats")
    assert response.status_code == 400
    assert "Unknown column" in response.json()["detail"]

    response = client.post("/api/sessions/activate", json={"session_id": "missing"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Session not found"

    response = client.post("/api/sessions", json={"name": "   ", "parent_id": base_id})
    assert response.status_code == 400
    assert "Session name is required" in response.json()["detail"]


def test_api_supports_encoded_column_names_and_drop_duplicates(edge_csv_bytes: bytes):
    client = TestClient(app)
    workspace = upload_csv(client, edge_csv_bytes, "edge.csv")
    base_id = workspace["active_session_id"]

    stats = client.get(f"/api/sessions/{base_id}/columns/Age%20Years/stats")
    assert stats.status_code == 200
    assert stats.json()["name"] == "Age Years"

    duplicate_upload = upload_csv(client, b"x,y\n1,A\n1,A\n2,B\n", "duplicates.csv")
    duplicate_id = duplicate_upload["active_session_id"]
    operated = client.post(
        f"/api/sessions/{duplicate_id}/operations",
        json={"operation_type": "drop_duplicates", "params": {}},
    )
    assert operated.status_code == 200
    assert operated.json()["active_session"]["overview"]["rows"] == 2


def test_api_applies_imputation_operation():
    client = TestClient(app)
    workspace = upload_csv(client, b"value,label\n1,A\n,B\n3,\n", "missing.csv")

    response = client.post(
        f"/api/sessions/{workspace['active_session_id']}/operations",
        json={"operation_type": "impute_missing", "params": {"column": "value", "method": "median"}},
    )

    assert response.status_code == 200
    assert response.json()["active_session"]["operations"][-1]["label"] == "Impute value: Median"
    assert response.json()["active_session"]["profile"]["missing_cells"] == 1


def test_api_operation_and_plot_error_edges(csv_bytes: bytes):
    client = TestClient(app)
    workspace = upload_csv(client, csv_bytes)
    base_id = workspace["active_session_id"]

    bad_operation = client.post(
        f"/api/sessions/{base_id}/operations",
        json={"operation_type": "filter_rows", "params": {"query": "   "}},
    )
    assert bad_operation.status_code == 400
    assert "Filter query cannot be empty" in bad_operation.json()["detail"]

    empty_preview = client.post(
        "/api/plots/preview",
        json={
            "session_id": base_id,
            "column": "age",
            "plot_type": "histogram",
            "local_query": "age > 999",
            "controls": {"bins": 4},
        },
    )
    assert empty_preview.status_code == 400
    assert "returned no rows" in empty_preview.json()["detail"]

    missing_plot_update = client.patch(
        "/api/plots/missing",
        json={"include_in_export": True, "remark": "No plot"},
    )
    assert missing_plot_update.status_code == 400
    assert "Plot not found" in missing_plot_update.json()["detail"]

    missing_plot_delete = client.delete("/api/plots/missing")
    assert missing_plot_delete.status_code == 400
    assert "Plot not found" in missing_plot_delete.json()["detail"]

    bad_progress = client.post(
        "/api/progress/load",
        files={"file": ("not_progress.csv", csv_bytes, "text/csv")},
    )
    assert bad_progress.status_code == 400
    assert ".danaleo" in bad_progress.json()["detail"]

    corrupt_progress = client.post(
        "/api/progress/load",
        files={"file": ("corrupt.danaleo", b"not a zip", "application/zip")},
    )
    assert corrupt_progress.status_code == 400

    bad_plot_type = client.post(
        "/api/plots/preview",
        json={"session_id": base_id, "column": "age", "plot_type": "unknown"},
    )
    assert bad_plot_type.status_code == 400
    assert "Unsupported plot type" in bad_plot_type.json()["detail"]

    missing_required_plot_field = client.post(
        "/api/plots/preview",
        json={"session_id": base_id, "column": "age"},
    )
    assert missing_required_plot_field.status_code == 422


def test_frontend_assets_are_served_without_browser_cache():
    client = TestClient(app)

    response = client.get(
        "/",
        headers={
            "If-None-Match": "cached",
            "If-Modified-Since": "Wed, 21 Oct 2015 07:28:00 GMT",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0, must-revalidate"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
