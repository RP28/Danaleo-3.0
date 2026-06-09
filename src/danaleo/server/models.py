from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    name: str = Field(min_length=1)
    parent_id: str | None = None


class ActivateSessionRequest(BaseModel):
    session_id: str


class ActivateDatasetRequest(BaseModel):
    dataset_id: str


class MergeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    left_session_id: str
    right_session_id: str
    how: str = "inner"
    left_on: list[str] = Field(default_factory=list)
    right_on: list[str] = Field(default_factory=list)
    suffixes: list[str] = Field(default_factory=lambda: ["_left", "_right"])
    relationship: str | None = Field(default=None, alias="validate")
    name: str = "merged.csv"


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
