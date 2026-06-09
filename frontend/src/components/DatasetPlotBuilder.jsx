import { useState } from 'react';
import { Save } from 'lucide-react';
import { api } from '../api.js';

const plotTypes = [
  ['correlation_heatmap', 'Pearson correlation heatmap'],
  ['missing_values', 'Missing-values overview'],
];

export default function DatasetPlotBuilder({ sessionId, anchorColumn, onSaved, onError }) {
  const [plotType, setPlotType] = useState('correlation_heatmap');
  const [figure, setFigure] = useState(null);
  const [controls, setControls] = useState({
    correlation_limit: 16,
    show_values: true,
    top_n: 20,
    include_complete: false,
    show_grid: true,
  });

  function updateControl(key, value) {
    setControls((current) => ({ ...current, [key]: value }));
  }

  function payload() {
    return {
      session_id: sessionId,
      column: anchorColumn,
      plot_type: plotType,
      local_query: '',
      controls,
    };
  }

  async function preview() {
    try {
      setFigure(await api.previewPlot(payload()));
    } catch (error) {
      onError(error.message);
    }
  }

  async function save() {
    try {
      const next = await api.savePlot({
        ...payload(),
        include_in_export: true,
        remark: '',
        title: plotTypes.find(([key]) => key === plotType)?.[1],
      });
      onSaved(next);
    } catch (error) {
      onError(error.message);
    }
  }

  return (
    <section className="dataset-plot-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Dataset plots</p>
          <h3>Global diagnostics</h3>
        </div>
        <div className="row compact">
          <button className="ghost-btn" onClick={preview}>Preview</button>
          <button className="primary-btn" onClick={save}><Save size={15} /> Save</button>
        </div>
      </div>

      <div className="builder-controls">
        <label>
          Plot
          <select value={plotType} onChange={(event) => setPlotType(event.target.value)}>
            {plotTypes.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>

        {plotType === 'correlation_heatmap' && (
          <label>
            Max numeric columns
            <input type="number" min="2" max="40" value={controls.correlation_limit} onChange={(event) => updateControl('correlation_limit', Number(event.target.value))} />
          </label>
        )}
        {plotType === 'correlation_heatmap' && (
          <label className="check"><input type="checkbox" checked={controls.show_values} onChange={(event) => updateControl('show_values', event.target.checked)} /> show coefficients</label>
        )}
        {plotType === 'missing_values' && (
          <label>
            Max columns
            <input type="number" min="1" max="100" value={controls.top_n} onChange={(event) => updateControl('top_n', Number(event.target.value))} />
          </label>
        )}
        {plotType === 'missing_values' && (
          <label className="check"><input type="checkbox" checked={controls.include_complete} onChange={(event) => updateControl('include_complete', event.target.checked)} /> include complete columns</label>
        )}
      </div>

      {figure?.image && (
        <div className="plot-card image-preview-card">
          <img className="plot-image" src={figure.image} alt={plotTypes.find(([key]) => key === plotType)?.[1]} />
        </div>
      )}
    </section>
  );
}
