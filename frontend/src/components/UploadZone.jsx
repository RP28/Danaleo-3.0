import { useState } from 'react';
import { Upload, Database, FileUp } from 'lucide-react';
import { api } from '../api.js';
import Toast from './Toast.jsx';

const DATA_FILE_ACCEPT = '.csv,.tsv,.tab,.txt,.json,.jsonl,.ndjson,.xlsx,.xls,.xlsm,.xlsb,.ods,.parquet,.pq,.feather,.arrow,.orc,.dta,.sas7bdat,.xpt,.h5,.hdf,.hdf5,.gz,.bz2,.xz,.zip';

export default function UploadZone({ onUploaded, onError, toast, setToast }) {
  const [files, setFiles] = useState([]);
  const [sampleMode, setSampleMode] = useState('none');
  const [sampleN, setSampleN] = useState(10000);
  const [sampleFrac, setSampleFrac] = useState(0.2);
  const [loading, setLoading] = useState(false);
  const [progressFile, setProgressFile] = useState(null);
  const [loadingProgress, setLoadingProgress] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!files.length) return onError('Choose at least one data file first');
    const form = new FormData();
    files.forEach((file) => form.append('file', file));
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

  async function loadProgress(event) {
    event.preventDefault();
    if (!progressFile) return onError('Choose a .danaleo file first');
    const form = new FormData();
    form.append('file', progressFile);
    setLoadingProgress(true);
    try {
      const data = await api.loadProgress(form);
      onUploaded(data);
    } catch (err) {
      onError(err.message);
    } finally {
      setLoadingProgress(false);
    }
  }

  return (
    <div className="upload-page">
      <div className="upload-card">
        <div className="brand-mark"><Database size={28}/></div>
        <p className="eyebrow">Danaleo 3.0</p>
        <h1>Interactive EDA workspace</h1>
        <p className="muted wide">Upload CSV, JSON, spreadsheet, Parquet, and other tabular data files. Each dataset opens in its own workspace tab.</p>
        <form onSubmit={submit} className="upload-form">
          <label className="dropzone">
            <Upload size={30}/>
            <span>{files.length ? `${files.length} data file(s) selected` : 'Click to choose data files'}</span>
            <input type="file" accept={DATA_FILE_ACCEPT} multiple onChange={(e) => setFiles(Array.from(e.target.files || []))}/>
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
        <form onSubmit={loadProgress} className="upload-form progress-form">
          <label className="dropzone compact-dropzone">
            <FileUp size={24}/>
            <span>{progressFile ? progressFile.name : 'Open saved .danaleo progress'}</span>
            <input type="file" accept=".danaleo,application/zip" onChange={(e) => setProgressFile(e.target.files?.[0])}/>
          </label>
          <button className="ghost-btn large" disabled={loadingProgress}>{loadingProgress ? 'Restoring…' : 'Restore progress'}</button>
        </form>
      </div>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
