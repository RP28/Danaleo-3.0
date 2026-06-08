import { useMemo, useState } from 'react';
import { api } from '../api.js';
import { Save, SlidersHorizontal } from 'lucide-react';

const numericPlotTypes = [
  ['histogram', 'Histogram'],
  ['kde', 'KDE'],
  ['box', 'Box plot'],
  ['violin', 'Violin plot']
];

const categoricalPlotTypes = [
  ['bar_top_n', 'Top-N bar'],
  ['pie_top_n', 'Top-N pie']
];

export default function PlotBuilder({ column, stats, sessionId, numericColumns, categoricalColumns, onPreview, onSaved, onError }) {
  const availableTypes = stats?.kind === 'numeric' ? numericPlotTypes : categoricalPlotTypes;
  const [plotType, setPlotType] = useState(availableTypes[0]?.[0] || 'histogram');
  const [localQuery, setLocalQuery] = useState('');
  const [figure, setFigure] = useState(null);
  const [title, setTitle] = useState('');
  const [remark, setRemark] = useState('');
  const [include, setInclude] = useState(true);
  const [controls, setControls] = useState({ bins: 30, top_n: 15, bw_adjust: 1.0, points: 160, fill: true, split_by: '' });

  const splitOptions = useMemo(() => categoricalColumns.filter((c) => c !== column), [categoricalColumns, column]);

  if (!column || !stats) {
    return (
      <section className="plot-builder empty-canvas">
        <h2>Select a column to begin</h2>
        <p>Plots, saved charts, and notebook export options will appear here.</p>
      </section>
    );
  }

  const actualTypes = stats.kind === 'numeric' ? numericPlotTypes : categoricalPlotTypes;
  if (!actualTypes.some(([key]) => key === plotType)) setPlotType(actualTypes[0][0]);

  function updateControl(key, value) {
    setControls((prev) => ({ ...prev, [key]: value }));
  }

  async function preview() {
    try {
      const payload = { session_id: sessionId, column, plot_type: plotType, local_query: localQuery, controls };
      const fig = await api.previewPlot(payload);
      setFigure(fig);
      onPreview(fig);
    } catch (err) { onError(err.message); }
  }

  async function save() {
    try {
      const data = await api.savePlot({ session_id: sessionId, column, plot_type: plotType, local_query: localQuery, controls, include_in_export: include, remark, title });
      onSaved(data);
      setRemark('');
      setTitle('');
    } catch (err) { onError(err.message); }
  }

  return (
    <section className="plot-builder">
      <div className="builder-header">
        <div>
          <p className="eyebrow"><SlidersHorizontal size={13}/> Local plot builder</p>
          <h2>{column}</h2>
        </div>
        <div className="row compact">
          <select value={plotType} onChange={(e) => setPlotType(e.target.value)}>
            {actualTypes.map(([key, label]) => <option value={key} key={key}>{label}</option>)}
          </select>
          <button className="primary-btn" onClick={preview}>Preview</button>
          <button className="ghost-btn" onClick={save}><Save size={15}/> Save</button>
        </div>
      </div>

      <div className="builder-controls">
        <label className="wide-control">Local filter query
          <input value={localQuery} onChange={(e) => setLocalQuery(e.target.value)} placeholder={`Optional, e.g. \`${column}\` > 0`} />
        </label>
        {plotType === 'histogram' && <label>Bins<input type="number" min="2" value={controls.bins} onChange={(e) => updateControl('bins', Number(e.target.value))}/></label>}
        {plotType === 'histogram' && <label className="check"><input type="checkbox" checked={!!controls.show_kde} onChange={(e) => updateControl('show_kde', e.target.checked)}/> show KDE</label>}
        {plotType === 'kde' && <label>Bandwidth<input type="number" min="0.1" step="0.1" value={controls.bw_adjust} onChange={(e) => updateControl('bw_adjust', Number(e.target.value))}/></label>}
        {plotType === 'kde' && <label>Points<input type="number" min="50" value={controls.points} onChange={(e) => updateControl('points', Number(e.target.value))}/></label>}
        {(plotType === 'box' || plotType === 'violin') && <label>Split by<select value={controls.split_by} onChange={(e) => updateControl('split_by', e.target.value)}><option value="">None</option>{splitOptions.map((c) => <option key={c}>{c}</option>)}</select></label>}
        {(plotType === 'bar_top_n' || plotType === 'pie_top_n') && <label>Top N<input type="number" min="1" max="100" value={controls.top_n} onChange={(e) => updateControl('top_n', Number(e.target.value))}/></label>}
      </div>

      <details className="soft-details">
        <summary>Export settings for this plot</summary>
        <div className="builder-controls">
          <label className="wide-control">Saved plot title<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional title"/></label>
          <label className="check"><input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)}/> include in notebook export</label>
          <label className="wide-control">Remarks<textarea value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="Optional notes to export as markdown"/></label>
        </div>
      </details>

      {figure?.image ? (
        <div className="plot-card preview-card image-preview-card">
          <img className="plot-image" src={figure.image} alt={`${plotType} preview for ${column}`} />
        </div>
      ) : <div className="preview-placeholder">Preview appears here. Local filters only affect this plot, not the session dataframe.</div>}
    </section>
  );
}
