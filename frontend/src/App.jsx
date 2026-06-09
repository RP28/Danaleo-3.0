import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';
import UploadZone from './components/UploadZone.jsx';
import Sidebar from './components/Sidebar.jsx';
import ColumnDetails from './components/ColumnDetails.jsx';
import PlotBuilder from './components/PlotBuilder.jsx';
import SessionTree from './components/SessionTree.jsx';
import SavedPlots from './components/SavedPlots.jsx';
import OverviewDashboard from './components/OverviewDashboard.jsx';
import Toast from './components/Toast.jsx';
import DatasetTabs from './components/DatasetTabs.jsx';
import SaveFileDialog from './components/SaveFileDialog.jsx';
import { BarChart3, Download, GitBranch, LayoutDashboard, Save, Trash2, X } from 'lucide-react';


function nextBranchName(_parent, sessions) {
  const usedNumbers = sessions
    .map((session) => /^s(\d+)$/.exec(session.name))
    .filter(Boolean)
    .map((match) => Number(match[1]));

  const nextIndex = usedNumbers.length > 0 ? Math.max(...usedNumbers) + 1 : 1;
  return `s${nextIndex}`;
}

export default function App() {
  const [workspace, setWorkspace] = useState(null);
  const [selectedColumn, setSelectedColumn] = useState(null);
  const [columnStats, setColumnStats] = useState(null);
  const [activeFigure, setActiveFigure] = useState(null);
  const [toast, setToast] = useState(null);
  const [activeView, setActiveView] = useState('overview');
  const [saveDialog, setSaveDialog] = useState(null);
  const [statsRevision, setStatsRevision] = useState(0);

  const activeSession = workspace?.active_session;
  const activeSessionId = workspace?.active_session_id;

  async function refresh() {
    try {
      const data = await api.workspace();
      setWorkspace(data);
      if (!data.ready) {
        setSelectedColumn(null);
        setColumnStats(null);
      }
    } catch (err) {
      setToast({ type: 'error', text: err.message });
    }
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    async function loadStats() {
      if (!selectedColumn || !activeSessionId) return;
      try {
        const stats = await api.stats(activeSessionId, selectedColumn);
        setColumnStats(stats);
      } catch (err) {
        setToast({ type: 'error', text: err.message });
      }
    }
    loadStats();
  }, [selectedColumn, activeSessionId, statsRevision]);

  const numericColumns = useMemo(() => {
    return activeSession?.columns?.filter((c) => c.kind === 'numeric').map((c) => c.name) || [];
  }, [activeSession]);

  const categoricalColumns = useMemo(() => {
    return activeSession?.columns?.filter((c) => c.kind === 'categorical').map((c) => c.name) || [];
  }, [activeSession]);

  const applyWorkspace = useCallback((next) => {
    setWorkspace(next);
    if (selectedColumn && !next.active_session?.columns.some((c) => c.name === selectedColumn)) {
      setSelectedColumn(null);
      setColumnStats(null);
    }
    if (activeFigure && !next.saved_plots.some((plot) => plot.id === activeFigure.id)) {
      setActiveFigure(null);
    }
  }, [activeFigure, selectedColumn]);

  async function handleWorkspaceUpdate(promise) {
    try {
      const next = await promise;
      applyWorkspace(next);
      setStatsRevision((revision) => revision + 1);
    } catch (err) {
      setToast({ type: 'error', text: err.message });
    }
  }

  const activateSessionFromTree = useCallback(async (sessionId) => {
    if (sessionId === workspace?.active_session_id) return;
    try {
      const next = await api.activateSession(sessionId);
      applyWorkspace(next);
    } catch (err) {
      setToast({ type: 'error', text: err.message });
    }
  }, [applyWorkspace, workspace?.active_session_id]);

  const createSessionFromTree = useCallback(async (parentId) => {
    const parent = workspace?.sessions.find((session) => session.id === parentId);
    if (!parent) return;
    const name = nextBranchName(parent, workspace.sessions);
    try {
      const next = await api.createSession(name, parentId);
      applyWorkspace(next);
      setToast({ type: 'success', text: `Created ${name}` });
    } catch (err) {
      setToast({ type: 'error', text: err.message });
    }
  }, [applyWorkspace, workspace]);



  const renameSessionFromTree = useCallback(async (sessionId, name) => {
    const cleanName = name?.trim();
    if (!cleanName) {
      setToast({ type: 'error', text: 'Session name is required' });
      return false;
    }
    try {
      const next = await api.renameSession(sessionId, cleanName);
      applyWorkspace(next);
      setToast({ type: 'success', text: `Renamed session to ${cleanName}` });
      return true;
    } catch (err) {
      setToast({ type: 'error', text: err.message });
      return false;
    }
  }, [applyWorkspace]);

  const deleteSessionFromTree = useCallback(async (sessionId) => {
    const session = workspace?.sessions.find((item) => item.id === sessionId);
    if (!session) return;
    const childCount = workspace.sessions.filter((item) => item.parent_id === sessionId).length;
    const message = childCount > 0
      ? `Delete "${session.name}" and its ${childCount} child session(s)? Saved plots from this branch will also be removed.`
      : `Delete "${session.name}"? Saved plots from this session will also be removed.`;
    if (!window.confirm(message)) return;
    try {
      const next = await api.deleteSession(sessionId);
      applyWorkspace(next);
      setToast({ type: 'success', text: `Deleted ${session.name}` });
    } catch (err) {
      setToast({ type: 'error', text: err.message });
    }
  }, [applyWorkspace, workspace]);

  const resetToUpload = useCallback(async () => {
    if (!window.confirm('Clear all open datasets and discard current progress?')) return;
    try {
      const next = await api.resetWorkspace();
      setWorkspace(next);
      setSelectedColumn(null);
      setColumnStats(null);
      setActiveFigure(null);
      setToast({ type: 'success', text: 'Workspace cleared' });
    } catch (err) {
      setToast({ type: 'error', text: err.message });
    }
  }, []);

  const activeDataset = workspace?.datasets.find((dataset) => dataset.id === workspace.active_dataset_id);
  const progressName = workspace?.datasets.length > 1
    ? 'danaleo_workspace.danaleo'
    : `${workspace?.csv_name?.replace(/\.[^.]+$/, '') || 'danaleo_progress'}.danaleo`;
  const notebookName = workspace?.datasets.length > 1
    ? 'danaleo_eda_notebooks.zip'
    : `${workspace?.csv_name?.replace(/\.[^.]+$/, '') || 'danaleo'}${activeDataset?.provenance?.type === 'merge' ? '_merged' : ''}_eda.ipynb`;

  const openWorkspace = useCallback((next, resetView = true) => {
    setWorkspace(next);
    setSelectedColumn(null);
    setColumnStats(null);
    setActiveFigure(null);
    if (resetView) setActiveView('overview');
  }, []);

  if (!workspace?.ready) {
    return <UploadZone onUploaded={openWorkspace} onError={(text) => setToast({ type: 'error', text })} toast={toast} setToast={setToast} />;
  }

  function exploreColumn(column) {
    if (column) setSelectedColumn(column);
    setActiveView('explore');
  }

  return (
    <div className="app-shell">
      <Sidebar
        workspace={workspace}
        selectedColumn={selectedColumn}
        onSelectColumn={exploreColumn}
        onDropColumn={(column) => {
          const message = `Drop column "${column}" from the current session?`;
          if (!window.confirm(message)) return;
          handleWorkspaceUpdate(api.applyOperation(activeSessionId, 'drop_column', { column }));
        }}
        savedPlots={(
          <SavedPlots
            plots={workspace.saved_plots}
            activeFigure={activeFigure}
            onSelectFigure={(figure) => {
              setActiveFigure(figure);
              setActiveView('explore');
            }}
            onWorkspaceUpdate={setWorkspace}
            onError={(text) => setToast({ type: 'error', text })}
          />
        )}
      />

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Danaleo 3.0</p>
            <h1>{workspace.csv_name}</h1>
          </div>
          <div className="topbar-actions">
            <button className="ghost-btn" onClick={resetToUpload}><Trash2 size={16}/> Clear workspace</button>
            <button className="ghost-btn" onClick={() => setSaveDialog({ title: 'Save Danaleo progress', suggestedName: progressName, loadFile: api.progressFile })}><Save size={16}/> Save progress</button>
            <button className="primary-btn" onClick={() => setSaveDialog({ title: 'Export Jupyter notebook', suggestedName: notebookName, loadFile: api.notebookFile })}><Download size={16}/> Export ipynb</button>
          </div>
        </header>

        <DatasetTabs
          workspace={workspace}
          onWorkspace={openWorkspace}
          onError={(text) => setToast({ type: 'error', text })}
        />

        <nav className="workspace-tabs" aria-label="Workspace sections">
          <button className={activeView === 'overview' ? 'active' : ''} onClick={() => setActiveView('overview')}><LayoutDashboard size={15}/> Overview</button>
          <button className={activeView === 'explore' ? 'active' : ''} onClick={() => setActiveView('explore')}><BarChart3 size={15}/> Explore & plot</button>
          <button className={activeView === 'history' ? 'active' : ''} onClick={() => setActiveView('history')}><GitBranch size={15}/> Sessions</button>
        </nav>

        {activeView === 'overview' && (
          <OverviewDashboard
            session={activeSession}
            provenance={workspace.datasets.find((dataset) => dataset.id === workspace.active_dataset_id)?.provenance}
            onSelectColumn={exploreColumn}
            onOpenExplore={exploreColumn}
            onApply={(operation, params) => handleWorkspaceUpdate(api.applyOperation(activeSessionId, operation, params))}
            onSaved={setWorkspace}
            onError={(text) => setToast({ type: 'error', text })}
          />
        )}

        {activeView === 'history' && (
          <SessionTree
            workspace={workspace}
            onActivate={activateSessionFromTree}
            onCreate={createSessionFromTree}
            onRename={renameSessionFromTree}
            onDelete={deleteSessionFromTree}
          />
        )}

        {activeView === 'explore' && (
          <section className="main-grid">
            <ColumnDetails
              key={`${activeSessionId}-${selectedColumn}`}
              stats={columnStats}
              column={selectedColumn}
              onApply={(operation, params) => handleWorkspaceUpdate(api.applyOperation(activeSessionId, operation, params))}
            />

            <div className="plot-canvas">
              {activeFigure?.id && activeFigure.image && (
                <section className="saved-figure-panel">
                  <div className="saved-figure-header">
                    <div>
                      <p className="eyebrow">Saved plot</p>
                      <strong>{activeFigure.savedTitle || 'Selected figure'}</strong>
                    </div>
                    <button className="icon-btn" type="button" onClick={() => setActiveFigure(null)} aria-label="Close saved plot preview">
                      <X size={15} />
                    </button>
                  </div>
                  <div className="plot-card active-figure image-preview-card">
                    <img className="plot-image" src={activeFigure.image} alt="Selected saved plot" />
                  </div>
                </section>
              )}
              <PlotBuilder
                key={`${activeSessionId}-${selectedColumn}`}
                column={selectedColumn}
                stats={columnStats}
                sessionId={activeSessionId}
                numericColumns={numericColumns}
                categoricalColumns={categoricalColumns}
                onPreview={setActiveFigure}
                onSaved={setWorkspace}
                onError={(text) => setToast({ type: 'error', text })}
              />
            </div>
          </section>
        )}
      </main>
      {saveDialog && (
        <SaveFileDialog
          config={saveDialog}
          onClose={() => setSaveDialog(null)}
          onSaved={(filename) => setToast({ type: 'success', text: `Saved ${filename}` })}
          onError={(text) => setToast({ type: 'error', text })}
        />
      )}
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
