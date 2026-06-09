from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(relative_path: str) -> str:
    return (ROOT / "frontend" / "src" / relative_path).read_text(encoding="utf-8")


def test_frontend_build_outputs_to_packaged_static_directory():
    package_json = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert "build" in package_json["scripts"]
    assert "vite build" in package_json["scripts"]["build"]
    assert "../src/danaleo/server/static" in package_json["scripts"]["build"]
    assert "--emptyOutDir" in package_json["scripts"]["build"]


def test_api_client_matches_backend_routes_and_surfaces_detail_errors():
    source = read_frontend("api.js")

    assert "/api/workspace" in source
    assert "/api/upload" in source
    assert "/api/sessions/activate" in source
    assert "/api/plots/preview" in source
    assert "/api/plots/save" in source
    assert "/api/export/notebook" in source
    assert "/columns/${encodeURIComponent(column)}/stats" in source
    assert "data.detail || message" in source
    assert "throw new Error(message)" in source


def test_session_rename_form_does_not_prevent_submit_click():
    source = read_frontend("components/SessionTree.jsx")

    assert "onSubmit={submitRename}" in source
    assert "onClick={stopOnly}" in source
    assert "onPointerDown={stopOnly}" in source
    assert "onClick={stop}" not in source
    assert 'aria-label="Save session name"' in source


def test_app_rename_callback_reports_success_or_failure_to_tree_node():
    source = read_frontend("App.jsx")

    assert "renameSessionFromTree" in source
    assert "api.renameSession(sessionId, cleanName)" in source
    assert "return true;" in source
    assert "return false;" in source


def test_session_tree_shows_parent_context_and_active_lineage():
    source = read_frontend("components/SessionTree.jsx")

    assert "layoutSessions" in source
    assert "activeLineageEdgeIds" in source
    assert "session-node-parent" in source
    assert "From {data.parentName}" in source
    assert "Parent session:" in source
    assert "active-lineage" in source
    assert "parentName: parent?.name" in source


def test_session_tree_branches_child_from_last_parent_operation_when_created_after_operations():
    source = read_frontend("components/SessionTree.jsx")

    assert "source_operation_id" in source
    assert "sessionEdgeSourceNodeId" in source
    assert "operationsBeforeBranch" in source
    assert "op.time < child.created_time" in source
    assert "const sourceNodeId = sessionEdgeSourceNodeId(session, byId)" in source
    assert "source: sourceNodeId" in source
    assert "sessionEdgeTargetNodeId(session)" in source


def test_session_tree_renders_operations_before_current_state_card():
    source = read_frontend("components/SessionTree.jsx")
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "sessionStartNodeId" in source
    assert "sessionStartNode" in source
    assert "sessionCurrentX" in source
    assert "CURRENT_STATE_GAP" in source
    assert "session.created_overview" in source
    assert "Current state" in styles


def test_tree_uses_compact_viewport_instead_of_auto_shrinking_everything():
    source = read_frontend("components/SessionTree.jsx")
    styles = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "fitView={false}" in source
    assert "defaultViewport={{ x: 42, y: 44, zoom: 0.92 }}" in source
    assert "const TIMELINE_X_GAP = 178" in source
    assert "const OPERATION_EDGE_TYPE = 'straight'" in source
    assert "const BRANCH_EDGE_TYPE = 'bezier'" in source
    assert "max-width: 126px" in styles


def test_auto_session_names_use_global_sequence_for_tree_readability():
    source = read_frontend("App.jsx")

    assert "function nextBranchName" in source
    assert "const usedNumbers = sessions" in source
    assert "Math.max(...usedNumbers) + 1" in source
    assert "return `s${nextIndex}`;" in source
    assert "return `${parent.name}.${nextIndex}`;" not in source


def test_plot_builder_exposes_current_plot_modes_and_controls():
    source = read_frontend("components/PlotBuilder.jsx")

    for plot_type in [
        "histogram",
        "kde",
        "box",
        "violin",
        "bar_top_n",
        "pie_top_n",
        "grouped_kde",
        "grouped_box",
        "grouped_violin",
        "scatter",
        "hexbin",
        "line",
    ]:
        assert plot_type in source

    for control in [
        "bins",
        "top_n",
        "bw_adjust",
        "points",
        "fill",
        "group_by",
        "group_limit",
        "show_outliers",
        "subplot_enabled",
        "subplot_columns",
        "subplot_cols",
        "subplot_limit",
        "compare_with",
        "marker_size",
        "alpha",
        "gridsize",
        "orientation",
        "sort_order",
        "show_grid",
        "log_x",
        "log_y",
        "chart_title",
    ]:
        assert control in source


def test_workspace_is_overview_first_and_keeps_sessions_in_dedicated_view():
    app = read_frontend("App.jsx")
    overview = read_frontend("components/OverviewDashboard.jsx")
    sidebar = read_frontend("components/Sidebar.jsx")

    assert "OverviewDashboard" in app
    assert "activeView" in app
    assert "Overview" in app
    assert "Explore & plot" in app
    assert "Sessions" in app
    assert "Highest absolute Pearson correlations" in overview
    assert "Variables with missing values" in overview
    assert "First {profile.preview.length} rows" in overview
    assert "drop_duplicates" in overview
    assert "Find a column" in sidebar


