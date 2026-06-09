import { FilePlus2, GitMerge, X } from 'lucide-react';
import { useState } from 'react';
import { api } from '../api.js';
import MergeDatasetsModal from './MergeDatasetsModal.jsx';

export default function DatasetTabs({ workspace, onWorkspace, onError }) {
  const [showMerge, setShowMerge] = useState(false);
  async function uploadFiles(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    const form = new FormData();
    files.forEach((file) => form.append('file', file));
    try {
      onWorkspace(await api.upload(form), true);
    } catch (error) {
      onError(error.message);
    }
  }

  async function activate(datasetId) {
    if (datasetId === workspace.active_dataset_id) return;
    try {
      onWorkspace(await api.activateDataset(datasetId), true);
    } catch (error) {
      onError(error.message);
    }
  }

  async function remove(event, dataset) {
    event.stopPropagation();
    if (!window.confirm(`Remove "${dataset.csv_name}" and all of its sessions and saved plots?`)) return;
    try {
      onWorkspace(await api.deleteDataset(dataset.id), true);
    } catch (error) {
      onError(error.message);
    }
  }

  return (
    <nav className="dataset-tabs" aria-label="CSV datasets">
      <div className="dataset-tab-scroll">
        {workspace.datasets.map((dataset) => (
          <div
            key={dataset.id}
            className={`dataset-tab ${dataset.id === workspace.active_dataset_id ? 'active' : ''}`}
          >
            <button type="button" className="dataset-tab-main" onClick={() => activate(dataset.id)}>
              <strong>{dataset.csv_name}</strong>
              <small>{dataset.provenance?.type === 'merge' ? 'merge result · ' : ''}{dataset.rows.toLocaleString()} rows · {dataset.columns} cols</small>
            </button>
            <button
              type="button"
              className="dataset-tab-close"
              aria-label={`Remove ${dataset.csv_name}`}
              onClick={(event) => remove(event, dataset)}
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
      {workspace.datasets.length > 1 && (
        <button className="ghost-btn dataset-merge" onClick={() => setShowMerge(true)}>
          <GitMerge size={15} /> Merge
        </button>
      )}
      <label className="ghost-btn dataset-add">
        <FilePlus2 size={15} /> Add CSVs
        <input type="file" accept=".csv,text/csv" multiple onChange={uploadFiles} />
      </label>
      {showMerge && (
        <MergeDatasetsModal
          workspace={workspace}
          onClose={() => setShowMerge(false)}
          onWorkspace={onWorkspace}
          onError={onError}
        />
      )}
    </nav>
  );
}
