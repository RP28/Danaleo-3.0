import { X } from 'lucide-react';

export default function Toast({ toast, onClose }) {
  if (!toast) return null;
  return (
    <div className={`toast ${toast.type || 'info'}`}>
      <span>{toast.text}</span>
      <button onClick={onClose}><X size={14}/></button>
    </div>
  );
}
