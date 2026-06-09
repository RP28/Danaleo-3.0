import { useMemo, useState } from 'react';
import { Search, Trash2 } from 'lucide-react';

export default function Sidebar({ workspace, selectedColumn, onSelectColumn, onDropColumn, savedPlots }) {
  const active = workspace.active_session;
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const visibleColumns = useMemo(() => active.columns.filter((column) => {
    const matchesQuery = column.name.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (kind === 'all' || column.kind === kind);
  }), [active.columns, kind, query]);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-dot" />
        <div>
          <strong>Danaleo</strong>
          <small>Data workspace</small>
        </div>
      </div>

      <section className="sidebar-section grow">
        <div className="column-heading">
          <p className="section-label">Columns <span>{visibleColumns.length}/{active.columns.length}</span></p>
          <span>{active.overview.rows.toLocaleString()} rows</span>
        </div>
        <label className="column-search">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a column" />
        </label>
        <div className="kind-filter">
          {['all', 'numeric', 'categorical', 'datetime'].map((value) => (
            <button key={value} className={kind === value ? 'active' : ''} onClick={() => setKind(value)}>{value}</button>
          ))}
        </div>
        <div className="column-list">
          {visibleColumns.map((col) => (
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
        {savedPlots}
      </section>
    </aside>
  );
}
