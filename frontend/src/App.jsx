import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';
import UploadZone from './components/UploadZone.jsx';
import Sidebar from './components/Sidebar.jsx';
import ColumnDetails from './components/ColumnDetails.jsx';
import PlotBuilder from './components/PlotBuilder.jsx';
import SessionTree from './components/SessionTree.jsx';
import SavedPlots from './components/SavedPlots.jsx';
import Toast from './components/Toast.jsx';
import { Download } from 'lucide-react';


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
  }, [selectedColumn, activeSessionId]);

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

  if (!workspace?.ready) {
    return <UploadZone onUploaded={setWorkspace} onError={(text) => setToast({ type: 'error', text })} toast={toast} setToast={setToast} />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        workspace={workspace}
        selectedColumn={selectedColumn}
        onSelectColumn={setSelectedColumn}
        onDropColumn={(column) => {
          const message = `Drop column "${column}" from the current session?`;
          if (!window.confirm(message)) return;
          handleWorkspaceUpdate(api.applyOperation(activeSessionId, 'drop_column', { column }));
        }}
      />

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Danaleo 3.0</p>
            <h1>{workspace.csv_name}</h1>
          </div>
          <div className="topbar-actions">
            <button className="primary-btn" onClick={() => api.exportNotebook().catch((err) => setToast({ type: 'error', text: err.message }))}><Download size={16}/> Export ipynb</button>
          </div>
        </header>

        <SessionTree
          workspace={workspace}
          onActivate={activateSessionFromTree}
          onCreate={createSessionFromTree}
          onRename={renameSessionFromTree}
          onDelete={deleteSessionFromTree}
        />

        <section className="main-grid">
          <ColumnDetails
            stats={columnStats}
            column={selectedColumn}
            onApply={(operation, params) => handleWorkspaceUpdate(api.applyOperation(activeSessionId, operation, params))}
          />

          <div className="plot-canvas">
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
            <SavedPlots
              plots={workspace.saved_plots}
              activeFigure={activeFigure}
              onSelectFigure={setActiveFigure}
              onWorkspaceUpdate={setWorkspace}
              onError={(text) => setToast({ type: 'error', text })}
            />
          </div>
        </section>
      </main>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
