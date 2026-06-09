import { AlertTriangle, ArrowRight, BarChart3, Database, Grid3X3, Sparkles } from 'lucide-react';

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

export default function OverviewDashboard({ session, onSelectColumn, onOpenExplore }) {
  const profile = session.profile;
  const columns = session.columns;
  const interestingColumns = [...columns]
    .sort((left, right) => right.missing_pct - left.missing_pct || right.unique - left.unique)
    .slice(0, 6);

  return (
    <div className="overview-dashboard">
      <section className="hero-panel">
        <div>
          <p className="eyebrow"><Sparkles size={14} /> Start here</p>
          <h2>Understand the shape before choosing a chart.</h2>
          <p className="muted">
            This overview surfaces data quality, column roles, relationships, and a raw preview.
            Select any column to investigate it in detail.
          </p>
        </div>
        <button className="primary-btn" onClick={() => onOpenExplore(columns[0]?.name)}>
          Explore columns <ArrowRight size={16} />
        </button>
      </section>

      <section className="metric-grid">
        <Metric icon={<Database size={18} />} label="Rows" value={profile.rows.toLocaleString()} detail={`${profile.columns} columns`} />
        <Metric icon={<BarChart3 size={18} />} label="Numeric" value={profile.numeric_columns} detail={`${profile.categorical_columns} categorical`} />
        <Metric icon={<AlertTriangle size={18} />} label="Missing" value={`${profile.missing_pct}%`} detail={`${profile.missing_cells.toLocaleString()} cells`} />
        <Metric icon={<Grid3X3 size={18} />} label="Duplicates" value={profile.duplicate_rows.toLocaleString()} detail="exact duplicate rows" />
      </section>

      <section className="insight-grid">
        <article className="insight-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Quality scan</p>
              <h3>Columns needing attention</h3>
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
              <p className="eyebrow">Relationships</p>
              <h3>Strongest correlations</h3>
            </div>
            <span className="overview-pill">{profile.top_correlations.length} pairs</span>
          </div>
          {profile.top_correlations.length ? profile.top_correlations.slice(0, 6).map((item) => (
            <button className="insight-row" key={`${item.left}-${item.right}`} onClick={() => onSelectColumn(item.left)}>
              <span>{item.left} ↔ {item.right}</span>
              <strong>{item.value}</strong>
            </button>
          )) : <p className="empty-note">Add at least two numeric columns to compare relationships.</p>}
        </article>

        <article className="insight-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Suggested next</p>
              <h3>Interesting columns</h3>
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

      <section className="data-preview-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Raw check</p>
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
