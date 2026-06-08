import { useState } from 'react';
import { Upload, Database } from 'lucide-react';
import { api } from '../api.js';
import Toast from './Toast.jsx';

export default function UploadZone({ onUploaded, onError, toast, setToast }) {
  const [file, setFile] = useState(null);
  const [sampleMode, setSampleMode] = useState('none');
  const [sampleN, setSampleN] = useState(10000);
  const [sampleFrac, setSampleFrac] = useState(0.2);
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!file) return onError('Choose a CSV file first');
    const form = new FormData();
    form.append('file', file);
    form.append('sample_mode', sampleMode);
    if (sampleMode === 'n') form.append('sample_n', sampleN);
    if (sampleMode === 'frac') form.append('sample_frac', sampleFrac);
    setLoading(true);
    try {
      const data = await api.upload(form);
      onUploaded(data);
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="upload-page">
      <div className="upload-card">
        <div className="brand-mark"><Database size={28}/></div>
        <p className="eyebrow">Danaleo 3.0</p>
        <h1>Interactive EDA workspace</h1>
        <p className="muted wide">Upload a single CSV file. After upload, this screen disappears and the workspace opens.</p>
        <form onSubmit={submit} className="upload-form">
          <label className="dropzone">
            <Upload size={30}/>
            <span>{file ? file.name : 'Click to choose a CSV file'}</span>
            <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0])}/>
          </label>

          <details className="soft-details">
            <summary>Large file sampling options</summary>
            <div className="row compact">
              <label><input type="radio" checked={sampleMode === 'none'} onChange={() => setSampleMode('none')}/> No sampling</label>
              <label><input type="radio" checked={sampleMode === 'n'} onChange={() => setSampleMode('n')}/> Sample N rows</label>
              <label><input type="radio" checked={sampleMode === 'frac'} onChange={() => setSampleMode('frac')}/> Sample fraction</label>
            </div>
            {sampleMode === 'n' && <input type="number" min="1" value={sampleN} onChange={(e) => setSampleN(e.target.value)} />}
            {sampleMode === 'frac' && <input type="number" min="0.01" max="0.99" step="0.01" value={sampleFrac} onChange={(e) => setSampleFrac(e.target.value)} />}
          </details>

          <button className="primary-btn large" disabled={loading}>{loading ? 'Loading…' : 'Open workspace'}</button>
        </form>
      </div>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
