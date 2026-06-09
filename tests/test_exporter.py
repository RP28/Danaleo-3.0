from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import nbformat
import pytest

from danaleo.core.exporter import export_notebook, export_notebooks_payload
from danaleo.core.session_store import WorkspaceStore


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

def notebook_code_cells(raw: bytes) -> list[str]:
    notebook = nbformat.reads(raw.decode("utf-8"), as_version=4)
    return [cell.source for cell in notebook.cells if cell.cell_type == "code"]

def test_export_notebook_recreates_sessions_operations_selected_plots(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(
        csv_bytes,
        "customers.csv",
        sample_mode="n",
        sample_n=6,
        random_state=3,
    )

    base_id = workspace_store.active_session_id
    child_id = workspace_store.create_session("Sydney Cleanup", base_id)["active_session_id"]

    workspace_store.apply_session_operation(child_id, "filter_rows", {"query": "city == 'Sydney'"})
    workspace_store.apply_session_operation(child_id, "drop_missing", {"column": "income"})

    workspace_store.save_plot(
        child_id,
        "income",
        "histogram",
        local_query="age > 20",
        controls={"bins": 5},
        include_in_export=True,
        remark="Income distribution after filtering.",
        title="Filtered income",
    )
    workspace_store.save_plot(
        child_id,
        "segment",
        "bar_top_n",
        controls={"top_n": 3},
        include_in_export=False,
        title="Skipped segment plot",
    )

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "Danaleo EDA Export: customers.csv" in combined_sources
    assert "df = pd.read_csv" in combined_sources
    assert "df = pd.read_csv('customers.csv')" in combined_sources
    assert "df = df.sample(n=6, random_state=3).reset_index(drop=True)" in combined_sources
    assert "df_sydney_cleanup = df.copy()" in combined_sources
    assert "df_sydney_cleanup = df_sydney_cleanup.query(\"city == 'Sydney'\").copy()" in combined_sources
    assert "df_sydney_cleanup = df_sydney_cleanup.dropna(subset=['income']).copy()" in combined_sources
    assert "Income distribution after filtering." in combined_sources
    assert "Filtered income" in combined_sources
    assert "sns.histplot(" in combined_sources


def test_export_notebook_requires_loaded_workspace():
    workspace_store = WorkspaceStore()

    with pytest.raises(ValueError, match="Nothing to export"):
        export_notebook(workspace_store)


def test_export_replays_branch_creation_at_exact_time_not_after_future_parent_ops(
    csv_bytes: bytes,
):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id
    parent_id = workspace_store.create_session("Parent", base_id)["active_session_id"]

    workspace_store.apply_session_operation(parent_id, "drop_missing", {"column": "income"})
    child_id = workspace_store.create_session("Child After Missing Drop", parent_id)[
        "active_session_id"
    ]

    workspace_store.apply_session_operation(parent_id, "drop_column", {"column": "segment"})
    workspace_store.apply_session_operation(child_id, "filter_rows", {"query": "age > 30"})

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    first_parent_op = "df_parent = df_parent.dropna(subset=['income']).copy()"
    child_copy = "df_child_after_missing_drop = df_parent.copy()"
    later_parent_op = "df_parent = df_parent.drop(columns=['segment']).copy()"
    child_op = "df_child_after_missing_drop = df_child_after_missing_drop.query('age > 30').copy()"

    assert first_parent_op in combined_sources
    assert child_copy in combined_sources
    assert later_parent_op in combined_sources
    assert child_op in combined_sources

    assert combined_sources.index(first_parent_op) < combined_sources.index(child_copy)
    assert combined_sources.index(child_copy) < combined_sources.index(later_parent_op)
    assert combined_sources.index(child_copy) < combined_sources.index(child_op)


def test_export_sanitizes_duplicate_session_variable_names(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id

    workspace_store.create_session("My Session!", base_id)
    workspace_store.create_session("My Session?", base_id)

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "df_my_session = df.copy()" in combined_sources
    assert "df_my_session_2 = df.copy()" in combined_sources


def test_export_replays_replace_values_and_drop_missing_operations(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id

    workspace_store.apply_session_operation(
        base_id,
        "replace_values",
        {"column": "segment", "old_value": "A", "new_value": "Alpha"},
    )
    workspace_store.apply_session_operation(
        base_id,
        "drop_missing",
        {"column": "income"},
    )

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "df['segment'] = df['segment'].replace('A', 'Alpha')" in combined_sources
    assert "df = df.dropna(subset=['income']).copy()" in combined_sources


def test_export_replays_typed_and_multiple_replacements():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"value,flag\n1,true\n2,false\n", "typed.csv")
    base_id = workspace_store.active_session_id
    workspace_store.apply_session_operation(
        base_id,
        "replace_values",
        {"column": "value", "old_value": "1, 2", "new_value": "10, 20", "multiple": True},
    )
    workspace_store.apply_session_operation(
        base_id,
        "replace_values",
        {"column": "flag", "old_value": "true", "new_value": "false", "multiple": False},
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "df['value'] = df['value'].replace([1, 2], [10, 20])" in combined_sources
    assert "df['flag'] = df['flag'].replace(True, False)" in combined_sources


def test_export_replacement_with_missing_value_compiles():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"value\n1\n2\n", "missing.csv")
    workspace_store.apply_session_operation(
        workspace_store.active_session_id,
        "replace_values",
        {"column": "value", "old_value": "1", "new_value": "null"},
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    operation_cell = next(cell.source for cell in notebook.cells if ".replace(1, pd.NA)" in cell.source)

    compile(operation_cell, "<replace-missing>", "exec")


def test_export_replays_drop_duplicates_operation():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"x,y\n1,A\n1,A\n2,B\n", "duplicates.csv")
    workspace_store.apply_session_operation(
        workspace_store.active_session_id,
        "drop_duplicates",
        {},
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "df = df.drop_duplicates().copy()" in combined_sources


def test_export_replays_imputation_operations():
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(b"value,label\n1,A\n,B\n3,\n", "missing.csv")
    session_id = workspace_store.active_session_id
    workspace_store.apply_session_operation(
        session_id,
        "impute_missing",
        {"column": "value", "method": "median"},
    )
    workspace_store.apply_session_operation(
        session_id,
        "impute_missing",
        {"column": "label", "method": "constant", "value": "Unknown"},
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "df['value'] = df['value'].fillna(df['value'].median())" in combined_sources
    assert "df['label'] = df['label'].fillna('Unknown')" in combined_sources


def test_export_keeps_dataset_level_plot_markdown_minimal(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    workspace_store.save_plot(
        workspace_store.active_session_id,
        "age",
        "correlation_heatmap",
        title="Pearson correlation heatmap",
    )

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "Pearson correlation heatmap" in combined_sources
    assert "Scope: **full dataset**" not in combined_sources
    assert "Column: `age`" not in combined_sources


def test_export_includes_group_and_subplot_plot_context(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    base_id = workspace_store.active_session_id

    workspace_store.save_plot(
        base_id,
        "age",
        "histogram",
        controls={
            "bins": 4,
            "group_by": "segment",
            "subplot_enabled": True,
            "subplot_columns": ["income"],
        },
        title="Age and income",
        remark="Grouped and subplot export check",
        include_in_export=True,
    )

    exported = export_notebook(workspace_store)
    combined_sources = notebook_sources(exported)

    assert "Age and income" in combined_sources
    assert "Grouped and subplot export check" in combined_sources
    assert "Group by: `segment`" not in combined_sources
    assert "Subplot columns: `age`, `income`" not in combined_sources
    assert "sns.histplot(" in combined_sources


def test_exported_notebook_plot_code_uses_only_standalone_libraries(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    base_id = workspace_store.active_session_id
    workspace_store.save_plot(
        base_id,
        "age",
        "scatter",
        controls={"compare_with": "income", "group_by": "segment"},
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    code_sources = "\n\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")

    assert "import pandas as pd" in code_sources
    assert "import numpy as np" in code_sources
    assert "import matplotlib.pyplot as plt" in code_sources
    assert "import seaborn as sns" in code_sources
    assert "sns.scatterplot(" in code_sources
    for cell in notebook.cells:
        if cell.cell_type == "code":
            compile(cell.source, "<exported-notebook-cell>", "exec")


def test_exported_plot_cells_do_not_define_plotting_helpers(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    base_id = workspace_store.active_session_id
    workspace_store.save_plot(base_id, "age", "histogram", controls={"bins": 12})
    workspace_store.save_plot(
        base_id,
        "age",
        "correlation_heatmap",
        controls={"show_values": True},
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    code_sources = [cell.source for cell in notebook.cells if cell.cell_type == "code"]

    assert not any(source.lstrip().startswith("def ") for source in code_sources)
    assert any("sns.histplot(" in source for source in code_sources)
    assert any("sns.heatmap(" in source for source in code_sources)


def test_export_without_saved_plots_has_no_selected_plots_section(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")

    combined_sources = notebook_sources(export_notebook(workspace_store))

    assert "# Selected plots" not in combined_sources
    assert "sns." not in combined_sources


def test_export_payload_includes_marked_plots_in_their_own_dataset_notebooks():
    workspace_store = WorkspaceStore()

    first = workspace_store.load_csv(b"x\n1\n2\n", "first.csv")
    workspace_store.save_plot(
        first["active_session_id"],
        "x",
        "histogram",
        title="First plot",
    )

    workspace_store.load_csv(b"y\n10\n20\n", "second.csv")
    workspace_store.save_plot(
        workspace_store.active_session_id,
        "y",
        "histogram",
        include_in_export=False,
        title="Skipped second plot",
    )

    raw, filename, media_type = export_notebooks_payload(workspace_store)

    assert filename == "danaleo_eda_notebooks.zip"
    assert media_type == "application/zip"

    entries = zip_notebook_sources(raw)

    assert set(entries) == {
        "first_eda.ipynb",
        "second_eda.ipynb",
    }

    first_sources = entries["first_eda.ipynb"]
    second_sources = entries["second_eda.ipynb"]

    assert "Danaleo EDA Export: first.csv" in first_sources
    assert "First plot" in first_sources
    assert "pd.read_csv('first.csv')" in first_sources

    assert "Danaleo EDA Export: second.csv" in second_sources
    assert "First plot" not in second_sources
    assert "Skipped second plot" not in second_sources


def test_export_payload_reconstructs_each_dataset_plot_session_operations_in_own_notebook():
    workspace_store = WorkspaceStore()

    source = workspace_store.load_csv(b"value\n1\n2\n2\n", "source.csv")
    branch_id = workspace_store.create_session(
        "Clean source",
        source["active_session_id"],
    )["active_session_id"]

    workspace_store.apply_session_operation(branch_id, "drop_duplicates", {})
    workspace_store.save_plot(branch_id, "value", "histogram", title="Source values")

    workspace_store.load_csv(b"other\n10\n20\n", "active.csv")

    raw, filename, media_type = export_notebooks_payload(workspace_store)

    assert filename == "danaleo_eda_notebooks.zip"
    assert media_type == "application/zip"

    entries = zip_notebook_sources(raw)

    source_sources = entries["source_eda.ipynb"]
    active_sources = entries["active_eda.ipynb"]

    assert "Source values" in source_sources
    assert "pd.read_csv('source.csv')" in source_sources
    assert ".drop_duplicates().copy()" in source_sources
    assert "_plot_df = df_clean_source.copy()" in source_sources

    assert "Source values" not in active_sources
    assert "pd.read_csv('active.csv')" in active_sources


def test_export_notebook_rebuilds_merge_without_redundant_markdown():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,a\n1,A\n2,B\n", "left.csv")
    right = workspace_store.load_csv(b"id,b\n2,X\n3,Y\n", "right.csv")

    workspace_store.create_merged_dataset(
        left["active_session_id"],
        right["active_session_id"],
        "outer",
        ["id"],
        ["id"],
        ["_left", "_right"],
        name="joined.csv",
    )

    exported = export_notebook(workspace_store)
    sources = notebook_sources(exported)
    code_cells = notebook_code_cells(exported)

    merge_cells = [source for source in code_cells if ".merge(" in source]

    assert "pd.read_csv('left.csv')" in sources
    assert "pd.read_csv('right.csv')" in sources

    assert len(merge_cells) == 1
    assert merge_cells[0].startswith("df = ")
    assert ".merge(" in merge_cells[0]
    assert "pd.merge(" not in merge_cells[0]

    assert "how='outer'" in merge_cells[0]
    assert "left_on=['id']" in merge_cells[0]
    assert "right_on=['id']" in merge_cells[0]
    assert "suffixes=('_left', '_right')" in merge_cells[0]

def test_exported_merged_root_operations_and_plots_use_loaded_dataframe():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,value\n1,10\n2,20\n2,20\n", "left.csv")
    right = workspace_store.load_csv(b"id,label\n2,B\n3,C\n", "right.csv")
    merged = workspace_store.create_merged_dataset(
        left["active_session_id"],
        right["active_session_id"],
        "left",
        ["id"],
        ["id"],
        ["_left", "_right"],
        name="merged.csv",
    )
    merged_session_id = merged["active_session_id"]
    workspace_store.apply_session_operation(merged_session_id, "drop_duplicates", {})
    workspace_store.save_plot(
        merged_session_id,
        "value",
        "histogram",
        title="Merged values",
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    sources = "\n\n".join(cell.source for cell in notebook.cells)

    assert "## Session: Merged result" not in sources
    assert "df = df.drop_duplicates().copy()" in sources
    assert "_plot_df = df.copy()" in sources
    assert "df_merged_result" not in sources
    assert ".merge(" in sources

    namespace = {
        "pd": __import__("pandas"),
        "np": __import__("numpy"),
        "plt": __import__("matplotlib.pyplot", fromlist=["pyplot"]),
        "df": workspace_store.require_session(merged_session_id).data.copy(),
    }
    for cell in notebook.cells:
        if (
            cell.cell_type != "code"
            or "pd.read_csv" in cell.source
            or ".merge(" in cell.source
            or cell.source == "df.head()"
        ):
            continue
        exec(compile(cell.source, "<merged-export-cell>", "exec"), namespace)


def test_renamed_root_session_still_exports_operations_against_df(csv_bytes: bytes):
    workspace_store = WorkspaceStore()
    loaded = workspace_store.load_csv(csv_bytes, "customers.csv")
    root_id = loaded["active_session_id"]
    workspace_store.rename_session(root_id, "Imported customers")
    workspace_store.apply_session_operation(root_id, "drop_duplicates", {})

    sources = notebook_sources(export_notebook(workspace_store))

    assert "## Session: Imported customers" not in sources
    assert "df = df.drop_duplicates().copy()" in sources
    assert "df_imported_customers" not in sources


def test_export_notebook_rebuilds_nested_merge_chain_with_source_session_operations():
    workspace_store = WorkspaceStore()
    products = workspace_store.load_csv(
        b"product_id,subcategory_id,price\n1,10,100\n2,20,200\n3,30,300\n",
        "products.csv",
    )
    product_branch = workspace_store.create_session(
        "Filtered products",
        products["active_session_id"],
    )["active_session_id"]
    workspace_store.apply_session_operation(
        product_branch,
        "filter_rows",
        {"query": "price >= 200"},
    )
    subcategories = workspace_store.load_csv(
        b"subcategory_id,category_id\n10,1\n20,1\n30,2\n",
        "subcategories.csv",
    )
    first_merge = workspace_store.create_merged_dataset(
        product_branch,
        subcategories["active_session_id"],
        "left",
        ["subcategory_id"],
        ["subcategory_id"],
        ["_product", "_subcategory"],
        name="products_with_subcategories.csv",
    )
    categories = workspace_store.load_csv(
        b"category_id,category\n1,A\n2,B\n",
        "categories.csv",
    )
    workspace_store.create_merged_dataset(
        first_merge["active_session_id"],
        categories["active_session_id"],
        "left",
        ["category_id"],
        ["category_id"],
        ["_product", "_category"],
        name="complete_products.csv",
    )

    exported = export_notebook(workspace_store)
    sources = notebook_sources(exported)
    code_cells = notebook_code_cells(exported)

    merge_cells = [source for source in code_cells if ".merge(" in source]

    assert "pd.read_csv('products.csv')" in sources
    assert "pd.read_csv('subcategories.csv')" in sources
    assert "pd.read_csv('categories.csv')" in sources
    assert ".query('price >= 200').copy()" in sources

    assert len(merge_cells) == 2
    assert all("pd.merge(" not in source for source in merge_cells)

    assert "pd.read_csv('products_with_subcategories.csv')" not in sources
    assert "pd.read_csv('complete_products.csv')" not in sources


def test_export_notebook_falls_back_to_merged_snapshot_when_source_dataset_was_removed():
    workspace_store = WorkspaceStore()

    left = workspace_store.load_csv(b"id,a\n1,A\n2,B\n", "left.csv")
    left_dataset_id = left["active_dataset_id"]

    right = workspace_store.load_csv(b"id,b\n2,X\n3,Y\n", "right.csv")

    workspace_store.create_merged_dataset(
        left["active_session_id"],
        right["active_session_id"],
        "outer",
        ["id"],
        ["id"],
        ["_left", "_right"],
        name="joined.csv",
    )

    workspace_store.delete_dataset(left_dataset_id)

    exported = export_notebook(workspace_store)
    sources = notebook_sources(exported)
    code_cells = notebook_code_cells(exported)

    assert "df = pd.read_csv('joined.csv')" in sources

    assert not any(".merge(" in source for source in code_cells)
    assert not any("pd.merge(" in source for source in code_cells)

def test_exported_markdown_keeps_only_critical_headings_and_user_remarks():
    workspace_store = WorkspaceStore()
    loaded = workspace_store.load_csv(b"value\n1\n2\n", "values.csv")
    child_id = workspace_store.create_session("s1", loaded["active_session_id"])[
        "active_session_id"
    ]
    workspace_store.save_plot(
        child_id,
        "value",
        "histogram",
        title="Value distribution",
        remark="Review this distribution.",
    )

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    markdown = [cell.source for cell in notebook.cells if cell.cell_type == "markdown"]

    assert markdown == [
        "# Danaleo EDA Export: values.csv",
        "## Session: s1",
        "## Value distribution",
        "Review this distribution.",
    ]


def test_exported_workflows_emit_each_load_merge_and_operation_as_separate_code_cell():
    workspace_store = WorkspaceStore()
    left = workspace_store.load_csv(b"id,value\n1,A\n1,A\n2,B\n", "left.csv")
    workspace_store.apply_session_operation(left["active_session_id"], "drop_duplicates", {})
    right = workspace_store.load_csv(b"id,label\n1,X\n2,Y\n", "right.csv")
    merged = workspace_store.create_merged_dataset(
        left["active_session_id"],
        right["active_session_id"],
        "left",
        ["id"],
        ["id"],
        ["_left", "_right"],
        name="merged.csv",
    )
    workspace_store.apply_session_operation(merged["active_session_id"], "drop_duplicates", {})

    notebook = nbformat.reads(export_notebook(workspace_store).decode("utf-8"), as_version=4)
    code_cells = [cell.source for cell in notebook.cells if cell.cell_type == "code"]

    assert "df_left = pd.read_csv('left.csv')" in code_cells
    assert "df_left = df_left.drop_duplicates().copy()" in code_cells
    assert "df_right = pd.read_csv('right.csv')" in code_cells
    merge_cells = [
        source
        for source in code_cells
        if source.startswith("df = ") and ".merge(" in source
    ]

    assert len(merge_cells) == 1
    assert "pd.merge(" not in merge_cells[0]
    assert "how='left'" in merge_cells[0]
    assert "left_on=['id']" in merge_cells[0]
    assert "right_on=['id']" in merge_cells[0]
    assert "df = df.drop_duplicates().copy()" in code_cells
