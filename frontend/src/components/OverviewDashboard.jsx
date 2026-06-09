import { AlertTriangle, ArrowRight, BarChart3, Database, GitMerge, Grid3X3 } from 'lucide-react';
import DatasetPlotBuilder from './DatasetPlotBuilder.jsx';

function Metric({ icon, label, value, detail }) {
  return (
    <article className="metric-card">
      <span className="metric-icon">{icon}</span>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

export default function OverviewDashboard({ session, provenance, onSelectColumn, onOpenExplore, onApply, onSaved, onError }) {
  const profile = session.profile;
  const columns = session.columns;
  const interestingColumns = [...columns]
    .sort((left, right) => right.missing_pct - left.missing_pct || right.unique - left.unique)
    .slice(0, 6);

  return (
    <div className="overview-dashboard">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Dataset profile</p>
          <h2>{session.name}</h2>
          <p className="muted">{profile.rows.toLocaleString()} observations across {profile.columns} variables.</p>
        </div>
        <button className="primary-btn" onClick={() => onOpenExplore(columns[0]?.name)}>
          Explore columns <ArrowRight size={16} />
        </button>
      </section>

      {provenance?.type === 'merge' && (
        <section className="merge-provenance-banner">
          <div className="merge-provenance-source">
            <Database size={17} />
            <span><strong>{provenance.left_dataset_name}</strong><small>{provenance.left_session_name}</small></span>
          </div>
          <div className="merge-provenance-operation">
            <GitMerge size={18} />
            <strong>{provenance.how === 'outer' ? 'full outer' : provenance.how} join</strong>
            <small>{provenance.left_on.length ? provenance.left_on.map((key, index) => `${key} → ${provenance.right_on[index]}`).join(', ') : 'cross product'}</small>
          </div>
          <div className="merge-provenance-source">
            <Database size={17} />
            <span><strong>{provenance.right_dataset_name}</strong><small>{provenance.right_session_name}</small></span>
          </div>
        </section>
      )}

      <section className="metric-grid">
        <Metric icon={<Database size={18} />} label="Rows" value={profile.rows.toLocaleString()} detail={`${profile.columns} columns`} />
        <Metric icon={<BarChart3 size={18} />} label="Numeric" value={profile.numeric_columns} detail={`${profile.categorical_columns} categorical`} />
        <Metric icon={<AlertTriangle size={18} />} label="Missing" value={`${profile.missing_pct}%`} detail={`${profile.missing_cells.toLocaleString()} cells`} />
        <article className="metric-card metric-action-card">
          <span className="metric-icon"><Grid3X3 size={18} /></span>
          <div>
            <span>Duplicates</span>
            <strong>{profile.duplicate_rows.toLocaleString()}</strong>
            <small>exact duplicate rows</small>
          </div>
          <button
            className="ghost-btn"
            disabled={!profile.duplicate_rows}
            onClick={() => {
              if (window.confirm(`Drop ${profile.duplicate_rows.toLocaleString()} exact duplicate row(s) from the active session?`)) {
                onApply('drop_duplicates', {});
              }
            }}
          >
            Drop duplicates
          </button>
        </article>
      </section>

      <section className="insight-grid">
        <article className="insight-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Missingness analysis</p>
              <h3>Variables with missing values</h3>
            </div>
            <span className="overview-pill">{profile.high_missing.length} flagged</span>
          </div>
          {profile.high_missing.length ? profile.high_missing.map((item) => (
            <button className="insight-row" key={item.name} onClick={() => onSelectColumn(item.name)}>
              <span>{item.name}</span>
              <strong>{item.missing_pct}% missing</strong>
            </button>
          )) : <p className="empty-note">No missing values detected.</p>}
        </article>

        <article className="insight-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Numeric associations</p>
              <h3>Highest absolute Pearson correlations</h3>
            </div>
            <span className="overview-pill">{profile.top_correlations.length} pairs</span>
          </div>
          {profile.top_correlations.length ? profile.top_correlations.slice(0, 6).map((item) => (
            <button className="insight-row" key={`${item.left}-${item.right}`} onClick={() => onSelectColumn(item.left)}>
              <span>{item.left} ↔ {item.right}</span>
              <strong>{item.value}</strong>
            </button>
          )) : <p className="empty-note">Pearson correlation requires at least two numeric variables.</p>}
        </article>

        <article className="insight-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Column diagnostics</p>
              <h3>Highest missingness or cardinality</h3>
            </div>
          </div>
          {interestingColumns.map((column) => (
            <button className="insight-row" key={column.name} onClick={() => onSelectColumn(column.name)}>
              <span>{column.name}</span>
              <strong>{column.kind} · {column.unique.toLocaleString()} unique</strong>
            </button>
          ))}
        </article>
      </section>

      <DatasetPlotBuilder
        key={session.id}
        sessionId={session.id}
        anchorColumn={columns[0]?.name}
        onSaved={onSaved}
        onError={onError}
      />

      <section className="data-preview-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Data preview</p>
            <h3>First {profile.preview.length} rows</h3>
          </div>
          <span className="overview-pill">showing up to 12 columns</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr>{profile.preview_columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
            <tbody>
              {profile.preview.map((row, index) => (
                <tr key={index}>
                  {profile.preview_columns.map((column) => <td key={column}>{String(row[column] ?? '—')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
