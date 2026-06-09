import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Database, GitMerge, Plus, Trash2, X } from 'lucide-react';
import { api } from '../api.js';

const joinTypes = [
  { value: 'inner', label: 'Inner', detail: 'Matching keys only' },
  { value: 'left', label: 'Left', detail: 'Keep every left row' },
  { value: 'right', label: 'Right', detail: 'Keep every right row' },
  { value: 'outer', label: 'Full outer', detail: 'Keep rows from both' },
  { value: 'cross', label: 'Cross', detail: 'Every row combination' },
];

function SourceCard({ side, datasets, datasetId, setDatasetId, detail, sessionId, setSessionId }) {
  const session = detail?.session_options.find((item) => item.id === sessionId);
  return (
    <article className={`merge-source-card ${side}`}>
      <div className="merge-source-icon"><Database size={24} /></div>
      <p className="eyebrow">{side} dataframe</p>
      <label>
        Dataset
        <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
          {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.csv_name}</option>)}
        </select>
      </label>
      <label>
        Session snapshot
        <select value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
          {(detail?.session_options || []).map((option) => (
            <option key={option.id} value={option.id}>{option.name} · {option.rows.toLocaleString()} rows</option>
          ))}
        </select>
      </label>
      <small>{session ? `${session.columns.length} columns selected for the merge` : 'Loading session columns…'}</small>
    </article>
  );
}

