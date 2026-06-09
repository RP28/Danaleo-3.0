import { useState } from 'react';
import { Wand2 } from 'lucide-react';

function StatLine({ label, value }) {
  return <div className="stat-line"><span>{label}</span><strong>{String(value ?? '—')}</strong></div>;
}

export default function ColumnDetails({ stats, column, onApply }) {
  const [filterQuery, setFilterQuery] = useState('');
  const [oldValue, setOldValue] = useState('');
  const [newValue, setNewValue] = useState('');
  const [multiple, setMultiple] = useState(false);
  const [replacementMethod, setReplacementMethod] = useState('constant');
  const [imputationMethod, setImputationMethod] = useState(stats?.kind === 'numeric' ? 'mean' : 'mode');
  const [imputationValue, setImputationValue] = useState('');
  const [transformationMethod, setTransformationMethod] = useState(stats?.kind === 'numeric' ? 'min_max' : 'one_hot');
  const [ordinalOrder, setOrdinalOrder] = useState('');

  if (!column || !stats) {
    return <aside className="details-panel empty"><p>Select a column to see stats, operations, and plot options.</p></aside>;
  }

  const topValues = stats.stats?.top_values || [];

  return (
    <aside className="details-panel">
      <div className="panel-title">
        <div>
          <p className="eyebrow">Column</p>
          <h2>{column}</h2>
        </div>
        <span className="kind-badge">{stats.kind}</span>
      </div>

      <details className="soft-details" key={`${column}-basic-stats`}>
        <summary>Basic statistics</summary>
        <div className="stats-grid">
          <StatLine label="dtype" value={stats.dtype}/>
          <StatLine label="rows" value={stats.rows.toLocaleString()}/>
          <StatLine label="missing" value={`${stats.missing.toLocaleString()} (${stats.missing_pct}%)`}/>
          <StatLine label="unique" value={stats.unique.toLocaleString()}/>
          {stats.kind === 'numeric' && Object.entries(stats.stats || {}).map(([k, v]) => <StatLine key={k} label={k} value={Number.isFinite(v) ? Number(v).toFixed(4) : v}/>) }
        </div>
      </details>

      {topValues.length > 0 && (
        <details className="soft-details" key={`${column}-top-values`}>
          <summary>Top values</summary>
          <div className="top-values">
            {topValues.slice(0, 10).map((item) => <StatLine key={item.value} label={item.value} value={item.count}/>) }
          </div>
        </details>
      )}

      <details className="soft-details" key={`${column}-operations`}>
        <summary>Column operations in current session</summary>
        <div className="stack">
          <label>Filter rows with pandas query</label>
          <textarea placeholder={`Example: \`${column}\` > 0`} value={filterQuery} onChange={(e) => setFilterQuery(e.target.value)} />
          <button className="primary-btn" onClick={() => onApply('filter_rows', { query: filterQuery })}><Wand2 size={15}/> Apply filter</button>
          <button className="ghost-btn danger" onClick={() => onApply('drop_missing', { column })}>Drop missing in this column</button>
        </div>
        <div className="stack separated">
          <label>Replace values in this column</label>
          <input placeholder="Old value" value={oldValue} onChange={(e) => setOldValue(e.target.value)} />
          <select value={replacementMethod} onChange={(event) => setReplacementMethod(event.target.value)}>
            <option value="constant">Custom value</option>
            <option value="nan">NaN (missing value)</option>
            {stats.kind === 'numeric' && <option value="mean">Mean of remaining values</option>}
            {stats.kind === 'numeric' && <option value="median">Median of remaining values</option>}
            <option value="mode">Mode of remaining values</option>
          </select>
          {replacementMethod === 'constant' && (
            <input placeholder="New value" value={newValue} onChange={(e) => setNewValue(e.target.value)} />
          )}
          <label className="check"><input type="checkbox" checked={multiple} onChange={(e) => setMultiple(e.target.checked)}/> comma-separated multiple replace</label>
          <button
            className="ghost-btn"
            onClick={() => onApply('replace_values', {
              column,
              old_value: oldValue,
              new_value: newValue,
              multiple,
              replacement_method: replacementMethod,
            })}
          >
            Replace
          </button>
        </div>
        <div className="stack separated">
          <label>Impute missing values</label>
          <select value={imputationMethod} onChange={(event) => setImputationMethod(event.target.value)}>
            {stats.kind === 'numeric' && <option value="mean">Mean</option>}
            {stats.kind === 'numeric' && <option value="median">Median</option>}
            <option value="mode">Mode (most frequent)</option>
            <option value="constant">Constant value</option>
            <option value="forward_fill">Forward fill</option>
            <option value="backward_fill">Backward fill</option>
            {stats.kind === 'numeric' && <option value="interpolate">Linear interpolation</option>}
          </select>
          {imputationMethod === 'constant' && (
            <input placeholder="Replacement value" value={imputationValue} onChange={(event) => setImputationValue(event.target.value)} />
          )}
          <small className="muted">Current missing values: {stats.missing.toLocaleString()}</small>
          <button
            className="ghost-btn"
            disabled={!stats.missing}
            onClick={() => onApply('impute_missing', { column, method: imputationMethod, value: imputationValue })}
          >
            <Wand2 size={15}/> Impute missing values
          </button>
        </div>
        <div className="stack separated">
          <label>Transform this column</label>
          <select value={transformationMethod} onChange={(event) => setTransformationMethod(event.target.value)}>
            {stats.kind !== 'numeric' && <option value="one_hot">One-hot encoding</option>}
            {stats.kind !== 'numeric' && <option value="ordinal">Ordinal encoding</option>}
            {stats.kind === 'numeric' && <option value="min_max">Min-max scaling (0 to 1)</option>}
            {stats.kind === 'numeric' && <option value="standardize">Standardization (z-score)</option>}
          </select>
          {transformationMethod === 'ordinal' && (
            <>
              <input
                placeholder="Optional order: low, medium, high"
                value={ordinalOrder}
                onChange={(event) => setOrdinalOrder(event.target.value)}
              />
              <small className="muted">Leave blank to encode values in a stable sorted order.</small>
            </>
          )}
          {transformationMethod === 'one_hot' && (
            <small className="muted">Creates one binary column per category and removes this source column.</small>
          )}
          <button
            className="ghost-btn"
            onClick={() => onApply('transform_column', {
              column,
              method: transformationMethod,
              order: ordinalOrder,
            })}
          >
            <Wand2 size={15}/> Apply transformation
          </button>
        </div>
      </details>
    </aside>
  );
}
