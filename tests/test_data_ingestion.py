from __future__ import annotations

import gzip
from io import BytesIO

import pandas as pd
import pytest

from danaleo.core.data_ingestion import is_supported_data_filename, source_format
from danaleo.core.exporter import export_notebook
from danaleo.core.session_store import WorkspaceStore


def test_supported_data_extensions_cover_common_tabular_formats():
    for filename in [
        "data.csv",
        "data.tsv",
        "data.json",
        "data.jsonl",
        "data.xlsx",
        "data.parquet",
        "data.feather",
        "data.orc",
        "data.dta",
        "data.sas7bdat",
        "data.h5",
    ]:
        assert is_supported_data_filename(filename)

    assert not is_supported_data_filename("unsafe.pkl")
    with pytest.raises(ValueError, match="Unsupported data file type"):
        source_format("unsafe.pkl")


@pytest.mark.parametrize(
    ("filename", "source", "expected_format"),
    [
        ("records.json", b'[{"name":"Alice","value":1},{"name":"Bob","value":2}]', "json"),
        ("records.jsonl", b'{"name":"Alice","value":1}\n{"name":"Bob","value":2}\n', "jsonl"),
        ("records.tsv", b"name\tvalue\nAlice\t1\nBob\t2\n", "delimited"),
    ],
)
def test_load_data_handles_text_tabular_formats(filename: str, source: bytes, expected_format: str):
    workspace = WorkspaceStore().load_data(source, filename)

    assert workspace["source_format"] == expected_format
    assert workspace["active_session"]["overview"]["rows"] == 2
    assert workspace["active_session"]["overview"]["columns"] == 2


def test_load_data_handles_compressed_text_formats():
    csv_workspace = WorkspaceStore().load_data(gzip.compress(b"name,value\nAlice,1\nBob,2\n"), "records.csv.gz")
    json_workspace = WorkspaceStore().load_data(
        gzip.compress(b'{"name":"Alice","value":1}\n{"name":"Bob","value":2}\n'),
        "records.jsonl.gz",
    )

    assert csv_workspace["source_format"] == "delimited"
    assert csv_workspace["active_session"]["overview"]["columns"] == 2
    assert json_workspace["source_format"] == "jsonl"
    assert json_workspace["active_session"]["overview"]["rows"] == 2


def test_load_data_handles_stata_and_project_round_trip():
    buffer = BytesIO()
    pd.DataFrame({"name": ["Alice", "Bob"], "value": [1, 2]}).to_stata(buffer, write_index=False)

    workspace_store = WorkspaceStore()
    original = workspace_store.load_data(buffer.getvalue(), "records.dta")
    restored = WorkspaceStore().import_project(workspace_store.export_project())

    assert original["source_format"] == "stata"
    assert restored["source_format"] == "stata"
    assert restored["active_session"]["overview"]["rows"] == 2


@pytest.mark.parametrize(
    ("filename", "writer", "expected_format"),
    [
        ("records.xlsx", lambda frame, path: frame.to_excel(path, index=False), "excel"),
        ("records.parquet", lambda frame, path: frame.to_parquet(path, index=False), "parquet"),
        ("records.feather", lambda frame, path: frame.to_feather(path), "feather"),
        ("records.orc", lambda frame, path: frame.to_orc(path, index=False), "orc"),
        ("records.h5", lambda frame, path: frame.to_hdf(path, key="records", index=False), "hdf"),
    ],
)
def test_load_data_handles_spreadsheet_and_columnar_formats(
    tmp_path,
    filename: str,
    writer,
    expected_format: str,
):
    path = tmp_path / filename
    writer(pd.DataFrame({"name": ["Alice", "Bob"], "value": [1, 2]}), path)

    try:
        workspace = WorkspaceStore().load_data(path.read_bytes(), filename)
    except ValueError as exc:
        if expected_format == "orc" and "sysctlbyname failed" in str(exc):
            pytest.skip("PyArrow ORC reader cannot query cache sizes in this macOS sandbox")
        raise

    assert workspace["source_format"] == expected_format
    assert workspace["active_session"]["overview"]["rows"] == 2
    assert workspace["active_session"]["overview"]["columns"] == 2


def test_excel_numeric_and_duplicate_headers_are_normalized(tmp_path):
    path = tmp_path / "numeric_headers.xlsx"
    pd.DataFrame([[1, 2, 3]], columns=[4046, "4046", None]).to_excel(path, index=False)

    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_data(path.read_bytes(), path.name)
    columns = [card["name"] for card in workspace["active_session"]["columns"]]
    notebook = export_notebook(workspace_store).decode("utf-8")

    assert columns == ["4046", "4046.1", "Unnamed: 2"]
    assert "df.columns = ['4046', '4046.1', 'Unnamed: 2']" in notebook


def test_json_notebook_export_uses_matching_reader():
    workspace_store = WorkspaceStore()
    workspace_store.load_data(b'{"name":"Alice","value":1}\n', "records.jsonl")

    notebook = export_notebook(workspace_store).decode("utf-8")

    assert "pd.read_json('records.jsonl', lines=True)" in notebook
