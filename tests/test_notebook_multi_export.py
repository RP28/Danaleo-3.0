from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import nbformat
from fastapi.testclient import TestClient

from danaleo.core.exporter import export_notebooks_payload
from danaleo.core.session_store import WorkspaceStore, store
from danaleo.server.app import app


def notebook_sources(raw: bytes) -> str:
    notebook = nbformat.reads(raw.decode("utf-8"), as_version=4)
    return "\n\n".join(cell.source for cell in notebook.cells)


def zip_notebook_sources(raw: bytes) -> dict[str, str]:
    with ZipFile(BytesIO(raw)) as archive:
        return {
            name: notebook_sources(archive.read(name))
            for name in archive.namelist()
            if name.endswith(".ipynb")
        }


def find_notebook_by_title(entries: dict[str, str], csv_name: str) -> str:
    expected_title = f"Danaleo EDA Export: {csv_name}"

    for source in entries.values():
        if expected_title in source:
            return source

    raise AssertionError(f"Notebook for {csv_name} was not found in exported zip")


def test_export_payload_single_dataset_returns_single_ipynb():
    workspace_store = WorkspaceStore()

    workspace_store.load_csv(
        b"id,name\n1,Alice\n2,Bob\n",
        "customers.csv",
    )

    raw, filename, media_type = export_notebooks_payload(workspace_store)

    assert filename.endswith(".ipynb")
    assert filename == "customers_eda.ipynb"
    assert media_type == "application/x-ipynb+json"

    sources = notebook_sources(raw)

    assert "Danaleo EDA Export: customers.csv" in sources
    assert "df = pd.read_csv('customers.csv')" in sources


def test_export_payload_multiple_csv_tabs_returns_zip_with_one_ipynb_per_tab():
    workspace_store = WorkspaceStore()

    customers = workspace_store.load_csv(
        b"customer_id,name,city\n1,Alice,Sydney\n2,Bob,Melbourne\n",
        "customers.csv",
    )

    workspace_store.apply_session_operation(
        customers["active_session_id"],
        "filter_rows",
        {"query": "customer_id > 0"},
    )

    orders = workspace_store.load_csv(
        b"order_id,customer_id,total\n101,1,50\n102,2,70\n",
        "orders.csv",
    )

    workspace_store.apply_session_operation(
        orders["active_session_id"],
        "drop_duplicates",
        {},
    )

    raw, filename, media_type = export_notebooks_payload(workspace_store)

    assert filename == "danaleo_eda_notebooks.zip"
    assert media_type == "application/zip"

    entries = zip_notebook_sources(raw)

    assert len(entries) == 2
    assert set(entries) == {
        "customers_eda.ipynb",
        "orders_eda.ipynb",
    }

    customers_sources = entries["customers_eda.ipynb"]
    orders_sources = entries["orders_eda.ipynb"]

    assert "Danaleo EDA Export: customers.csv" in customers_sources
    assert "df = pd.read_csv('customers.csv')" in customers_sources
    assert "df = df.query('customer_id > 0').copy()" in customers_sources

    assert "Danaleo EDA Export: orders.csv" in orders_sources
    assert "df = pd.read_csv('orders.csv')" in orders_sources
    assert "df = df.drop_duplicates().copy()" in orders_sources


def test_export_payload_zip_contains_merged_dataset_notebook_with_dataframe_merge_code():
    workspace_store = WorkspaceStore()

    customers = workspace_store.load_csv(
        b"customer_id,name\n1,Alice\n2,Bob\n",
        "customers.csv",
    )

    orders = workspace_store.load_csv(
        b"order_id,customer_id,total\n101,1,50\n102,2,70\n103,3,90\n",
        "orders.csv",
    )

    workspace_store.create_merged_dataset(
        customers["active_session_id"],
        orders["active_session_id"],
        "inner",
        ["customer_id"],
        ["customer_id"],
        ["_customer", "_order"],
        name="customer_orders.csv",
    )

    raw, filename, media_type = export_notebooks_payload(workspace_store)

    assert filename == "danaleo_eda_notebooks.zip"
    assert media_type == "application/zip"

    entries = zip_notebook_sources(raw)

    assert len(entries) == 3
    assert "customers_eda.ipynb" in entries
    assert "orders_eda.ipynb" in entries
    assert "customer_orders_merged_eda.ipynb" in entries

    merged_sources = entries["customer_orders_merged_eda.ipynb"]

    assert "Danaleo EDA Export: customer_orders.csv" in merged_sources

    # Source CSVs should be loaded.
    assert "pd.read_csv('customers.csv')" in merged_sources
    assert "pd.read_csv('orders.csv')" in merged_sources

    # Merged notebook should rebuild using dataframe .merge(...) code.
    assert ".merge(" in merged_sources
    assert "pd.merge(" not in merged_sources

    assert "how='inner'" in merged_sources
    assert "left_on=['customer_id']" in merged_sources
    assert "right_on=['customer_id']" in merged_sources
    assert "suffixes=('_customer', '_order')" in merged_sources

    # It should not simply read the already-created merged CSV snapshot.
    assert "pd.read_csv('customer_orders.csv')" not in merged_sources


def test_export_payload_zip_keeps_each_dataset_plots_inside_its_own_notebook():
    workspace_store = WorkspaceStore()

    first = workspace_store.load_csv(
        b"x\n1\n2\n3\n",
        "first.csv",
    )

    workspace_store.save_plot(
        first["active_session_id"],
        "x",
        "histogram",
        title="First histogram",
        include_in_export=True,
    )

    second = workspace_store.load_csv(
        b"y\n10\n20\n30\n",
        "second.csv",
    )

    workspace_store.save_plot(
        second["active_session_id"],
        "y",
        "histogram",
        title="Second histogram",
        include_in_export=True,
    )

    raw, filename, media_type = export_notebooks_payload(workspace_store)

    assert filename == "danaleo_eda_notebooks.zip"
    assert media_type == "application/zip"

    entries = zip_notebook_sources(raw)

    first_sources = entries["first_eda.ipynb"]
    second_sources = entries["second_eda.ipynb"]

    assert "First histogram" in first_sources
    assert "Second histogram" not in first_sources

    assert "Second histogram" in second_sources
    assert "First histogram" not in second_sources


def test_export_route_multiple_csv_tabs_downloads_zip_response():
    store.load_csv_batch(
        [
            (b"id,name\n1,Alice\n2,Bob\n", "customers.csv"),
            (b"order_id,total\n101,50\n102,70\n", "orders.csv"),
        ]
    )

    client = TestClient(app)
    response = client.get("/api/export/notebook")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert 'filename="danaleo_eda_notebooks.zip"' in response.headers["content-disposition"]

    entries = zip_notebook_sources(response.content)

    assert set(entries) == {
        "customers_eda.ipynb",
        "orders_eda.ipynb",
    }

    assert "Danaleo EDA Export: customers.csv" in entries["customers_eda.ipynb"]
    assert "Danaleo EDA Export: orders.csv" in entries["orders_eda.ipynb"]