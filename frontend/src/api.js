const API_BASE = import.meta.env.DEV ? 'http://127.0.0.1:8765' : '';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let message = `Request failed: ${res.status}`;
    try {
      const data = await res.json();
      message = data.detail || message;
    } catch (_) {}
    throw new Error(message);
  }
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return res.json();
  return res;
}

export const api = {
  workspace: () => request('/api/workspace'),
  resetWorkspace: () => request('/api/workspace/reset', { method: 'POST' }),
  upload: (formData) => request('/api/upload', { method: 'POST', body: formData }),
  activateDataset: (datasetId) => request('/api/datasets/activate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId })
  }),
  datasetDetail: (datasetId) => request(`/api/datasets/${datasetId}`),
  deleteDataset: (datasetId) => request(`/api/datasets/${datasetId}`, { method: 'DELETE' }),
  previewMerge: (payload) => request('/api/merges/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  createMerge: (payload) => request('/api/merges', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  loadProgress: (formData) => request('/api/progress/load', { method: 'POST', body: formData }),
  createSession: (name, parentId) => request('/api/sessions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: parentId })
  }),
  activateSession: (sessionId) => request('/api/sessions/activate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId })
  }),
  renameSession: (sessionId, name) => request(`/api/sessions/${sessionId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  }),
  deleteSession: (sessionId) => request(`/api/sessions/${sessionId}`, { method: 'DELETE' }),
  stats: (sessionId, column) => request(`/api/sessions/${sessionId}/columns/${encodeURIComponent(column)}/stats`),
  applyOperation: (sessionId, operationType, params) => request(`/api/sessions/${sessionId}/operations`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operation_type: operationType, params })
  }),
  previewPlot: (payload) => request('/api/plots/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  savePlot: (payload) => request('/api/plots/save', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  updatePlot: (plotId, payload) => request(`/api/plots/${plotId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),
  deletePlot: (plotId) => request(`/api/plots/${plotId}`, { method: 'DELETE' }),
  saveProgress: async () => {
    const res = await request('/api/progress/download');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const disposition = res.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="(.+)"/);
    a.download = match?.[1] || 'danaleo_progress.danaleo';
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
  exportNotebook: async () => {
    const res = await request('/api/export/notebook');
    const blob = await res.blob();

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');

    a.href = url;

    const disposition = res.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/);

    const headerFilename = match?.[1] || match?.[2];
    const fallbackFilename = blob.type.includes('zip')
      ? 'danaleo_eda_notebooks.zip'
      : 'danaleo_eda.ipynb';

    a.download = headerFilename
      ? decodeURIComponent(headerFilename)
      : fallbackFilename;

    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(url);
  }
};
