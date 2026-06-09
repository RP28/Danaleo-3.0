import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Save, SlidersHorizontal, Trash2 } from 'lucide-react';
import { api } from '../api.js';

const numericPlotTypes = [
  ['histogram', 'Histogram'],
  ['kde', 'KDE'],
  ['box', 'Box plot'],
  ['violin', 'Violin plot'],
  ['scatter', 'Scatter relationship'],
  ['hexbin', 'Hexbin density'],
  ['line', 'Line relationship'],
  ['bar_top_n', 'Top-N bar'],
  ['pie_top_n', 'Top-N pie'],
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
const topNPlotTypes = new Set(['bar_top_n', 'pie_top_n']);
const relationshipPlotTypes = new Set(['scatter', 'hexbin', 'line']);
const noSubplotPlotTypes = new Set(['scatter', 'hexbin', 'line']);

function defaultControls() {
  return {
    bins: 30,
    top_n: 15,
    bw_adjust: 1.0,
    points: 160,
    fill: true,
    group_by: '',
    group_limit: 8,
    show_outliers: true,
    subplot_enabled: false,
    subplot_columns: [],
    subplot_cols: 2,
    subplot_limit: 12,
    compare_with: '',
    marker_size: 28,
    alpha: 0.72,
    gridsize: 30,
    sort_x: true,
    show_markers: true,
    orientation: 'vertical',
    sort_order: 'descending',
    show_grid: true,
    log_x: false,
    log_y: false,
    chart_title: ''
  };
}

function uniqueValues(values) {
  return values.filter((value, index, arr) => value && arr.indexOf(value) === index);
}

function LocalPlotBlock({
  column,
  stats,
  sessionId,
  numericColumns,
  categoricalColumns,
  localQuery,
  blockNumber,
  canRemove,
  onRemove,
  onPreview,
  onSaved,
  onError
}) {
  const actualTypes = useMemo(() => {
    return stats?.kind === 'numeric' ? numericPlotTypes : categoricalPlotTypes;
  }, [stats?.kind]);

  const [plotType, setPlotType] = useState(actualTypes[0]?.[0] || 'histogram');
  const [figure, setFigure] = useState(null);
  const [title, setTitle] = useState('');
  const [remark, setRemark] = useState('');
  const [include, setInclude] = useState(true);
  const [controls, setControls] = useState(() => defaultControls());
  const [expanded, setExpanded] = useState(true);

  const groupOptions = useMemo(() => {
    return categoricalColumns.filter((c) => c !== column);
  }, [categoricalColumns, column]);

  const subplotOptions = useMemo(() => {
    return stats?.kind === 'numeric' ? numericColumns : categoricalColumns;
  }, [categoricalColumns, numericColumns, stats?.kind]);

  const selectedSubplotColumns = useMemo(() => {
    return uniqueValues([column, ...(controls.subplot_columns || [])]).filter((c) =>
      subplotOptions.includes(c)
    );
  }, [column, controls.subplot_columns, subplotOptions]);

  const canUseGroupedPlots = stats?.kind === 'numeric' && groupOptions.length > 0;
  const canUseSubplots = subplotOptions.length > 1 && !noSubplotPlotTypes.has(plotType);
  const isGroupedPlot = groupedPlotTypes.has(plotType);
  const isKdePlot = kdePlotTypes.has(plotType);
  const isTopNPlot = topNPlotTypes.has(plotType);
  const isRelationshipPlot = relationshipPlotTypes.has(plotType);

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
      group_by: prev.group_by && groupOptions.includes(prev.group_by) ? prev.group_by : '',
      subplot_columns: []
    }));
  }, [column, groupOptions]);

  function updateControl(key, value) {
    setControls((prev) => ({ ...prev, [key]: value }));
  }

  function toggleSubplotColumn(nextColumn) {
    if (nextColumn === column) return;

    setControls((prev) => {
      const current = prev.subplot_columns || [];
      const exists = current.includes(nextColumn);

      return {
        ...prev,
        subplot_columns: exists
          ? current.filter((c) => c !== nextColumn)
          : [...current, nextColumn]
      };
    });
  }

  function buildPayload() {
    const nextControls = { ...controls };

    if (noSubplotPlotTypes.has(plotType)) {
      nextControls.subplot_enabled = false;
      nextControls.subplot_columns = [];
    }

    if (!isGroupedPlot) {
      nextControls.group_by = '';
    }

    if (isGroupedPlot && !nextControls.group_by) {
      throw new Error('Choose a categorical column in Group by');
    }

    if (isGroupedPlot && !canUseGroupedPlots) {
      throw new Error('Grouped plots need at least one categorical column');
    }

    if (isTopNPlot && Number(nextControls.top_n) < 1) {
      throw new Error('Top N must be at least 1');
    }

    if (isRelationshipPlot && !nextControls.compare_with) {
      throw new Error('Choose a numeric column in Compare with');
    }

    if (nextControls.subplot_enabled) {
      const selected = uniqueValues([column, ...(nextControls.subplot_columns || [])]).filter((c) =>
        subplotOptions.includes(c)
      );

      if (selected.length < 2) {
        throw new Error('Choose at least two columns for subplot mode');
      }

      nextControls.subplot_columns = selected;
    } else {
      nextControls.subplot_columns = [];
      nextControls.subplot_cols = 2;
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
    <details className="plot-block" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>
        <span>
          <strong>Plot {blockNumber}</strong>
          <small>{actualTypes.find(([key]) => key === plotType)?.[1]}</small>
        </span>
      </summary>
      <div className="plot-block-body">
        <div className="plot-block-toolbar">
          <select value={plotType} onChange={(e) => setPlotType(e.target.value)}>
            {actualTypes.map(([key, label]) => (
              <option key={key} value={key} disabled={groupedPlotTypes.has(key) && !canUseGroupedPlots}>
                {label}
                {groupedPlotTypes.has(key) && !canUseGroupedPlots ? ' (needs categorical column)' : ''}
              </option>
            ))}
          </select>

          <button className="ghost-btn" type="button" onClick={preview}>
            Preview
          </button>

          <button className="primary-btn" type="button" onClick={save}>
            <Save size={16} /> Save
          </button>
          {canRemove && (
            <button className="icon-btn danger-btn" type="button" onClick={onRemove} aria-label={`Remove plot ${blockNumber}`}>
              <Trash2 size={14} />
            </button>
          )}
        </div>

        <div className="builder-controls">
        {isRelationshipPlot && (
          <label>
            Compare with
            <select value={controls.compare_with} onChange={(e) => updateControl('compare_with', e.target.value)}>
              <option value="">Choose numeric column</option>
              {numericColumns.filter((c) => c !== column).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}

        {plotType === 'scatter' && groupOptions.length > 0 && (
          <label>
            Color by
            <select value={controls.group_by} onChange={(e) => updateControl('group_by', e.target.value)}>
              <option value="">No grouping</option>
              {groupOptions.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}

        {(plotType === 'scatter' || plotType === 'line') && (
          <label>
            Opacity
            <input type="number" min="0.05" max="1" step="0.05" value={controls.alpha} onChange={(e) => updateControl('alpha', Number(e.target.value))} />
          </label>
        )}

        {(plotType === 'scatter' || plotType === 'line') && (
          <label>
            Marker size
            <input type="number" min="4" max="300" value={controls.marker_size} onChange={(e) => updateControl('marker_size', Number(e.target.value))} />
          </label>
        )}

        {plotType === 'hexbin' && (
          <label>
            Grid density
            <input type="number" min="8" max="100" value={controls.gridsize} onChange={(e) => updateControl('gridsize', Number(e.target.value))} />
          </label>
        )}

        {plotType === 'line' && (
          <label className="check"><input type="checkbox" checked={!!controls.sort_x} onChange={(e) => updateControl('sort_x', e.target.checked)} /> sort by X</label>
        )}

        {plotType === 'line' && (
          <label className="check"><input type="checkbox" checked={!!controls.show_markers} onChange={(e) => updateControl('show_markers', e.target.checked)} /> show markers</label>
        )}

        {plotType === 'histogram' && (
          <label>
            Bins
            <input
              type="number"
              min="2"
              max="200"
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
            />
            show KDE
          </label>
        )}

        {isKdePlot && (
          <label>
            Bandwidth
            <input
              type="number"
              min="0.1"
              max="5"
              step="0.1"
              value={controls.bw_adjust}
              onChange={(e) => updateControl('bw_adjust', Number(e.target.value))}
            />
          </label>
        )}

        {isKdePlot && (
          <label>
            Points
            <input
              type="number"
              min="40"
              max="500"
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
            />
            fill curve
          </label>
        )}

        {isGroupedPlot && (
          <label>
            Group by
            <select
              value={controls.group_by}
              onChange={(e) => updateControl('group_by', e.target.value)}
            >
              <option value="">Choose category</option>
              {groupOptions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}

        {isGroupedPlot && (
          <label>
            Max groups
            <input
              type="number"
              min="2"
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
            />
            show outliers
          </label>
        )}

        {isTopNPlot && (
          <label>
            Top N
            <input
              type="number"
              min="1"
              max="100"
              value={controls.top_n}
              onChange={(e) => updateControl('top_n', Number(e.target.value))}
            />
          </label>
        )}

        {plotType === 'bar_top_n' && (
          <label>
            Orientation
            <select value={controls.orientation} onChange={(e) => updateControl('orientation', e.target.value)}>
              <option value="vertical">Vertical</option>
              <option value="horizontal">Horizontal</option>
            </select>
          </label>
        )}

        {plotType === 'bar_top_n' && (
          <label>
            Sort
            <select value={controls.sort_order} onChange={(e) => updateControl('sort_order', e.target.value)}>
              <option value="descending">Descending</option>
              <option value="ascending">Ascending</option>
              <option value="none">Original</option>
            </select>
          </label>
        )}
        </div>

      <details className="soft-details">
        <summary>Visual settings</summary>
        <div className="builder-controls">
          <label className="wide-control">
            Chart title
            <input value={controls.chart_title} onChange={(e) => updateControl('chart_title', e.target.value)} placeholder="Use the automatic title" />
          </label>
          <label className="check"><input type="checkbox" checked={!!controls.show_grid} onChange={(e) => updateControl('show_grid', e.target.checked)} /> show grid</label>
          <label className="check"><input type="checkbox" checked={!!controls.log_x} onChange={(e) => updateControl('log_x', e.target.checked)} /> log X axis</label>
          <label className="check"><input type="checkbox" checked={!!controls.log_y} onChange={(e) => updateControl('log_y', e.target.checked)} /> log Y axis</label>
        </div>
      </details>

      {canUseSubplots && (
        <details className="soft-details">
          <summary>Subplot mode</summary>

          <div className="builder-controls">
            <label className="check">
              <input
                type="checkbox"
                checked={!!controls.subplot_enabled}
                onChange={(e) => updateControl('subplot_enabled', e.target.checked)}
              />
              compare multiple columns as subplots
            </label>

            {controls.subplot_enabled && (
              <label>
                Columns per row
                <input
                  type="number"
                  min="1"
                  max="4"
                  value={controls.subplot_cols}
                  onChange={(e) => updateControl('subplot_cols', Number(e.target.value))}
                />
              </label>
            )}

            {controls.subplot_enabled && (
              <label>
                Max subplots
                <input
                  type="number"
                  min="2"
                  max="30"
                  value={controls.subplot_limit}
                  onChange={(e) => updateControl('subplot_limit', Number(e.target.value))}
                />
              </label>
            )}
          </div>

          {controls.subplot_enabled && (
            <div className="stack separated">
              <p className="muted">Selected columns: {selectedSubplotColumns.length}</p>

              <div className="builder-controls">
                {subplotOptions.map((c) => (
                  <label className="check" key={c}>
                    <input
                      type="checkbox"
                      checked={selectedSubplotColumns.includes(c)}
                      disabled={c === column}
                      onChange={() => toggleSubplotColumn(c)}
                    />
                    {c}
                    {c === column ? ' (current)' : ''}
                  </label>
                ))}
              </div>
            </div>
          )}
        </details>
      )}

      <details className="soft-details">
        <summary>Export settings for this plot</summary>

        <div className="builder-controls">
          <label className="wide-control">
            Saved plot title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Optional title"
            />
          </label>

          <label className="check">
            <input checked={include} onChange={(e) => setInclude(e.target.checked)} type="checkbox" />
            include in notebook export
          </label>

          <label className="wide-control">
            Remarks
            <textarea
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder="Optional notes to export as markdown"
            />
          </label>
        </div>
      </details>

      {figure?.image ? (
        <div className="plot-card preview-card image-preview-card">
          <img className="plot-image" src={figure.image} alt={`${plotType} preview for ${column}`} />
        </div>
      ) : (
        <div className="preview-placeholder">
          Preview appears here.
          <br />
          Local filters only affect this plot, not the session dataframe.
        </div>
      )}
      </div>
    </details>
  );
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
  const [localQuery, setLocalQuery] = useState('');
  const [plotBlocks, setPlotBlocks] = useState([1]);
  const nextBlockId = useRef(2);

  useEffect(() => {
    setLocalQuery('');
    setPlotBlocks([1]);
    nextBlockId.current = 2;
  }, [column, sessionId]);

  if (!column || !stats) {
    return (
      <section className="plot-builder">
        <h2>Select a column to begin</h2>
        <p className="muted">Plots, saved charts, and notebook export options will appear here.</p>
      </section>
    );
  }

  function addPlotBlock() {
    const id = nextBlockId.current;
    nextBlockId.current += 1;
    setPlotBlocks((current) => [...current, id]);
  }

  return (
    <section className="plot-builder">
      <div className="builder-header plot-builder-heading">
        <div>
          <p className="eyebrow"><SlidersHorizontal size={14} /> Local plot builder</p>
          <h2>{column}</h2>
        </div>
        <button className="primary-btn" type="button" onClick={addPlotBlock}>
          <Plus size={15} /> Add plot
        </button>
      </div>

      <label className="shared-query">
        <span>Shared local query</span>
        <input
          value={localQuery}
          onChange={(event) => setLocalQuery(event.target.value)}
          placeholder={`Optional, e.g. \`${column}\` > 0`}
        />
        <small>Applied to every plot block below without changing the session dataframe.</small>
      </label>

      <div className="plot-block-list">
        {plotBlocks.map((blockId, index) => (
          <LocalPlotBlock
            key={blockId}
            column={column}
            stats={stats}
            sessionId={sessionId}
            numericColumns={numericColumns}
            categoricalColumns={categoricalColumns}
            localQuery={localQuery}
            blockNumber={index + 1}
            canRemove={plotBlocks.length > 1}
            onRemove={() => setPlotBlocks((current) => current.filter((id) => id !== blockId))}
            onPreview={onPreview}
            onSaved={onSaved}
            onError={onError}
          />
        ))}
      </div>
    </section>
  );
}
