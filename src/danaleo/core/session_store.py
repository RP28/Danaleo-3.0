from __future__ import annotations

import json
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from danaleo.core.operations import apply_operation, operation_label
from danaleo.core.plots import build_figure
from danaleo.core.stats import column_cards, dataframe_overview


@dataclass
class OperationRecord:
    id: str
    operation_type: str
    label: str
    params: dict[str, Any]
    time: int


@dataclass
class SessionRecord:
    id: str
    name: str
    parent_id: str | None
    created_time: int
    created_overview: dict[str, Any] = field(default_factory=dict)
    source_operation_id: str | None = None
    operations: list[OperationRecord] = field(default_factory=list)
    data: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class PlotRecord:
    id: str
    session_id: str
    session_name: str
    column: str
    plot_type: str
    local_query: str
    controls: dict[str, Any]
    figure: dict[str, Any]
    include_in_export: bool
    remark: str
    created_time: int
    title: str


class WorkspaceStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.csv_path: str | None = None
        self.csv_name: str | None = None
        self.time_counter = 0
        self.active_session_id: str | None = None
        self.sessions: dict[str, SessionRecord] = {}
        self.saved_plots: dict[str, PlotRecord] = {}
        self.sample_info: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return bool(self.sessions and self.active_session_id)

    def _tick(self) -> int:
        self.time_counter += 1
        return self.time_counter

    def _read_csv_with_sampling(
        self,
        csv_path: str,
        sample_mode: str = "none",
        sample_n: int | None = None,
        sample_frac: float | None = None,
        random_state: int = 42,
    ) -> tuple[pd.DataFrame, dict[str, Any] | None]:
        df = pd.read_csv(csv_path)
        sample_info: dict[str, Any] | None = None
        original_rows = len(df)
        if sample_mode == "n" and sample_n and sample_n > 0 and sample_n < len(df):
            df = df.sample(n=int(sample_n), random_state=random_state).reset_index(drop=True)
            sample_info = {
                "mode": "n",
                "sample_n": int(sample_n),
                "random_state": random_state,
                "original_rows": int(original_rows),
            }
        elif sample_mode == "frac" and sample_frac and 0 < sample_frac < 1:
            df = df.sample(frac=float(sample_frac), random_state=random_state).reset_index(drop=True)
            sample_info = {
                "mode": "frac",
                "sample_frac": float(sample_frac),
                "random_state": random_state,
                "original_rows": int(original_rows),
            }
        return df, sample_info

    def load_csv(
        self,
        file_bytes: bytes,
        filename: str,
        sample_mode: str = "none",
        sample_n: int | None = None,
        sample_frac: float | None = None,
        random_state: int = 42,
    ) -> dict[str, Any]:
        suffix = Path(filename).suffix or ".csv"
        with NamedTemporaryFile(delete=False, suffix=suffix, prefix="danaleo_") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        df, sample_info = self._read_csv_with_sampling(
            tmp_path,
            sample_mode,
            sample_n,
            sample_frac,
            random_state,
        )

        self.reset()
        self.csv_path = tmp_path
        self.csv_name = filename
        self.sample_info = sample_info
        base_id = uuid4().hex
        created_time = self._tick()
        self.sessions[base_id] = SessionRecord(
            id=base_id,
            name="Base Session",
            parent_id=None,
            created_time=created_time,
            created_overview=dataframe_overview(df),
            source_operation_id=None,
            operations=[
                OperationRecord(
                    id=uuid4().hex,
                    operation_type="created_session",
                    label="Created Base Session",
                    params={},
                    time=created_time,
                )
            ],
            data=df,
        )
        self.active_session_id = base_id
        return self.workspace_summary()

    def require_session(self, session_id: str | None = None) -> SessionRecord:
        if not self.ready:
            raise ValueError("Upload a CSV file first")
        sid = session_id or self.active_session_id
        if not sid or sid not in self.sessions:
            raise ValueError("Session not found")
        return self.sessions[sid]

    def create_session(self, name: str, parent_id: str | None = None) -> dict[str, Any]:
        parent = self.require_session(parent_id)
        if not name.strip():
            raise ValueError("Session name is required")
        parent_operations = [op for op in parent.operations if op.operation_type != "created_session"]
        source_operation_id = parent_operations[-1].id if parent_operations else None
        sid = uuid4().hex
        created_time = self._tick()
        self.sessions[sid] = SessionRecord(
            id=sid,
            name=name.strip(),
            parent_id=parent.id,
            created_time=created_time,
            created_overview=dataframe_overview(parent.data),
            source_operation_id=source_operation_id,
            operations=[
                OperationRecord(
                    id=uuid4().hex,
                    operation_type="created_session",
                    label=f"Created {name.strip()}",
                    params={},
                    time=created_time,
                )
            ],
            data=parent.data.copy(),
        )
        self.active_session_id = sid
        return self.workspace_summary()

    def set_active_session(self, session_id: str) -> dict[str, Any]:
        self.require_session(session_id)
        self.active_session_id = session_id
        return self.workspace_summary()



    def rename_session(self, session_id: str, name: str) -> dict[str, Any]:
        session = self.require_session(session_id)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Session name is required")
        old_name = session.name
        session.name = clean_name

        # Keep saved plot metadata in sync so plot cards and notebook export
        # continue to show the latest session name.
        for plot in self.saved_plots.values():
            if plot.session_id == session.id and plot.session_name == old_name:
                plot.session_name = clean_name

        return self.workspace_summary()

    def delete_session(self, session_id: str) -> dict[str, Any]:
        self.require_session(session_id)
        if len(self.sessions) == 1:
            raise ValueError("Cannot delete the only session")

        child_map: dict[str, list[str]] = {}
        for session in self.sessions.values():
            if session.parent_id:
                child_map.setdefault(session.parent_id, []).append(session.id)

        ids_to_delete: set[str] = set()
        stack = [session_id]
        while stack:
            current_id = stack.pop()
            if current_id in ids_to_delete:
                continue
            ids_to_delete.add(current_id)
            stack.extend(child_map.get(current_id, []))

        if len(ids_to_delete) >= len(self.sessions):
            raise ValueError("Cannot delete every session. Create another session first.")

        deleted_session = self.sessions[session_id]
        for sid in ids_to_delete:
            self.sessions.pop(sid, None)

        self.saved_plots = {
            plot_id: plot
            for plot_id, plot in self.saved_plots.items()
            if plot.session_id not in ids_to_delete
        }

        if self.active_session_id in ids_to_delete:
            fallback_id = deleted_session.parent_id if deleted_session.parent_id in self.sessions else None
            if not fallback_id:
                fallback_id = sorted(self.sessions.values(), key=lambda x: x.created_time)[0].id
            self.active_session_id = fallback_id

        return self.workspace_summary()

    def apply_session_operation(self, session_id: str, operation_type: str, params: dict[str, Any]) -> dict[str, Any]:
        session = self.require_session(session_id)
        new_df = apply_operation(session.data, operation_type, params)
        event_time = self._tick()
        session.data = new_df
        session.operations.append(
            OperationRecord(
                id=uuid4().hex,
                operation_type=operation_type,
                label=operation_label(operation_type, params),
                params=params,
                time=event_time,
            )
        )
        return self.workspace_summary()

    def preview_plot(
        self,
        session_id: str,
        column: str,
        plot_type: str,
        local_query: str = "",
        controls: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.require_session(session_id)
        return build_figure(session.data, column, plot_type, local_query, controls or {})

    def save_plot(
        self,
        session_id: str,
        column: str,
        plot_type: str,
        local_query: str = "",
        controls: dict[str, Any] | None = None,
        include_in_export: bool = True,
        remark: str = "",
        title: str | None = None,
    ) -> dict[str, Any]:
        session = self.require_session(session_id)
        figure = build_figure(session.data, column, plot_type, local_query, controls or {})
        pid = uuid4().hex
        self.saved_plots[pid] = PlotRecord(
            id=pid,
            session_id=session.id,
            session_name=session.name,
            column=column,
            plot_type=plot_type,
            local_query=local_query,
            controls=controls or {},
            figure=figure,
            include_in_export=include_in_export,
            remark=remark,
            created_time=self._tick(),
            title=title or f"{plot_type.replace('_', ' ').title()} — {column}",
        )
        return self.workspace_summary()

    def update_plot(self, plot_id: str, include_in_export: bool | None = None, remark: str | None = None) -> dict[str, Any]:
        if plot_id not in self.saved_plots:
            raise ValueError("Plot not found")
        plot = self.saved_plots[plot_id]
        if include_in_export is not None:
            plot.include_in_export = include_in_export
        if remark is not None:
            plot.remark = remark
        return self.workspace_summary()

    def delete_plot(self, plot_id: str) -> dict[str, Any]:
        if plot_id not in self.saved_plots:
            raise ValueError("Plot not found")
        self.saved_plots.pop(plot_id)
        return self.workspace_summary()

    def _project_manifest(self) -> dict[str, Any]:
        if not self.ready:
            raise ValueError("Upload a CSV file first")
        return {
            "format": "danaleo.project",
            "version": 1,
            "csv_name": self.csv_name,
            "sample_info": self.sample_info,
            "active_session_id": self.active_session_id,
            "time_counter": self.time_counter,
            "sessions": [
                {
                    "id": session.id,
                    "name": session.name,
                    "parent_id": session.parent_id,
                    "created_time": session.created_time,
                    "created_overview": session.created_overview,
                    "source_operation_id": session.source_operation_id,
                    "operations": [op.__dict__ for op in session.operations],
                }
                for session in sorted(self.sessions.values(), key=lambda item: item.created_time)
            ],
            "saved_plots": [
                {
                    "id": plot.id,
                    "session_id": plot.session_id,
                    "session_name": plot.session_name,
                    "column": plot.column,
                    "plot_type": plot.plot_type,
                    "local_query": plot.local_query,
                    "controls": plot.controls,
                    "include_in_export": plot.include_in_export,
                    "remark": plot.remark,
                    "created_time": plot.created_time,
                    "title": plot.title,
                }
                for plot in sorted(self.saved_plots.values(), key=lambda item: item.created_time)
            ],
        }

    def export_project(self) -> bytes:
        if not self.ready:
            raise ValueError("Upload a CSV file first")
        if not self.csv_path or not Path(self.csv_path).exists():
            raise ValueError("Source CSV is no longer available")

        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(self._project_manifest(), indent=2))
            archive.write(self.csv_path, "source.csv")
        return buffer.getvalue()

    def import_project(self, project_bytes: bytes) -> dict[str, Any]:
        with ZipFile(BytesIO(project_bytes)) as archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                source_bytes = archive.read("source.csv")
            except KeyError as exc:
                raise ValueError("Saved progress file is missing required project data") from exc

        if manifest.get("format") != "danaleo.project" or manifest.get("version") != 1:
            raise ValueError("Unsupported saved progress file")

        csv_name = str(manifest.get("csv_name") or "source.csv")
        suffix = Path(csv_name).suffix or ".csv"
        with NamedTemporaryFile(delete=False, suffix=suffix, prefix="danaleo_") as tmp:
            tmp.write(source_bytes)
            tmp_path = tmp.name

        sample_info = manifest.get("sample_info")
        if sample_info:
            mode = sample_info.get("mode", "none")
            df, restored_sample_info = self._read_csv_with_sampling(
                tmp_path,
                mode,
                sample_info.get("sample_n"),
                sample_info.get("sample_frac"),
                sample_info.get("random_state", 42),
            )
            if restored_sample_info:
                restored_sample_info["original_rows"] = sample_info.get(
                    "original_rows",
                    restored_sample_info["original_rows"],
                )
        else:
            df, restored_sample_info = self._read_csv_with_sampling(tmp_path)

        raw_sessions = manifest.get("sessions") or []
        if not raw_sessions:
            raise ValueError("Saved progress file does not contain any sessions")

        records: dict[str, SessionRecord] = {}
        for raw in raw_sessions:
            operations = [
                OperationRecord(
                    id=str(op["id"]),
                    operation_type=str(op["operation_type"]),
                    label=str(op["label"]),
                    params=dict(op.get("params") or {}),
                    time=int(op["time"]),
                )
                for op in raw.get("operations", [])
            ]
            record = SessionRecord(
                id=str(raw["id"]),
                name=str(raw["name"]),
                parent_id=raw.get("parent_id"),
                created_time=int(raw["created_time"]),
                created_overview=dict(raw.get("created_overview") or {}),
                source_operation_id=raw.get("source_operation_id"),
                operations=operations,
                data=pd.DataFrame(),
            )
            records[record.id] = record

        materialized: dict[tuple[str, str | None], pd.DataFrame] = {}

        def build_session_data(session_id: str, stop_operation_id: str | None = None) -> pd.DataFrame:
            cache_key = (session_id, stop_operation_id)
            if cache_key in materialized:
                return materialized[cache_key].copy()

            if session_id not in records:
                raise ValueError("Saved progress file references a missing session")

            session = records[session_id]
            if session.parent_id is None:
                current = df.copy()
            else:
                current = build_session_data(session.parent_id, session.source_operation_id)

            found_stop = stop_operation_id is None
            for operation in session.operations:
                if operation.operation_type == "created_session":
                    if operation.id == stop_operation_id:
                        found_stop = True
                        break
                    continue
                current = apply_operation(current, operation.operation_type, operation.params)
                if operation.id == stop_operation_id:
                    found_stop = True
                    break

            if not found_stop:
                raise ValueError("Saved progress file references a missing operation")

            materialized[cache_key] = current.copy()
            return current

        for record in sorted(records.values(), key=lambda item: item.created_time):
            record.data = build_session_data(record.id)

        plots: dict[str, PlotRecord] = {}
        for raw in manifest.get("saved_plots") or []:
            session_id = str(raw["session_id"])
            if session_id not in records:
                continue
            controls = dict(raw.get("controls") or {})
            figure = build_figure(
                records[session_id].data,
                str(raw["column"]),
                str(raw["plot_type"]),
                str(raw.get("local_query") or ""),
                controls,
            )
            plot = PlotRecord(
                id=str(raw["id"]),
                session_id=session_id,
                session_name=str(raw.get("session_name") or records[session_id].name),
                column=str(raw["column"]),
                plot_type=str(raw["plot_type"]),
                local_query=str(raw.get("local_query") or ""),
                controls=controls,
                figure=figure,
                include_in_export=bool(raw.get("include_in_export", True)),
                remark=str(raw.get("remark") or ""),
                created_time=int(raw["created_time"]),
                title=str(raw.get("title") or f"{raw['plot_type']} - {raw['column']}"),
            )
            plots[plot.id] = plot

        active_session_id = manifest.get("active_session_id")
        if active_session_id not in records:
            active_session_id = sorted(records.values(), key=lambda item: item.created_time)[0].id

        max_time = max(
            [int(manifest.get("time_counter") or 0)]
            + [session.created_time for session in records.values()]
            + [op.time for session in records.values() for op in session.operations]
            + [plot.created_time for plot in plots.values()]
        )

        self.reset()
        self.csv_path = tmp_path
        self.csv_name = csv_name
        self.sample_info = restored_sample_info
        self.sessions = records
        self.saved_plots = plots
        self.active_session_id = str(active_session_id)
        self.time_counter = max_time
        return self.workspace_summary()

    def session_summary(self, session: SessionRecord) -> dict[str, Any]:
        return {
            "id": session.id,
            "name": session.name,
            "parent_id": session.parent_id,
            "created_time": session.created_time,
            "created_overview": session.created_overview or dataframe_overview(session.data),
            "source_operation_id": session.source_operation_id,
            "overview": dataframe_overview(session.data),
            "columns": column_cards(session.data),
            "operations": [op.__dict__ for op in session.operations],
        }

    def workspace_summary(self) -> dict[str, Any]:
        active = self.require_session(self.active_session_id) if self.ready else None
        return {
            "ready": self.ready,
            "csv_name": self.csv_name,
            "csv_path": self.csv_path,
            "sample_info": self.sample_info,
            "active_session_id": self.active_session_id,
            "active_session": self.session_summary(active) if active else None,
            "sessions": [self.session_summary(s) for s in sorted(self.sessions.values(), key=lambda x: x.created_time)],
            "saved_plots": [p.__dict__ for p in sorted(self.saved_plots.values(), key=lambda x: x.created_time)],
        }


store = WorkspaceStore()