export default function MergeDatasetsModal({ workspace, onClose, onWorkspace, onError }) {
  const otherDataset = workspace.datasets.find((dataset) => dataset.id !== workspace.active_dataset_id);
  const [leftDatasetId, setLeftDatasetId] = useState(workspace.active_dataset_id);
  const [rightDatasetId, setRightDatasetId] = useState(otherDataset?.id || workspace.active_dataset_id);
  const [leftDetail, setLeftDetail] = useState(null);
  const [rightDetail, setRightDetail] = useState(null);
  const [leftSessionId, setLeftSessionId] = useState('');
  const [rightSessionId, setRightSessionId] = useState('');
  const [how, setHow] = useState('inner');
  const [keyPairs, setKeyPairs] = useState([{ left: '', right: '' }]);
  const [leftSuffix, setLeftSuffix] = useState('_left');
  const [rightSuffix, setRightSuffix] = useState('_right');
  const [validate, setValidate] = useState('');
  const [name, setName] = useState('merged.csv');
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let active = true;
    api.datasetDetail(leftDatasetId)
      .then((detail) => {
        if (!active) return;
        setLeftDetail(detail);
        setLeftSessionId(detail.active_session_id);
      })
      .catch((error) => onError(error.message));
    return () => { active = false; };
  }, [leftDatasetId, onError]);

  useEffect(() => {
    let active = true;
    api.datasetDetail(rightDatasetId)
      .then((detail) => {
        if (!active) return;
        setRightDetail(detail);
        setRightSessionId(detail.active_session_id);
      })
      .catch((error) => onError(error.message));
    return () => { active = false; };
  }, [rightDatasetId, onError]);

  const leftSession = leftDetail?.session_options.find((item) => item.id === leftSessionId);
  const rightSession = rightDetail?.session_options.find((item) => item.id === rightSessionId);

  useEffect(() => {
    if (how === 'cross' || !leftSession || !rightSession) return;
    const commonColumn = leftSession.columns.find((column) => rightSession.columns.includes(column));
    if (!commonColumn) return;
    setKeyPairs((pairs) => (
      pairs.length === 1 && !pairs[0].left && !pairs[0].right
        ? [{ left: commonColumn, right: commonColumn }]
        : pairs
    ));
  }, [how, leftSession, rightSession]);

  const payload = useMemo(() => ({
    left_session_id: leftSessionId,
    right_session_id: rightSessionId,
    how,
    left_on: how === 'cross' ? [] : keyPairs.map((pair) => pair.left),
    right_on: how === 'cross' ? [] : keyPairs.map((pair) => pair.right),
    suffixes: [leftSuffix, rightSuffix],
    validate: validate || null,
    name,
  }), [how, keyPairs, leftSessionId, leftSuffix, name, rightSessionId, rightSuffix, validate]);

  useEffect(() => { setPreview(null); }, [payload]);

  function updatePair(index, side, value) {
    setKeyPairs((pairs) => pairs.map((pair, pairIndex) => (
      pairIndex === index ? { ...pair, [side]: value } : pair
    )));
  }

  async function runPreview() {
    setLoadingPreview(true);
    try {
      setPreview(await api.previewMerge(payload));
    } catch (error) {
      onError(error.message);
    } finally {
      setLoadingPreview(false);
    }
  }

  async function createMerge() {
    setCreating(true);
    try {
      onWorkspace(await api.createMerge(payload), true);
      onClose();
    } catch (error) {
      onError(error.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="merge-modal" role="dialog" aria-modal="true" aria-label="Merge dataframes" onMouseDown={(event) => event.stopPropagation()}>
        <header className="merge-modal-header">
          <div>
            <p className="eyebrow"><GitMerge size={14} /> Dataframe merge</p>
            <h2>Combine two session snapshots</h2>
            <p className="muted">The result opens as a new independent dataset tab.</p>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close merge dialog"><X size={18} /></button>
        </header>

        <div className="merge-visual">
          <SourceCard
            side="left"
            datasets={workspace.datasets}
            datasetId={leftDatasetId}
            setDatasetId={setLeftDatasetId}
            detail={leftDetail}
            sessionId={leftSessionId}
            setSessionId={setLeftSessionId}
          />
          <div className="merge-flow-node">
            <ArrowRight size={20} />
            <span><GitMerge size={24} /></span>
            <ArrowRight size={20} />
            <strong>{how === 'outer' ? 'full outer' : how}</strong>
          </div>
          <SourceCard
            side="right"
            datasets={workspace.datasets}
            datasetId={rightDatasetId}
            setDatasetId={setRightDatasetId}
            detail={rightDetail}
            sessionId={rightSessionId}
            setSessionId={setRightSessionId}
          />
        </div>

        <div className="join-type-grid">
          {joinTypes.map((type) => (
            <button key={type.value} className={how === type.value ? 'active' : ''} onClick={() => setHow(type.value)}>
              <strong>{type.label}</strong>
              <small>{type.detail}</small>
            </button>
          ))}
        </div>

        {how !== 'cross' && (
          <section className="merge-key-section">
            <div className="panel-heading">
              <div><p className="eyebrow">Key mapping</p><h3>Columns used to match rows</h3></div>
              <button className="ghost-btn" onClick={() => setKeyPairs((pairs) => [...pairs, { left: '', right: '' }])}><Plus size={14} /> Add key</button>
            </div>
            <div className="merge-key-labels"><span>Left key</span><span>Right key</span><span /></div>
            {keyPairs.map((pair, index) => (
              <div className="merge-key-row" key={index}>
                <select value={pair.left} onChange={(event) => updatePair(index, 'left', event.target.value)}>
                  <option value="">Select left column</option>
                  {(leftSession?.columns || []).map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
                <select value={pair.right} onChange={(event) => updatePair(index, 'right', event.target.value)}>
                  <option value="">Select right column</option>
                  {(rightSession?.columns || []).map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
                <button
                  className="node-icon-btn danger"
                  disabled={keyPairs.length === 1}
                  onClick={() => setKeyPairs((pairs) => pairs.filter((_, pairIndex) => pairIndex !== index))}
                  aria-label="Remove join key"
                ><Trash2 size={14} /></button>
              </div>
            ))}
          </section>
        )}

        <section className="merge-settings">
          <label>Result name<input value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>Left suffix<input value={leftSuffix} onChange={(event) => setLeftSuffix(event.target.value)} /></label>
          <label>Right suffix<input value={rightSuffix} onChange={(event) => setRightSuffix(event.target.value)} /></label>
          <label>
            Validate relationship
            <select value={validate} onChange={(event) => setValidate(event.target.value)}>
              <option value="">No validation</option>
              <option value="one_to_one">One-to-one</option>
              <option value="one_to_many">One-to-many</option>
              <option value="many_to_one">Many-to-one</option>
              <option value="many_to_many">Many-to-many</option>
            </select>
          </label>
        </section>

        {preview && (
          <section className="merge-preview">
            <div className="merge-diagnostic-grid">
              <div><span>Result</span><strong>{preview.result_rows.toLocaleString()}</strong><small>{preview.result_columns} columns</small></div>
              <div><span>Matched</span><strong>{preview.matched_rows.toLocaleString()}</strong><small>rows from both</small></div>
              <div><span>Left only</span><strong>{preview.left_only_rows.toLocaleString()}</strong><small>unmatched left rows</small></div>
              <div><span>Right only</span><strong>{preview.right_only_rows.toLocaleString()}</strong><small>unmatched right rows</small></div>
            </div>
            <div className="table-scroll">
              <table>
                <thead><tr>{preview.columns.slice(0, 10).map((column) => <th key={column}>{column}</th>)}</tr></thead>
                <tbody>{preview.preview.map((row, index) => (
                  <tr key={index}>{preview.columns.slice(0, 10).map((column) => <td key={column}>{String(row[column] ?? '—')}</td>)}</tr>
                ))}</tbody>
              </table>
            </div>
          </section>
        )}

        <footer className="merge-modal-actions">
          <span className="muted">Inputs remain unchanged. The merged result is stored as its own snapshot.</span>
          <button className="ghost-btn" onClick={runPreview} disabled={loadingPreview}>{loadingPreview ? 'Calculating…' : 'Preview merge'}</button>
          <button className="primary-btn" onClick={createMerge} disabled={!preview || creating}>{creating ? 'Creating…' : 'Create merged tab'}</button>
        </footer>
      </section>
    </div>
  );
}