def test_loading_new_or_saved_data_resets_transient_workspace_state():
    app = read_frontend("App.jsx")

    assert "const openWorkspace = useCallback" in app
    assert "setSelectedColumn(null)" in app
    assert "setColumnStats(null)" in app
    assert "setActiveFigure(null)" in app
    assert "setActiveView('overview')" in app
    assert "onUploaded={openWorkspace}" in app


def test_dataset_plot_builder_resets_when_active_session_changes():
    overview = read_frontend("components/OverviewDashboard.jsx")

    assert "key={session.id}" in overview


def test_dataset_level_plots_are_not_in_column_plot_builder():
    builder = read_frontend("components/PlotBuilder.jsx")
    dataset_builder = read_frontend("components/DatasetPlotBuilder.jsx")

    assert "correlation_heatmap" not in builder
    assert "missing_values" not in builder
    assert "correlation_heatmap" in dataset_builder
    assert "missing_values" in dataset_builder


def test_plot_builder_keeps_plot_filter_local_and_sends_export_metadata():
    source = read_frontend("components/PlotBuilder.jsx")

    assert "localQuery" in source
    assert "local_query: localQuery" in source
    assert "include_in_export: include" in source
    assert "remark" in source
    assert "title" in source
    assert "api.previewPlot(payload)" in source
    assert "api.savePlot" in source


def test_saved_plots_can_toggle_export_state():
    source = read_frontend("components/SavedPlots.jsx")

    assert "api.updatePlot" in source
    assert "include_in_export: !plot.include_in_export" in source
    assert "onWorkspaceUpdate(data)" in source
    assert "In export" in source
    assert "Skip export" in source


def test_toasts_auto_dismiss_after_five_seconds():
    source = read_frontend("components/Toast.jsx")

    assert "useEffect" in source
    assert "window.setTimeout(onClose, 5000)" in source
    assert "window.clearTimeout(timer)" in source


def test_upload_zone_limits_to_csv_and_exposes_sampling_inputs():
    source = read_frontend("components/UploadZone.jsx")

    assert 'accept=".csv,text/csv"' in source
    assert "sample_mode" in source
    assert "sample_n" in source
    assert "sample_frac" in source
    assert "setSampleMode('none')" in source
    assert "setSampleMode('n')" in source
    assert "setSampleMode('frac')" in source
    assert "multiple" in source
    assert "files.forEach((file) => form.append('file', file))" in source


def test_dataset_tabs_support_upload_activation_and_deletion():
    app = read_frontend("App.jsx")
    tabs = read_frontend("components/DatasetTabs.jsx")
    api = read_frontend("api.js")

    assert "DatasetTabs" in app
    assert "workspace.datasets.map" in tabs
    assert "workspace.active_dataset_id" in tabs
    assert "api.activateDataset(datasetId)" in tabs
    assert "api.deleteDataset(dataset.id)" in tabs
    assert "multiple" in tabs
    assert "/api/datasets/activate" in api
    assert "/api/datasets/${datasetId}" in api
    assert "Clear workspace" in app


def test_visual_merge_workflow_exposes_join_types_keys_preview_and_creation():
    tabs = read_frontend("components/DatasetTabs.jsx")
    merge = read_frontend("components/MergeDatasetsModal.jsx")
    api = read_frontend("api.js")
    styles = read_frontend("styles.css")

    assert "MergeDatasetsModal" in tabs
    assert "workspace.datasets.length > 1" in tabs
    for join_type in ["inner", "left", "right", "outer", "cross"]:
        assert f"value: '{join_type}'" in merge
    assert "left_on" in merge
    assert "right_on" in merge
    assert "one_to_one" in merge
    assert "matched_rows" in merge
    assert "left_only_rows" in merge
    assert "right_only_rows" in merge
    assert "api.previewMerge(payload)" in merge
    assert "api.createMerge(payload)" in merge
    assert "commonColumn" in merge
    assert "/api/merges/preview" in api
    assert "/api/merges" in api
    assert ".merge-visual" in styles
    assert "merge-provenance-banner" in read_frontend("components/OverviewDashboard.jsx")


def test_recent_session_operations_panel_removed_from_column_details():
    source = read_frontend("components/ColumnDetails.jsx")

    assert "Recent session operations" not in source
    assert "operation-list" not in source
    assert "activeSession.operations" not in source


def test_column_delete_is_in_sidebar_column_section():
    app = read_frontend("App.jsx")
    sidebar = read_frontend("components/Sidebar.jsx")
    details = read_frontend("components/ColumnDetails.jsx")
    styles = read_frontend("styles.css")

    assert "onDropColumn" in sidebar
    assert "Drop column" in sidebar
    assert "api.applyOperation(activeSessionId, 'drop_column', { column })" in app
    assert "Drop column" not in details
    assert ".column-delete-btn" in styles


def test_session_tree_panel_is_always_visible_inside_sessions_tab():
    source = read_frontend("components/SessionTree.jsx")

    assert "isTreeExpanded" not in source
    assert "tree-panel-toggle" not in source
    assert "Hide" not in source
    assert 'id="session-tree-canvas"' in source
