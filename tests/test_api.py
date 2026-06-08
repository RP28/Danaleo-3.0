from __future__ import annotations

from fastapi.testclient import TestClient

from danaleo.core.session_store import store
from danaleo.server.app import app


def test_api_end_to_end_workspace_flow(csv_bytes: bytes):
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/workspace").json()["ready"] is False

    bad_upload = client.post("/api/upload", files={"file": ("bad.txt", b"not,csv")})
    assert bad_upload.status_code == 400

    uploaded = client.post("/api/upload", files={"file": ("customers.csv", csv_bytes, "text/csv")})
    assert uploaded.status_code == 200
    workspace = uploaded.json()
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

    operated = client.post(f"/api/sessions/{branch_id}/operations", json={"operation_type": "filter_rows", "params": {"query": "age > 30"}})
    assert operated.status_code == 200
    branch = next(session for session in operated.json()["sessions"] if session["id"] == branch_id)
    assert branch["overview"]["rows"] == 5
    assert operated.json()["active_session_id"] == base_id

    preview = client.post(
        "/api/plots/preview",
        json={"session_id": branch_id, "column": "age", "plot_type": "histogram", "controls": {"bins": 4}},
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

    updated_plot = client.patch(f"/api/plots/{plot['id']}", json={"include_in_export": False, "remark": "Skip it"})
    assert updated_plot.status_code == 200
    assert updated_plot.json()["saved_plots"][0]["include_in_export"] is False
    assert updated_plot.json()["saved_plots"][0]["remark"] == "Skip it"

    export_response = client.get("/api/export/notebook")
    assert export_response.status_code == 200
    assert export_response.headers["content-disposition"].endswith('filename="customers_eda.ipynb"')
    assert b"Danaleo EDA Export" in export_response.content

    deleted = client.delete(f"/api/sessions/{branch_id}")
    assert deleted.status_code == 200
    assert len(deleted.json()["sessions"]) == 1
    assert deleted.json()["saved_plots"] == []


def test_api_returns_400_for_invalid_session_actions(csv_bytes: bytes):
    client = TestClient(app)
    client.post("/api/upload", files={"file": ("customers.csv", csv_bytes, "text/csv")})

    response = client.patch("/api/sessions/missing", json={"name": "Nope"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Session not found"

    base_id = store.active_session_id
    response = client.delete(f"/api/sessions/{base_id}")
    assert response.status_code == 400
    assert "Cannot delete the only session" in response.json()["detail"]


def test_frontend_assets_are_served_without_browser_cache():
    client = TestClient(app)

    response = client.get("/", headers={"If-None-Match": "cached", "If-Modified-Since": "Wed, 21 Oct 2015 07:28:00 GMT"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0, must-revalidate"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
