from __future__ import annotations

import pytest
from pydantic import ValidationError

from danaleo.server.models import (
    ActivateDatasetRequest,
    CreateSessionRequest,
    PlotRequest,
    SavePlotRequest,
    UpdatePlotRequest,
)


def test_session_and_plot_requests_validate_required_fields():
    with pytest.raises(ValidationError):
        CreateSessionRequest(name="")
    with pytest.raises(ValidationError):
        PlotRequest(session_id="session", column="x")


def test_request_defaults_are_independent_and_export_defaults_are_stable():
    first = PlotRequest(session_id="s", column="x", plot_type="histogram")
    second = PlotRequest(session_id="s", column="x", plot_type="histogram")
    first.controls["bins"] = 5

    assert second.controls == {}

    saved = SavePlotRequest(session_id="s", column="x", plot_type="histogram")
    assert saved.include_in_export is True
    assert saved.remark == ""
    assert saved.title is None

    update = UpdatePlotRequest()
    assert update.include_in_export is None
    assert update.remark is None

    dataset = ActivateDatasetRequest(dataset_id="dataset-1")
    assert dataset.dataset_id == "dataset-1"
