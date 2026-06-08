import { Trash2 } from 'lucide-react';

export default function Sidebar({ workspace, selectedColumn, onSelectColumn, onDropColumn }) {
  const active = workspace.active_session;

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-dot" />
        <div>
          <strong>Danaleo</strong>
          <small>CSV workspace</small>
        </div>
      </div>

      <section className="sidebar-section grow">
        <p className="section-label">Columns</p>
        <div className="column-list">
          {active.columns.map((col) => (
            <div
              className={`column-item ${selectedColumn === col.name ? 'selected' : ''}`}
              key={col.name}
            >
              <button
                className="column-select-btn"
                type="button"
                onClick={() => onSelectColumn(col.name)}
                title={`View ${col.name}`}
              >
                <span>{col.name}</span>
                <small>{col.kind} · {col.missing_pct}% missing</small>
              </button>
              <button
                className="column-delete-btn"
                type="button"
                title={`Drop column: ${col.name}`}
                aria-label={`Drop column ${col.name}`}
                onClick={() => onDropColumn(col.name)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </aside>
  );
}
