import { useEffect, useState } from 'react';
import { Check, Copy, Download, X } from 'lucide-react';

interface PythonFile {
  name: string;
  content: string;
}

interface PythonExportModalProps {
  open: boolean;
  onClose: () => void;
}

export function PythonExportModal({ open, onClose }: PythonExportModalProps) {
  const [files, setFiles] = useState<PythonFile[]>([]);
  const [activeFile, setActiveFile] = useState<string>('forex_agent.py');
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || files.length > 0) return;
    setLoading(true);
    fetch('/api/python-agent')
      .then((r) => r.json())
      .then((data) => {
        if (data?.ok && Array.isArray(data.files)) {
          setFiles(data.files);
        }
      })
      .finally(() => setLoading(false));
  }, [open, files.length]);

  if (!open) return null;

  const current = files.find((f) => f.name === activeFile) || files[0];

  const handleCopy = async () => {
    if (!current) return;
    await navigator.clipboard.writeText(current.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleDownload = (file: PythonFile) => {
    const blob = new Blob([file.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = file.name;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Export du script Python MT5 Windows 10"
    >
      <div className="flex max-h-[88vh] w-full max-w-4xl flex-col rounded-2xl border border-[#1e2633] bg-[#0f131a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#1e2633] px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-100">
              Agent Autonome Windows 10 — MetaTrader 5 (Exness-MT5Trial16)
            </h2>
            <p className="text-xs text-slate-400">
              Dossier cible : C:\Users\DELL PRO\Desktop\Trading\forex-agent · Génère dashboard/forex_dashboard.html
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#1e2633] bg-[#090c11] text-slate-300 hover:text-white cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1e2633] bg-[#090c11] px-6 py-3">
          <div className="flex items-center gap-2">
            {files.map((f) => (
              <button
                key={f.name}
                type="button"
                onClick={() => setActiveFile(f.name)}
                className={`whitespace-nowrap rounded-lg px-3 py-1.5 font-mono text-xs font-semibold transition-colors cursor-pointer ${
                  f.name === (current?.name ?? '')
                    ? 'bg-emerald-600 text-white'
                    : 'bg-[#131924] text-slate-300 hover:text-white'
                }`}
              >
                {f.name}
              </button>
            ))}
          </div>

          {current && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleCopy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#1e2633] bg-[#131924] px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-[#1a2230] cursor-pointer"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? 'Copié' : 'Copier'}
              </button>
              <button
                type="button"
                onClick={() => handleDownload(current)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 cursor-pointer"
              >
                <Download className="h-3.5 w-3.5" />
                Télécharger
              </button>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto p-5">
          {loading ? (
            <div className="py-12 text-center text-sm text-slate-400">Chargement des fichiers...</div>
          ) : (
            <pre className="overflow-x-auto rounded-xl border border-[#1a2230] bg-[#07090d] p-4 font-mono text-xs leading-relaxed text-slate-200">
              {current?.content || ''}
            </pre>
          )}
        </div>

        <div className="border-t border-[#1e2633] bg-[#090c11] px-6 py-3 text-xs text-slate-400">
          Installation : <span className="font-mono text-slate-200">pip install -r requirements.txt</span> puis{' '}
          <span className="font-mono text-slate-200">python forex_agent.py</span> (arrêt propre sur Ctrl+C avec MT5.shutdown()).
        </div>
      </div>
    </div>
  );
}
