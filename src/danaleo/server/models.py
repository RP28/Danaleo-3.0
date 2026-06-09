from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    name: str = Field(min_length=1)
    parent_id: str | None = None


class ActivateSessionRequest(BaseModel):
    session_id: str


class ActivateDatasetRequest(BaseModel):
    dataset_id: str


class RenameSessionRequest(BaseModel):
    name: str = Field(min_length=1)


class OperationRequest(BaseModel):
    operation_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class PlotRequest(BaseModel):
    session_id: str
    column: str
    plot_type: str
    local_query: str = ""
    controls: dict[str, Any] = Field(default_factory=dict)


class SavePlotRequest(PlotRequest):
    include_in_export: bool = True
    remark: str = ""
    title: str | None = None


class UpdatePlotRequest(BaseModel):
    include_in_export: bool | None = None
    remark: str | None = None
