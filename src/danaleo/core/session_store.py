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
from danaleo.core.stats import column_cards, dataframe_overview, dataset_profile


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


@dataclass
class DatasetRecord:
    id: str
    csv_path: str
    csv_name: str
    sample_info: dict[str, Any] | None
    active_session_id: str
    sessions: dict[str, SessionRecord] = field(default_factory=dict)
    saved_plots: dict[str, PlotRecord] = field(default_factory=dict)
    provenance: dict[str, Any] | None = None


class WorkspaceStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        for dataset in getattr(self, "datasets", {}).values():
            Path(dataset.csv_path).unlink(missing_ok=True)
        self.time_counter = 0
        self.active_dataset_id: str | None = None
        self.datasets: dict[str, DatasetRecord] = {}

    @property
    def active_dataset(self) -> DatasetRecord | None:
        if not self.active_dataset_id:
            return None
        return self.datasets.get(self.active_dataset_id)

    @property
    def csv_path(self) -> str | None:
        return self.active_dataset.csv_path if self.active_dataset else None

    @property
    def csv_name(self) -> str | None:
        return self.active_dataset.csv_name if self.active_dataset else None

    @property
    def sample_info(self) -> dict[str, Any] | None:
        return self.active_dataset.sample_info if self.active_dataset else None

    @property
    def active_session_id(self) -> str | None:
        return self.active_dataset.active_session_id if self.active_dataset else None

    @active_session_id.setter
    def active_session_id(self, value: str) -> None:
        if not self.active_dataset:
            raise ValueError("Upload a CSV file first")
        self.active_dataset.active_session_id = value

    @property
    def sessions(self) -> dict[str, SessionRecord]:
        return self.active_dataset.sessions if self.active_dataset else {}

    @property
    def saved_plots(self) -> dict[str, PlotRecord]:
        return self.active_dataset.saved_plots if self.active_dataset else {}

    @saved_plots.setter
    def saved_plots(self, value: dict[str, PlotRecord]) -> None:
        if not self.active_dataset:
            raise ValueError("Upload a CSV file first")
        self.active_dataset.saved_plots = value

    @property
    def ready(self) -> bool:
        return bool(self.datasets and self.active_dataset)

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
        return self._register_dataset(df, tmp_path, filename, sample_info)

    def _register_dataset(
        self,
        df: pd.DataFrame,
        csv_path: str,
        filename: str,
        sample_info: dict[str, Any] | None = None,
        session_name: str = "Base Session",
        creation_label: str = "Created Base Session",
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dataset_id = uuid4().hex
        base_id = uuid4().hex
        created_time = self._tick()
        base_session = SessionRecord(
            id=base_id,
            name=session_name,
            parent_id=None,
            created_time=created_time,
            created_overview=dataframe_overview(df),
            source_operation_id=None,
            operations=[
                OperationRecord(
                    id=uuid4().hex,
                    operation_type="created_session",
                    label=creation_label,
                    params={},
                    time=created_time,
                )
            ],
            data=df,
        )
        self.datasets[dataset_id] = DatasetRecord(
            id=dataset_id,
            csv_path=csv_path,
            csv_name=filename,
            sample_info=sample_info,
            active_session_id=base_id,
            sessions={base_id: base_session},
            provenance=provenance,
        )
        self.active_dataset_id = dataset_id
        return self.workspace_summary()

    def set_active_dataset(self, dataset_id: str) -> dict[str, Any]:
        if dataset_id not in self.datasets:
            raise ValueError("Dataset not found")
        self.active_dataset_id = dataset_id
        return self.workspace_summary()

    def delete_dataset(self, dataset_id: str) -> dict[str, Any]:
        if dataset_id not in self.datasets:
            raise ValueError("Dataset not found")
        deleted = self.datasets.pop(dataset_id)
        Path(deleted.csv_path).unlink(missing_ok=True)
        if not self.datasets:
            self.active_dataset_id = None
        elif self.active_dataset_id == dataset_id:
            self.active_dataset_id = next(iter(self.datasets))
        return self.workspace_summary()

    def load_csv_batch(
        self,
        files: list[tuple[bytes, str]],
        sample_mode: str = "none",
        sample_n: int | None = None,
        sample_frac: float | None = None,
        random_state: int = 42,
    ) -> dict[str, Any]:
        if not files:
            raise ValueError("Choose at least one CSV file")

        previous_ids = set(self.datasets)
        previous_active_dataset_id = self.active_dataset_id
        previous_time = self.time_counter
        try:
            for file_bytes, filename in files:
                self.load_csv(
                    file_bytes,
                    filename,
                    sample_mode,
                    sample_n,
                    sample_frac,
                    random_state,
                )
        except Exception:
            for dataset_id, dataset in self.datasets.items():
                if dataset_id not in previous_ids:
                    Path(dataset.csv_path).unlink(missing_ok=True)
            self.datasets = {
                dataset_id: dataset
                for dataset_id, dataset in self.datasets.items()
                if dataset_id in previous_ids
            }
            self.active_dataset_id = previous_active_dataset_id
            self.time_counter = previous_time
            raise
        return self.workspace_summary()

    def _activate_dataset_for_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            return
        for dataset in self.datasets.values():
            if session_id in dataset.sessions:
                self.active_dataset_id = dataset.id
                return

    def _find_session(self, session_id: str) -> tuple[DatasetRecord, SessionRecord]:
        for dataset in self.datasets.values():
            if session_id in dataset.sessions:
                return dataset, dataset.sessions[session_id]
        raise ValueError("Session not found")

    def require_session(self, session_id: str | None = None) -> SessionRecord:
        if not self.ready:
            raise ValueError("Upload a CSV file first")
        sid = session_id or self.active_session_id
        if sid:
            self._activate_dataset_for_session(sid)
        if not sid or sid not in self.sessions:
            raise ValueError("Session not found")
        return self.sessions[sid]

    def dataset_detail(self, dataset_id: str) -> dict[str, Any]:
        if dataset_id not in self.datasets:
            raise ValueError("Dataset not found")
        dataset = self.datasets[dataset_id]
        return {
            **self.dataset_summary(dataset),
            "session_options": [
                {
                    "id": session.id,
                    "name": session.name,
                    "rows": len(session.data),
                    "columns": [str(column) for column in session.data.columns],
                }
                for session in sorted(dataset.sessions.values(), key=lambda item: item.created_time)
            ],
        }

    def _merge_frames(
        self,
        left_session_id: str,
        right_session_id: str,
        how: str,
        left_on: list[str],
        right_on: list[str],
        suffixes: list[str],
        validate: str | None,
    ) -> tuple[pd.DataFrame, dict[str, Any], DatasetRecord, DatasetRecord]:
        if left_session_id == right_session_id:
            raise ValueError("Choose two different sessions to merge")
        left_dataset, left_session = self._find_session(left_session_id)
        right_dataset, right_session = self._find_session(right_session_id)
        allowed_how = {"inner", "left", "right", "outer", "cross"}
        if how not in allowed_how:
            raise ValueError(f"Unsupported join type: {how}")

        if how == "cross":
            left_keys: list[str] = []
            right_keys: list[str] = []
        else:
            left_keys = [str(column) for column in left_on if str(column)]
            right_keys = [str(column) for column in right_on if str(column)]
            if not left_keys or not right_keys:
                raise ValueError("Select at least one join key for each dataset")
            if len(left_keys) != len(right_keys):
                raise ValueError("Left and right join keys must have the same count")
            if len(set(left_keys)) != len(left_keys) or len(set(right_keys)) != len(right_keys):
                raise ValueError("Each join key column can only be selected once")
            missing_left = [column for column in left_keys if column not in left_session.data.columns]
            missing_right = [column for column in right_keys if column not in right_session.data.columns]
            if missing_left:
                raise ValueError(f"Left join key not found: {missing_left[0]}")
            if missing_right:
                raise ValueError(f"Right join key not found: {missing_right[0]}")

        clean_suffixes = [str(value) for value in suffixes]
        if len(clean_suffixes) != 2 or clean_suffixes[0] == clean_suffixes[1]:
            raise ValueError("Provide two different column suffixes")
        allowed_validate = {None, "one_to_one", "one_to_many", "many_to_one", "many_to_many"}
        if validate not in allowed_validate:
            raise ValueError(f"Unsupported relationship validation: {validate}")

        indicator = "__danaleo_merge_status__"
        while indicator in left_session.data.columns or indicator in right_session.data.columns:
            indicator = f"_{indicator}"
        merge_args: dict[str, Any] = {
            "how": how,
            "suffixes": tuple(clean_suffixes),
            "indicator": indicator,
        }
        if validate:
            merge_args["validate"] = validate
        if how != "cross":
            merge_args["left_on"] = left_keys
            merge_args["right_on"] = right_keys

        result = pd.merge(left_session.data, right_session.data, **merge_args)
        counts = result[indicator].value_counts().to_dict()
        result = result.drop(columns=[indicator])
        diagnostics = {
            "left_rows": len(left_session.data),
            "right_rows": len(right_session.data),
            "result_rows": len(result),
            "result_columns": len(result.columns),
            "matched_rows": int(counts.get("both", 0)),
            "left_only_rows": int(counts.get("left_only", 0)),
            "right_only_rows": int(counts.get("right_only", 0)),
            "columns": [str(column) for column in result.columns],
            "preview": dataset_profile(result, preview_rows=8)["preview"],
        }
        return result, diagnostics, left_dataset, right_dataset

    def preview_merge(
        self,
        left_session_id: str,
        right_session_id: str,
        how: str,
        left_on: list[str],
        right_on: list[str],
        suffixes: list[str],
        validate: str | None = None,
    ) -> dict[str, Any]:
        _, diagnostics, _, _ = self._merge_frames(
            left_session_id,
            right_session_id,
            how,
            left_on,
            right_on,
            suffixes,
            validate,
        )
        return diagnostics

    def create_merged_dataset(
        self,
        left_session_id: str,
        right_session_id: str,
        how: str,
        left_on: list[str],
        right_on: list[str],
        suffixes: list[str],
        validate: str | None = None,
        name: str = "merged.csv",
    ) -> dict[str, Any]:
        result, diagnostics, left_dataset, right_dataset = self._merge_frames(
            left_session_id,
            right_session_id,
            how,
            left_on,
            right_on,
            suffixes,
            validate,
        )
        clean_name = Path(name.strip() or "merged.csv").name
        if not clean_name.lower().endswith(".csv"):
            clean_name += ".csv"
        with NamedTemporaryFile(delete=False, suffix=".csv", prefix="danaleo_merge_") as tmp:
            result.to_csv(tmp.name, index=False)
            tmp_path = tmp.name

        provenance = {
            "type": "merge",
            "how": how,
            "left_dataset_id": left_dataset.id,
            "left_dataset_name": left_dataset.csv_name,
            "left_session_id": left_session_id,
            "left_session_name": left_dataset.sessions[left_session_id].name,
            "right_dataset_id": right_dataset.id,
            "right_dataset_name": right_dataset.csv_name,
            "right_session_id": right_session_id,
            "right_session_name": right_dataset.sessions[right_session_id].name,
            "left_on": left_on if how != "cross" else [],
            "right_on": right_on if how != "cross" else [],
            "suffixes": suffixes,
            "validate": validate,
            "diagnostics": {key: value for key, value in diagnostics.items() if key not in {"preview", "columns"}},
        }
        return self._register_dataset(
            result,
            tmp_path,
            clean_name,
            session_name="Merged result",
            creation_label=f"Created {how} join result",
            provenance=provenance,
        )

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
        self._activate_dataset_for_plot(plot_id)
        if plot_id not in self.saved_plots:
            raise ValueError("Plot not found")
        plot = self.saved_plots[plot_id]
        if include_in_export is not None:
            plot.include_in_export = include_in_export
        if remark is not None:
            plot.remark = remark
        return self.workspace_summary()

    def delete_plot(self, plot_id: str) -> dict[str, Any]:
        self._activate_dataset_for_plot(plot_id)
        if plot_id not in self.saved_plots:
            raise ValueError("Plot not found")
        self.saved_plots.pop(plot_id)
        return self.workspace_summary()

    def _activate_dataset_for_plot(self, plot_id: str) -> None:
        if plot_id in self.saved_plots:
            return
        for dataset in self.datasets.values():
            if plot_id in dataset.saved_plots:
                self.active_dataset_id = dataset.id
                return

    def _dataset_manifest(self, dataset: DatasetRecord) -> dict[str, Any]:
        return {
            "id": dataset.id,
            "csv_name": dataset.csv_name,
            "sample_info": dataset.sample_info,
            "provenance": dataset.provenance,
            "active_session_id": dataset.active_session_id,
            "source_path": f"datasets/{dataset.id}/source.csv",
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
                for session in sorted(dataset.sessions.values(), key=lambda item: item.created_time)
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
                for plot in sorted(dataset.saved_plots.values(), key=lambda item: item.created_time)
            ],
        }

    def _project_manifest(self) -> dict[str, Any]:
        if not self.ready:
            raise ValueError("Upload a CSV file first")
        return {
            "format": "danaleo.project",
            "version": 2,
            "active_dataset_id": self.active_dataset_id,
            "time_counter": self.time_counter,
            "datasets": [self._dataset_manifest(dataset) for dataset in self.datasets.values()],
        }

    def export_project(self) -> bytes:
        if not self.ready:
            raise ValueError("Upload a CSV file first")
        for dataset in self.datasets.values():
            if not Path(dataset.csv_path).exists():
                raise ValueError(f"Source CSV is no longer available: {dataset.csv_name}")

        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            manifest = self._project_manifest()
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for dataset in self.datasets.values():
                archive.write(dataset.csv_path, f"datasets/{dataset.id}/source.csv")
        return buffer.getvalue()

    def _restore_dataset(self, raw: dict[str, Any], source_bytes: bytes) -> DatasetRecord:
        csv_name = str(raw.get("csv_name") or "source.csv")
        suffix = Path(csv_name).suffix or ".csv"
        with NamedTemporaryFile(delete=False, suffix=suffix, prefix="danaleo_") as tmp:
            tmp.write(source_bytes)
            tmp_path = tmp.name

        sample_info = raw.get("sample_info")
        if sample_info:
            df, restored_sample_info = self._read_csv_with_sampling(
                tmp_path,
                sample_info.get("mode", "none"),
                sample_info.get("sample_n"),
                sample_info.get("sample_frac"),
                sample_info.get("random_state", 42),
            )
            if restored_sample_info:
                restored_sample_info["original_rows"] = sample_info.get("original_rows", restored_sample_info["original_rows"])
        else:
            df, restored_sample_info = self._read_csv_with_sampling(tmp_path)

        raw_sessions = raw.get("sessions") or []
        if not raw_sessions:
            raise ValueError("Saved progress file does not contain any sessions")

        records: dict[str, SessionRecord] = {}
        for item in raw_sessions:
            operations = [
                OperationRecord(
                    id=str(op["id"]),
                    operation_type=str(op["operation_type"]),
                    label=str(op["label"]),
                    params=dict(op.get("params") or {}),
                    time=int(op["time"]),
                )
                for op in item.get("operations", [])
            ]
            record = SessionRecord(
                id=str(item["id"]),
                name=str(item["name"]),
                parent_id=item.get("parent_id"),
                created_time=int(item["created_time"]),
                created_overview=dict(item.get("created_overview") or {}),
                source_operation_id=item.get("source_operation_id"),
                operations=operations,
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
            current = df.copy() if session.parent_id is None else build_session_data(session.parent_id, session.source_operation_id)
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
        for item in raw.get("saved_plots") or []:
            session_id = str(item["session_id"])
            if session_id not in records:
                continue
            controls = dict(item.get("controls") or {})
            plot = PlotRecord(
                id=str(item["id"]),
                session_id=session_id,
                session_name=str(item.get("session_name") or records[session_id].name),
                column=str(item["column"]),
                plot_type=str(item["plot_type"]),
                local_query=str(item.get("local_query") or ""),
                controls=controls,
                figure=build_figure(records[session_id].data, str(item["column"]), str(item["plot_type"]), str(item.get("local_query") or ""), controls),
                include_in_export=bool(item.get("include_in_export", True)),
                remark=str(item.get("remark") or ""),
                created_time=int(item["created_time"]),
                title=str(item.get("title") or f"{item['plot_type']} - {item['column']}"),
            )
            plots[plot.id] = plot

        active_session_id = raw.get("active_session_id")
        if active_session_id not in records:
            active_session_id = sorted(records.values(), key=lambda item: item.created_time)[0].id
        return DatasetRecord(
            id=str(raw.get("id") or uuid4().hex),
            csv_path=tmp_path,
            csv_name=csv_name,
            sample_info=restored_sample_info,
            active_session_id=str(active_session_id),
            sessions=records,
            saved_plots=plots,
            provenance=dict(raw.get("provenance") or {}) or None,
        )

    def import_project(self, project_bytes: bytes) -> dict[str, Any]:
        with ZipFile(BytesIO(project_bytes)) as archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except KeyError as exc:
                raise ValueError("Saved progress file is missing required project data") from exc

            if manifest.get("format") != "danaleo.project" or manifest.get("version") not in {1, 2}:
                raise ValueError("Unsupported saved progress file")

            if manifest.get("version") == 1:
                try:
                    source_bytes = archive.read("source.csv")
                except KeyError as exc:
                    raise ValueError("Saved progress file is missing required project data") from exc
                raw_datasets = [{**manifest, "id": uuid4().hex}]
                source_by_id = {raw_datasets[0]["id"]: source_bytes}
            else:
                raw_datasets = manifest.get("datasets") or []
                if not raw_datasets:
                    raise ValueError("Saved progress file does not contain any datasets")
                dataset_ids = [str(raw.get("id") or "") for raw in raw_datasets]
                if any(not dataset_id for dataset_id in dataset_ids):
                    raise ValueError("Saved progress file contains a dataset without an id")
                if len(set(dataset_ids)) != len(dataset_ids):
                    raise ValueError("Saved progress file contains duplicate dataset ids")
                try:
                    source_by_id = {
                        str(raw["id"]): archive.read(str(raw.get("source_path") or f"datasets/{raw['id']}/source.csv"))
                        for raw in raw_datasets
                    }
                except KeyError as exc:
                    raise ValueError("Saved progress file is missing required project data") from exc

        restored = {
            str(raw["id"]): self._restore_dataset(raw, source_by_id[str(raw["id"])])
            for raw in raw_datasets
        }
        max_time = max(
            [int(manifest.get("time_counter") or 0)]
            + [session.created_time for dataset in restored.values() for session in dataset.sessions.values()]
            + [op.time for dataset in restored.values() for session in dataset.sessions.values() for op in session.operations]
            + [plot.created_time for dataset in restored.values() for plot in dataset.saved_plots.values()]
        )
        active_dataset_id = manifest.get("active_dataset_id")
        if active_dataset_id not in restored:
            active_dataset_id = next(iter(restored))
        self.reset()
        self.datasets = restored
        self.active_dataset_id = str(active_dataset_id)
        self.time_counter = max_time
        return self.workspace_summary()

    def session_summary(self, session: SessionRecord, include_profile: bool = False) -> dict[str, Any]:
        summary = {
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
        if include_profile:
            summary["profile"] = dataset_profile(session.data)
        return summary

    def dataset_summary(self, dataset: DatasetRecord) -> dict[str, Any]:
        active = dataset.sessions[dataset.active_session_id]
        return {
            "id": dataset.id,
            "csv_name": dataset.csv_name,
            "sample_info": dataset.sample_info,
            "provenance": dataset.provenance,
            "active_session_id": dataset.active_session_id,
            "rows": len(active.data),
            "columns": len(active.data.columns),
            "sessions": len(dataset.sessions),
            "saved_plots": len(dataset.saved_plots),
        }

    def workspace_summary(self) -> dict[str, Any]:
        active = self.require_session(self.active_session_id) if self.ready else None
        return {
            "ready": self.ready,
            "active_dataset_id": self.active_dataset_id,
            "datasets": [self.dataset_summary(dataset) for dataset in self.datasets.values()],
            "csv_name": self.csv_name,
            "csv_path": self.csv_path,
            "sample_info": self.sample_info,
            "active_session_id": self.active_session_id,
            "active_session": self.session_summary(active, include_profile=True) if active else None,
            "sessions": [self.session_summary(s) for s in sorted(self.sessions.values(), key=lambda x: x.created_time)],
            "saved_plots": [p.__dict__ for p in sorted(self.saved_plots.values(), key=lambda x: x.created_time)],
        }


store = WorkspaceStore()
