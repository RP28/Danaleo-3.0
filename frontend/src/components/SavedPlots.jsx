import { api } from '../api.js';

export default function SavedPlots({ plots, activeFigure, onSelectFigure, onWorkspaceUpdate, onError }) {
  async function toggle(plot) {
    try {
      const data = await api.updatePlot(plot.id, { include_in_export: !plot.include_in_export });
      onWorkspaceUpdate(data);
    } catch (err) { onError(err.message); }
  }

  return (
    <section className="saved-section">
      <div className="saved-header">
        <h2>Saved plots</h2>
        <span>{plots.length} saved</span>
      </div>
      {activeFigure?.image && (
        <div className="plot-card active-figure image-preview-card">
          <img className="plot-image" src={activeFigure.image} alt="Selected saved plot" />
        </div>
      )}
      <div className="saved-grid">
        {plots.map((plot) => (
          <article className="saved-card" key={plot.id}>
            <div>
              <strong>{plot.title}</strong>
              <small>{plot.session_name} · {plot.column} · {plot.plot_type}</small>
            </div>
            {plot.remark && <p>{plot.remark}</p>}
            <div className="row compact">
              <button className="ghost-btn" onClick={() => onSelectFigure(plot.figure)}>View</button>
              <button className={plot.include_in_export ? 'primary-btn' : 'ghost-btn'} onClick={() => toggle(plot)}>{plot.include_in_export ? 'In export' : 'Skip export'}</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
