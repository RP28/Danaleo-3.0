from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from danaleo.core.exporter import export_notebook
from danaleo.core.session_store import store
from danaleo.core.stats import column_stats
from danaleo.server.models import (
    ActivateSessionRequest,
    CreateSessionRequest,
    OperationRequest,
    PlotRequest,
    RenameSessionRequest,
    SavePlotRequest,
    UpdatePlotRequest,
)

app = FastAPI(title="Danaleo", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prevent_frontend_cache(request, call_next):
    """Always serve the local frontend fresh.

    While iterating on packaged builds, browsers can keep an older React bundle and
    FastAPI's StaticFiles may answer with 304 Not Modified. Removing conditional
    cache headers for frontend files makes each reload fetch the current bundle.
    """
    frontend_path = request.url.path == "/" or request.url.path.startswith("/assets/")
    if frontend_path:
        request.scope["headers"] = [
            (name, value)
            for name, value in request.scope["headers"]
            if name.lower() not in {b"if-none-match", b"if-modified-since"}
        ]

    response = await call_next(request)

    if frontend_path:
        response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/workspace")
def workspace() -> dict:
    return store.workspace_summary()


@app.post("/api/upload")
async def upload_csv(
    file: UploadFile = File(...),
    sample_mode: str = Form("none"),
    sample_n: int | None = Form(None),
    sample_frac: float | None = Form(None),
    random_state: int = Form(42),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    try:
        content = await file.read()
        return store.load_csv(content, file.filename, sample_mode, sample_n, sample_frac, random_state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sessions")
def create_session(payload: CreateSessionRequest) -> dict:
    try:
        return store.create_session(payload.name, payload.parent_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sessions/activate")
def activate_session(payload: ActivateSessionRequest) -> dict:
    try:
        return store.set_active_session(payload.session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, payload: RenameSessionRequest) -> dict:
    try:
        return store.rename_session(session_id, payload.name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    try:
        return store.delete_session(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/operations")
def apply_operation(session_id: str, payload: OperationRequest) -> dict:
    try:
        return store.apply_session_operation(session_id, payload.operation_type, payload.params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}/columns/{column}/stats")
def stats(session_id: str, column: str) -> dict:
    try:
        session = store.require_session(session_id)
        return column_stats(session.data, column)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/plots/preview")
def preview_plot(payload: PlotRequest) -> dict:
    try:
        return store.preview_plot(
            payload.session_id,
            payload.column,
            payload.plot_type,
            payload.local_query,
            payload.controls,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/plots/save")
def save_plot(payload: SavePlotRequest) -> dict:
    try:
        return store.save_plot(
            payload.session_id,
            payload.column,
            payload.plot_type,
            payload.local_query,
            payload.controls,
            payload.include_in_export,
            payload.remark,
            payload.title,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/plots/{plot_id}")
def update_plot(plot_id: str, payload: UpdatePlotRequest) -> dict:
    try:
        return store.update_plot(plot_id, payload.include_in_export, payload.remark)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/export/notebook")
def export() -> Response:
    try:
        data = export_notebook(store)
        filename = (store.csv_name or "danaleo_export.csv").rsplit(".", 1)[0] + "_eda.ipynb"
        return Response(
            data,
            media_type="application/x-ipynb+json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


STATIC_DIR = Path(__file__).parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

if INDEX_FILE.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    @app.get("/", response_class=HTMLResponse)
    def frontend_missing() -> str:
        return """
        <html><body style='font-family: system-ui; padding: 3rem; background: #0b0e14; color: #f6f7fb'>
        <h1>Danaleo backend is running</h1>
        <p>The React frontend has not been built yet.</p>
        <pre>cd frontend\nnpm install\nnpm run build\ncd ..\ndanaleo</pre>
        </body></html>
        """
