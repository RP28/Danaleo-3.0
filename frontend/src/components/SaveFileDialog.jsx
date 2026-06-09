import { useEffect, useState } from 'react';
import { FolderOpen, Save, X } from 'lucide-react';

function ensureExtension(name, extension) {
  const cleanName = name.trim() || `danaleo_export${extension}`;
  return cleanName.toLowerCase().endsWith(extension) ? cleanName : `${cleanName}${extension}`;
}

function downloadFallback(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export default function SaveFileDialog({ config, onClose, onSaved, onError }) {
  const [filename, setFilename] = useState(config.suggestedName);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setFilename(config.suggestedName);
  }, [config.suggestedName]);

  async function saveFile() {
    setSaving(true);
    try {
      const file = await config.loadFile();
      const finalName = ensureExtension(filename, file.extension);

      if (window.showSaveFilePicker) {
        const handle = await window.showSaveFilePicker({
          suggestedName: finalName,
          types: [{
            description: file.description,
            accept: { [file.mediaType]: [file.extension] },
          }],
        });
        const writable = await handle.createWritable();
        await writable.write(file.blob);
        await writable.close();
      } else {
        downloadFallback(file.blob, finalName);
      }

      onSaved(finalName);
      onClose();
    } catch (error) {
      if (error?.name !== 'AbortError') onError(error.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="save-file-dialog" role="dialog" aria-modal="true" aria-label={config.title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="merge-modal-header">
          <div>
            <p className="eyebrow"><Save size={14} /> Save file</p>
            <h2>{config.title}</h2>
            <p className="muted">Name the file, then choose its location.</p>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close save dialog"><X size={18} /></button>
        </header>
        <label className="save-file-name">
          File name
          <input value={filename} onChange={(event) => setFilename(event.target.value)} autoFocus />
        </label>
        <p className="muted save-location-note">
          <FolderOpen size={15} />
          Your browser will open a location picker when supported. Otherwise it will use your browser download location.
        </p>
        <footer className="save-file-actions">
          <button className="ghost-btn" onClick={onClose}>Cancel</button>
          <button className="primary-btn" onClick={saveFile} disabled={saving}>
            <FolderOpen size={15} /> {saving ? 'Preparing file…' : 'Choose location and save'}
          </button>
        </footer>
      </section>
    </div>
  );
}
