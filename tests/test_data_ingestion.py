from __future__ import annotations

import gzip
from decimal import Decimal
from io import BytesIO

import nbformat
import pandas as pd
import pytest

from danaleo.core.data_ingestion import is_supported_data_filename, source_format
from danaleo.core.exporter import export_notebook
from danaleo.core.session_store import WorkspaceStore


def execute_exported_load(workspace_store: WorkspaceStore) -> pd.DataFrame:
    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    namespace: dict = {}
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if cell.source.strip() == "df.head()":
            break
        exec(cell.source, namespace)
    return namespace["df"]


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


def test_json_wrappers_encodings_and_nested_values_are_normalized():
    source = (
        '{"metadata":{"source":"CRM"},"results":'
        '[{"name":"André","profile":{"city":"Montréal"},"tags":["a","b"]}]}'
    ).encode("cp1252")

    workspace = WorkspaceStore().load_data(source, "wrapped.json")
    columns = [card["name"] for card in workspace["active_session"]["columns"]]
    preview = workspace["active_session"]["profile"]["preview"][0]

    assert workspace["parse_info"]["record_path"] == "results"
    assert workspace["parse_info"]["encoding"] == "cp1252"
    assert columns == ["name", "tags", "profile.city"]
    assert preview["tags"] == '["a", "b"]'


def test_json_dict_index_and_scalar_array_are_loaded_as_tables():
    dict_workspace = WorkspaceStore().load_data(
        b'{"alice":{"score":10},"bob":{"score":20}}',
        "scores.json",
    )
    list_workspace = WorkspaceStore().load_data(b'["a","b"]', "values.json")

    assert [card["name"] for card in dict_workspace["active_session"]["columns"]] == [
        "index",
        "score",
    ]
    assert [card["name"] for card in list_workspace["active_session"]["columns"]] == ["value"]


def test_json_column_and_split_orientations_are_loaded_as_tables():
    columns_workspace = WorkspaceStore().load_data(
        b'{"name":["Alice","Bob"],"score":[10,20]}',
        "columns.json",
    )
    split_workspace = WorkspaceStore().load_data(
        b'{"columns":["name","score"],"index":["a","b"],'
        b'"data":[["Alice",10],["Bob",20]]}',
        "split.json",
    )

    assert columns_workspace["active_session"]["overview"]["rows"] == 2
    assert [card["name"] for card in columns_workspace["active_session"]["columns"]] == [
        "name",
        "score",
    ]
    assert [card["name"] for card in split_workspace["active_session"]["columns"]] == [
        "index",
        "name",
        "score",
    ]


def test_content_signatures_override_misleading_supported_extensions(tmp_path):
    excel_path = tmp_path / "actual.xlsx"
    parquet_path = tmp_path / "actual.parquet"
    frame = pd.DataFrame({"name": ["Alice"], "value": [1]})
    frame.to_excel(excel_path, index=False)
    frame.to_parquet(parquet_path, index=False)

    excel_workspace = WorkspaceStore().load_data(excel_path.read_bytes(), "misnamed.csv")
    parquet_workspace = WorkspaceStore().load_data(parquet_path.read_bytes(), "misnamed.txt")
    json_workspace = WorkspaceStore().load_data(b'[{"name":"Alice","value":1}]', "misnamed.txt")

    assert excel_workspace["source_format"] == "excel"
    assert parquet_workspace["source_format"] == "parquet"
    assert json_workspace["source_format"] == "json"


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


def test_excel_selects_non_empty_data_sheet_and_detects_title_rows(tmp_path):
    path = tmp_path / "report.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame().to_excel(writer, sheet_name="Cover", index=False)
        pd.DataFrame({"name": ["Alice", "Bob"], "value": [1, 2]}).to_excel(
            writer,
            sheet_name="Data",
            index=False,
            startrow=2,
        )
        worksheet = writer.sheets["Data"]
        worksheet.cell(row=1, column=1, value="Quarterly report")

    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_data(path.read_bytes(), path.name)
    notebook = export_notebook(workspace_store).decode("utf-8")

    assert workspace["parse_info"]["sheet_name"] == "Data"
    assert workspace["parse_info"]["header_row"] == 2
    assert workspace["active_session"]["overview"]["rows"] == 2
    assert [card["name"] for card in workspace["active_session"]["columns"]] == ["name", "value"]
    assert "header=2" in notebook


def test_excel_rejects_workbooks_without_a_table(tmp_path):
    path = tmp_path / "empty.xlsx"
    pd.DataFrame().to_excel(path, index=False)

    with pytest.raises(ValueError, match="does not contain a non-empty table"):
        WorkspaceStore().load_data(path.read_bytes(), path.name)


