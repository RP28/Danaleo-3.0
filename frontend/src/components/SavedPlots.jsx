import { api } from '../api.js';
import { Eye, FileCheck2, FileX2, Trash2 } from 'lucide-react';

export default function SavedPlots({ plots, activeFigure, onSelectFigure, onWorkspaceUpdate, onError }) {
  const globalPlotTypes = new Set(['correlation_heatmap', 'missing_values']);
  function select(plot) {
    onSelectFigure({ ...plot.figure, id: plot.id, savedTitle: plot.title });
  }

  async function toggle(plot) {
    try {
      const data = await api.updatePlot(plot.id, { include_in_export: !plot.include_in_export });
      onWorkspaceUpdate(data);
    } catch (err) { onError(err.message); }
  }

  async function remove(plot) {
    if (!window.confirm(`Delete saved plot "${plot.title}"?`)) return;
    try {
      const data = await api.deletePlot(plot.id);
      if (activeFigure?.id === plot.id) onSelectFigure(null);
      onWorkspaceUpdate(data);
    } catch (err) { onError(err.message); }
  }

  return (
    <section className="saved-section">
      <div className="saved-header">
        <p className="section-label">Saved plots</p>
        <span>{plots.length}</span>
      </div>
      <div className="saved-grid">
        {plots.length === 0 && <p className="saved-empty">Saved plots will appear here.</p>}
        {plots.map((plot) => (
          <article className={`saved-card ${activeFigure?.id === plot.id ? 'selected' : ''}`} key={plot.id}>
            <button className="saved-card-main" type="button" onClick={() => select(plot)}>
              <strong>{plot.title}</strong>
              <small>{plot.session_name} · {globalPlotTypes.has(plot.plot_type) ? 'full dataset' : plot.column} · {plot.plot_type}</small>
            </button>
            <div className="saved-card-actions">
              <button className="icon-btn" type="button" onClick={() => select(plot)} title="View plot" aria-label={`View ${plot.title}`}><Eye size={14}/></button>
              <button className={`icon-btn ${plot.include_in_export ? 'included' : ''}`} type="button" onClick={() => toggle(plot)} title={plot.include_in_export ? 'In export' : 'Skip export'} aria-label={`Toggle export for ${plot.title}`}>
                {plot.include_in_export ? <FileCheck2 size={14}/> : <FileX2 size={14}/>}
              </button>
              <button className="icon-btn danger-btn" type="button" onClick={() => remove(plot)} aria-label={`Delete ${plot.title}`}><Trash2 size={14}/></button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
