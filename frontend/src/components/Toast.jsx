import { useEffect } from 'react';
import { X } from 'lucide-react';

export default function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return undefined;

    const timer = window.setTimeout(onClose, 5000);
    return () => window.clearTimeout(timer);
  }, [toast, onClose]);

  if (!toast) return null;
  return (
    <div className={`toast ${toast.type || 'info'}`}>
      <span>{toast.text}</span>
      <button onClick={onClose}><X size={14}/></button>
    </div>
  );
}
