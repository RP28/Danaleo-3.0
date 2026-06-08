from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_session_rename_form_does_not_prevent_submit_click():
    """Regression test for the tree tick icon not saving renamed sessions.

    The bug was caused by the rename form using onClick={stop}, where stop()
    called preventDefault(). Clicking the submit/tick button therefore cancelled
    the native form submit before React could call onSubmit.
    """
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "onSubmit={submitRename}" in source
    assert "onClick={stopOnly}" in source
    assert "onPointerDown={stopOnly}" in source
    assert "onClick={stop}" not in source
    assert "aria-label=\"Save session name\"" in source


def test_app_rename_callback_reports_success_or_failure_to_tree_node():
    source = (ROOT / "frontend/src/App.jsx").read_text()

    assert "return true;" in source
    assert "return false;" in source
    assert "api.renameSession(sessionId, cleanName)" in source


def test_session_tree_shows_parent_context_and_active_lineage():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "layoutSessions" in source
    assert "activeLineageEdgeIds" in source
    assert "session-node-parent" in source
    assert "From {data.parentName}" in source
    assert "Parent session:" in source
    assert "active-lineage" in source
    assert "parentName: parent?.name" in source


def test_topbar_does_not_show_manual_refresh_button():
    source = (ROOT / "frontend/src/App.jsx").read_text()

    assert "RefreshCw" not in source
    assert "> Refresh<" not in source
    assert "Export ipynb" in source


def test_session_tree_branches_child_from_last_parent_operation_when_created_after_operations():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "source_operation_id" in source
    assert "sessionEdgeSourceNodeId" in source
    assert "operationsBeforeBranch" in source
    assert "op.time < child.created_time" in source
    assert "const sourceNodeId = sessionEdgeSourceNodeId(session, byId)" in source
    assert "source: sourceNodeId" in source
    assert "sessionEdgeTargetNodeId(session)" in source
    assert "Timeline runs left to right" not in source


def test_session_tree_renders_operations_before_current_state_card():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "sessionStartNodeId" in source
    assert "sessionStartNode" in source
    assert "sessionCurrentX" in source
    assert "CURRENT_STATE_GAP" in source
    assert "Current state" in (ROOT / "frontend/src/styles.css").read_text()
    assert "session.created_overview" in source



def test_tree_uses_compact_viewport_instead_of_auto_shrinking_everything():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()
    styles = (ROOT / "frontend/src/styles.css").read_text()

    assert "fitView={false}" in source
    assert "defaultViewport={{ x: 42, y: 44, zoom: 0.92 }}" in source
    assert "const TIMELINE_X_GAP = 178" in source
    assert "const OPERATION_EDGE_TYPE = 'straight'" in source
    assert "const BRANCH_EDGE_TYPE = 'bezier'" in source
    assert "max-width: 126px" in styles


def test_auto_session_names_use_global_sequence_for_tree_readability():
    source = (ROOT / "frontend/src/App.jsx").read_text()

    assert "function nextBranchName" in source
    assert "const usedNumbers = sessions" in source
    assert "Math.max(...usedNumbers) + 1" in source
    assert "return `s${nextIndex}`;" in source
    assert "return `${parent.name}.${nextIndex}`;" not in source
    assert "branch ${childCount" not in source


def test_tree_collapses_intermediate_current_state_when_child_starts_from_same_state():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "shouldCollapseCurrentSessionNode" in source
    assert "childBranchesFromFinalOperation" in source
    assert "session.id === activeSessionId" in source
    assert "hasOperations && !collapseCurrentSessionNode" in source
    assert "if (!collapseCurrentSessionNode)" in source
    assert "Intermediate current-state cards collapse" not in source


def test_workspace_uses_compact_density_values():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()
    styles = (ROOT / "frontend/src/styles.css").read_text()

    assert "const NODE_Y_GAP = 98" in source
    assert "const TIMELINE_X_GAP = 178" in source
    assert "const CURRENT_STATE_GAP = 160" in source
    assert "<Background gap={22} size={0.8} />" in source
    assert "grid-template-columns: 260px 1fr" in styles
    assert "--compact-page-pad: 14px" in styles
    assert "height: 360px" in styles
    assert "min-width: 108px" in styles


def test_recent_session_operations_panel_removed_from_column_details():
    source = (ROOT / "frontend/src/components/ColumnDetails.jsx").read_text()

    assert "Recent session operations" not in source
    assert "operation-list" not in source
    assert "activeSession.operations" not in source
    assert "activeSession" not in source


def test_column_details_sections_are_dropdowns_and_closed_by_default():
    source = (ROOT / "frontend/src/components/ColumnDetails.jsx").read_text()
    styles = (ROOT / "frontend/src/styles.css").read_text()

    assert "Basic statistics" in source
    assert "key={`${column}-basic-stats`}" in source
    assert "key={`${column}-top-values`}" in source
    assert "key={`${column}-operations`}" in source
    assert '<details className="soft-details" open' not in source
    assert ".soft-details summary::after" in styles


def test_drop_column_action_lives_in_sidebar_column_list():
    sidebar = (ROOT / "frontend/src/components/Sidebar.jsx").read_text()
    app = (ROOT / "frontend/src/App.jsx").read_text()
    details = (ROOT / "frontend/src/components/ColumnDetails.jsx").read_text()
    styles = (ROOT / "frontend/src/styles.css").read_text()

    assert "column-delete-btn" in sidebar
    assert "aria-label={`Drop column ${col.name}`}" in sidebar
    assert "onDropColumn(col.name)" in sidebar
    assert "onDropColumn={(column) =>" in app
    assert "api.applyOperation(activeSessionId, 'drop_column', { column })" in app
    assert "Drop column" not in details
    assert ".column-delete-btn" in styles


def test_session_tree_uses_timeline_columns_for_parent_operations_and_child_branches():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "branchSourceX" in source
    assert "timelineXForTime(eventTimeForOperation(op), timelineIndex)" in source
    assert "The x-axis is now a real workspace timeline" in source
    assert "branchDelta" in source


def test_sidebar_no_longer_shows_active_session_summary():
    source = (ROOT / "frontend/src/components/Sidebar.jsx").read_text()
    styles = (ROOT / "frontend/src/styles.css").read_text()

    assert "Active session" not in source
    assert "active-session-card" not in source
    assert "Use the tree node controls" not in source
    assert ".active-session-card" not in styles
    assert "Columns" in source


def test_session_tree_header_does_not_render_explanatory_subtitle():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()

    assert "Session tree" in source
    assert "<small>Timeline runs left to right" not in source
    assert "operations and session states are nodes" not in source


def test_session_tree_panel_is_collapsible_dropdown():
    source = (ROOT / "frontend/src/components/SessionTree.jsx").read_text()
    styles = (ROOT / "frontend/src/styles.css").read_text()

    assert "const [isTreeExpanded, setIsTreeExpanded] = useState(true);" in source
    assert "aria-expanded={isTreeExpanded}" in source
    assert 'aria-controls="session-tree-canvas"' in source
    assert "tree-panel-toggle" in source
    assert "{isTreeExpanded && (" in source
    assert "tree-panel collapsed" not in source
    assert ".tree-panel.collapsed" in styles
    assert ".tree-panel-toggle-label" in styles
