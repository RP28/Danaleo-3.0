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
    ]:
        assert control in source


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


def test_upload_zone_limits_to_csv_and_exposes_sampling_inputs():
    source = read_frontend("components/UploadZone.jsx")

    assert 'accept=".csv,text/csv"' in source
    assert "sample_mode" in source
    assert "sample_n" in source
    assert "sample_frac" in source
    assert "setSampleMode('none')" in source
    assert "setSampleMode('n')" in source
    assert "setSampleMode('frac')" in source


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


def test_session_tree_panel_is_collapsible_dropdown():
    source = read_frontend("components/SessionTree.jsx")
    styles = read_frontend("styles.css")

    assert "const [isTreeExpanded, setIsTreeExpanded] = useState(true);" in source
    assert "aria-expanded={isTreeExpanded}" in source
    assert 'aria-controls="session-tree-canvas"' in source
    assert "tree-panel-toggle" in source
    assert "{isTreeExpanded && (" in source
    assert ".tree-panel.collapsed" in styles
    assert ".tree-panel-toggle-label" in styles