def test_hdf_selects_largest_readable_table(tmp_path):
    path = tmp_path / "tables.h5"
    pd.DataFrame({"small": [1]}).to_hdf(path, key="small")
    pd.DataFrame({"name": ["A", "B", "C"], "value": [1, 2, 3]}).to_hdf(path, key="records")

    workspace = WorkspaceStore().load_data(path.read_bytes(), path.name)

    assert workspace["parse_info"]["key"] == "/records"
    assert workspace["active_session"]["overview"]["rows"] == 3


def test_parquet_materializes_meaningful_index_and_reproduces_it_in_notebook(tmp_path):
    path = tmp_path / "indexed.parquet"
    frame = pd.DataFrame({"value": [10, 20]}, index=pd.Index(["A", "B"], name="customer_id"))
    frame.to_parquet(path)

    workspace_store = WorkspaceStore()
    workspace = workspace_store.load_data(path.read_bytes(), path.name)
    notebook = export_notebook(workspace_store).decode("utf-8")

    assert [card["name"] for card in workspace["active_session"]["columns"]] == [
        "customer_id",
        "value",
    ]
    assert workspace["parse_info"]["index_names"] == ["customer_id"]
    assert "df.index.names = ['customer_id']" in notebook
    assert "df = df.reset_index()" in notebook


def test_parquet_binary_and_nested_cells_are_profile_safe(tmp_path):
    path = tmp_path / "complex.parquet"
    pd.DataFrame(
        {
            "raw": [b"hello", b"world"],
            "tags": [["a", "b"], ["c"]],
            "amount": [Decimal("12.34"), Decimal("56.78")],
        }
    ).to_parquet(path, index=False)

    workspace = WorkspaceStore().load_data(path.read_bytes(), path.name)
    preview = workspace["active_session"]["profile"]["preview"][0]

    assert preview["raw"] == "hello"
    assert preview["tags"] == '["a", "b"]'
    assert preview["amount"] == "12.34"


def test_json_notebook_export_uses_matching_reader():
    workspace_store = WorkspaceStore()
    workspace_store.load_data(b'{"name":"Alice","value":1}\n', "records.jsonl")

    notebook = export_notebook(workspace_store).decode("utf-8")

    assert "pd.read_json('records.jsonl', lines=True, encoding='utf-8')" in notebook


def test_wrapped_json_notebook_export_reuses_record_path():
    workspace_store = WorkspaceStore()
    workspace_store.load_data(b'{"data":[{"name":"Alice","value":1}]}', "wrapped.json")

    notebook = export_notebook(workspace_store).decode("utf-8")

    assert "pd.json_normalize(" in notebook
    assert "['data']" in notebook


def test_compressed_wrapped_json_notebook_export_uses_compression_reader():
    workspace_store = WorkspaceStore()
    workspace_store.load_data(
        gzip.compress(b'{"data":[{"name":"Alice","value":1}]}'),
        "wrapped.json.gz",
    )

    notebook = export_notebook(workspace_store).decode("utf-8")

    assert "__import__('gzip').open('wrapped.json.gz'" in notebook
    assert "['data']" in notebook


def test_exported_notebook_load_matches_robust_ingestion(tmp_path, monkeypatch):
    sources = [
        (
            "regional.csv",
            "sep=;\nname;city;empty\nAndré;Montréal;\n;;\n".encode("cp1252"),
        ),
        (
            "wrapped.json",
            b'{"results":[{"name":"Alice","tags":["a","b"],"profile":{"city":"Sydney"}}]}',
        ),
    ]

    excel_path = tmp_path / "report.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame().to_excel(writer, sheet_name="Cover", index=False)
        pd.DataFrame({"name": ["Alice", "Bob"], "value": [1, 2]}).to_excel(
            writer,
            sheet_name="Data",
            index=False,
            startrow=2,
        )
    sources.append((excel_path.name, excel_path.read_bytes()))

    parquet_path = tmp_path / "complex.parquet"
    pd.DataFrame(
        {
            "raw": [b"hello", b"world"],
            "tags": [["a", "b"], ["c"]],
            "amount": [Decimal("12.34"), Decimal("56.78")],
        },
        index=pd.Index(["A", "B"], name="customer_id"),
    ).to_parquet(parquet_path)
    sources.append((parquet_path.name, parquet_path.read_bytes()))

    monkeypatch.chdir(tmp_path)
    for filename, source in sources:
        (tmp_path / filename).write_bytes(source)
        workspace_store = WorkspaceStore()
        workspace_store.load_data(source, filename)
        expected = workspace_store.sessions[workspace_store.active_session_id].data

        pd.testing.assert_frame_equal(execute_exported_load(workspace_store), expected)
