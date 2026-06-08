import { useEffect, useMemo, useState } from 'react';

import { api } from '../api.js';
import { Save, SlidersHorizontal } from 'lucide-react';

const numericPlotTypes = [
  ['histogram', 'Histogram'],
  ['kde', 'KDE'],
  ['box', 'Box plot'],
  ['violin', 'Violin plot'],
  ['grouped_kde', 'KDE by category'],
  ['grouped_box', 'Box by category'],
  ['grouped_violin', 'Violin by category']
];

const categoricalPlotTypes = [
  ['bar_top_n', 'Top-N bar'],
  ['pie_top_n', 'Top-N pie']
];

const groupedPlotTypes = new Set(['grouped_kde', 'grouped_box', 'grouped_violin']);
const kdePlotTypes = new Set(['kde', 'grouped_kde']);

function defaultControls() {
  return {
    bins: 30,
    top_n: 15,
    bw_adjust: 1.0,
    points: 160,
    fill: true,
    group_by: '',
    group_limit: 8,
    show_outliers: true
  };
}

export default function PlotBuilder({
  column,
  stats,
  sessionId,
  numericColumns,
  categoricalColumns,
  onPreview,
  onSaved,
  onError
}) {
  const actualTypes = useMemo(() => {
    return stats?.kind === 'numeric' ? numericPlotTypes : categoricalPlotTypes;
  }, [stats?.kind]);

  const [plotType, setPlotType] = useState(actualTypes[0]?.[0] || 'histogram');
  const [localQuery, setLocalQuery] = useState('');
  const [figure, setFigure] = useState(null);
  const [title, setTitle] = useState('');
  const [remark, setRemark] = useState('');
  const [include, setInclude] = useState(true);
  const [controls, setControls] = useState(defaultControls);

  const groupOptions = useMemo(() => {
    return categoricalColumns.filter((c) => c !== column);
  }, [categoricalColumns, column]);

  const canUseGroupedPlots = stats?.kind === 'numeric' && groupOptions.length > 0;
  const isGroupedPlot = groupedPlotTypes.has(plotType);
  const isKdePlot = kdePlotTypes.has(plotType);

  useEffect(() => {
    const nextTypes = stats?.kind === 'numeric' ? numericPlotTypes : categoricalPlotTypes;
    const nextDefault = nextTypes[0]?.[0] || 'histogram';
    if (!nextTypes.some(([key]) => key === plotType)) {
      setPlotType(nextDefault);
    }
  }, [plotType, stats?.kind]);

  useEffect(() => {
    setFigure(null);
    setTitle('');
    setRemark('');
    setControls((prev) => ({
      ...defaultControls(),
      group_by: prev.group_by && groupOptions.includes(prev.group_by) ? prev.group_by : ''
    }));
  }, [column, groupOptions]);

  if (!column || !stats) {
    return (
      <section className="plot-builder empty-canvas">
        <h2>Select a column to begin</h2>
        <p>Plots, saved charts, and notebook export options will appear here.</p>
      </section>
    );
  }

  function updateControl(key, value) {
    setControls((prev) => ({ ...prev, [key]: value }));
  }

  function buildPayload() {
    const nextControls = { ...controls };

    if (!isGroupedPlot) {
      nextControls.group_by = '';
    }

    if (isGroupedPlot && !nextControls.group_by) {
      throw new Error('Choose a categorical column in Group by');
    }

    return {
      session_id: sessionId,
      column,
      plot_type: plotType,
      local_query: localQuery,
      controls: nextControls
    };
  }

  async function preview() {
    try {
      const payload = buildPayload();
      const fig = await api.previewPlot(payload);
      setFigure(fig);
      onPreview(fig);
    } catch (err) {
      onError(err.message);
    }
  }

  async function save() {
    try {
      const payload = buildPayload();
      const data = await api.savePlot({
        ...payload,
        include_in_export: include,
        remark,
        title
      });
      onSaved(data);
      setRemark('');
      setTitle('');
    } catch (err) {
      onError(err.message);
    }
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
            {actualTypes.map(([key, label]) => (
              <option value={key} key={key} disabled={groupedPlotTypes.has(key) && !canUseGroupedPlots}>
                {label}{groupedPlotTypes.has(key) && !canUseGroupedPlots ? ' (needs categorical column)' : ''}
              </option>
            ))}
          </select>
          <button className="primary-btn" onClick={preview}>Preview</button>
          <button className="ghost-btn" onClick={save}><Save size={15}/> Save</button>
        </div>
      </div>

      <div className="builder-controls">
        <label className="wide-control">Local filter query
          <input
            value={localQuery}
            onChange={(e) => setLocalQuery(e.target.value)}
            placeholder={`Optional, e.g. \`${column}\` > 0`}
          />
        </label>

        {plotType === 'histogram' && (
          <label>Bins
            <input
              type="number"
              min="2"
              value={controls.bins}
              onChange={(e) => updateControl('bins', Number(e.target.value))}
            />
          </label>
        )}

        {plotType === 'histogram' && (
          <label className="check">
            <input
              type="checkbox"
              checked={!!controls.show_kde}
              onChange={(e) => updateControl('show_kde', e.target.checked)}
            /> show KDE
          </label>
        )}

        {isKdePlot && (
          <label>Bandwidth
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={controls.bw_adjust}
              onChange={(e) => updateControl('bw_adjust', Number(e.target.value))}
            />
          </label>
        )}

        {isKdePlot && (
          <label>Points
            <input
              type="number"
              min="50"
              value={controls.points}
              onChange={(e) => updateControl('points', Number(e.target.value))}
            />
          </label>
        )}

        {isKdePlot && (
          <label className="check">
            <input
              type="checkbox"
              checked={!!controls.fill}
              onChange={(e) => updateControl('fill', e.target.checked)}
            /> fill curve
          </label>
        )}

        {isGroupedPlot && (
          <label>Group by
            <select value={controls.group_by} onChange={(e) => updateControl('group_by', e.target.value)}>
              <option value="">Choose category</option>
              {groupOptions.map((c) => <option value={c} key={c}>{c}</option>)}
            </select>
          </label>
        )}

        {isGroupedPlot && (
          <label>Max groups
            <input
              type="number"
              min="1"
              max="30"
              value={controls.group_limit}
              onChange={(e) => updateControl('group_limit', Number(e.target.value))}
            />
          </label>
        )}

        {(plotType === 'grouped_box' || plotType === 'grouped_violin') && (
          <label className="check">
            <input
              type="checkbox"
              checked={!!controls.show_outliers}
              onChange={(e) => updateControl('show_outliers', e.target.checked)}
            /> show outliers
          </label>
        )}

        {(plotType === 'bar_top_n' || plotType === 'pie_top_n') && (
          <label>Top N
            <input
              type="number"
              min="1"
              max="100"
              value={controls.top_n}
              onChange={(e) => updateControl('top_n', Number(e.target.value))}
            />
          </label>
        )}
      </div>

      {isGroupedPlot && (
        <p className="interaction-hint">
          Two-column plot: numeric value <strong>{column}</strong> grouped by categorical labels from <strong>{controls.group_by || '...'}</strong>.
        </p>
      )}

      <details className="soft-details">
        <summary>Export settings for this plot</summary>
        <div className="builder-controls">
          <label className="wide-control">Saved plot title
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional title"/>
          </label>
          <label className="check">
            <input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)}/> include in notebook export
          </label>
          <label className="wide-control">Remarks
            <textarea value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="Optional notes to export as markdown"/>
          </label>
        </div>
      </details>

      {figure?.image ? (
        <div className="plot-card preview-card image-preview-card">
          <img className="plot-image" src={figure.image} alt={`${plotType} preview for ${column}`} />
        </div>
      ) : (
        <div className="preview-placeholder">Preview appears here. Local filters only affect this plot, not the session dataframe.</div>
      )}
    </section>
  );
}