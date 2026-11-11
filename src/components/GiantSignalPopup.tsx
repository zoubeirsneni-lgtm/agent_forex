import { X } from 'lucide-react';
import type { SignalDirection } from '../lib/forexEngine';

export interface ConfirmedPopupData {
  signature: string;
  pair: string;
  timeframe: '1m' | '3m';
  direction: SignalDirection;
  signalLabel: string;
  confluenceLabel: string;
  llmLabel: string;
}

interface GiantSignalPopupProps {
  popup: ConfirmedPopupData | null;
  onDismiss: (signature: string) => void;
}

export function GiantSignalPopup({ popup, onDismiss }: GiantSignalPopupProps) {
  if (!popup) return null;

  const isSell = popup.direction === 'VENTE';
  const borderClass = isSell
    ? 'border-red-500 shadow-[0_0_90px_rgba(239,68,68,0.35)]'
    : 'border-emerald-500 shadow-[0_0_90px_rgba(16,185,129,0.35)]';
  const signalColorClass = isSell ? 'text-red-400' : 'text-emerald-400';
  const llmBgClass = isSell ? 'bg-emerald-600 text-white' : 'bg-emerald-600 text-white';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 sm:p-8 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="giant-popup-title"
    >
      <div
        className={`relative w-full max-w-4xl rounded-3xl border-[6px] bg-[#0b0f17] px-8 py-14 sm:px-14 sm:py-20 text-center ${borderClass}`}
      >
        <button
          type="button"
          onClick={() => onDismiss(popup.signature)}
          aria-label="Fermer le signal confirmé"
          className="absolute right-5 top-5 flex h-14 w-14 items-center justify-center rounded-xl border border-slate-700 bg-slate-800/90 text-slate-100 transition-colors hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white cursor-pointer"
        >
          <X className="h-8 w-8" />
        </button>

        <h2
          id="giant-popup-title"
          className="mb-6 text-3xl sm:text-5xl font-extrabold tracking-tight text-white"
        >
          🔔 SIGNAL CONFIRMÉ
        </h2>

        <div className="mb-3 font-mono text-5xl sm:text-7xl font-extrabold tracking-tight text-white tabular-nums">
          {popup.pair}
        </div>

        <div className="mb-8 text-2xl sm:text-4xl font-bold text-slate-300">
          Timeframe : <span className="font-mono text-white">{popup.timeframe}</span>
        </div>

        <div
          className={`mb-5 font-mono text-4xl sm:text-6xl font-extrabold tracking-tight tabular-nums ${signalColorClass}`}
        >
          {popup.signalLabel}
        </div>

        <div className="mb-8 font-mono text-3xl sm:text-4xl font-bold text-slate-100 tabular-nums">
          Confluence : {popup.confluenceLabel}
        </div>

        <div
          className={`inline-block rounded-2xl px-10 py-4 font-mono text-2xl sm:text-4xl font-extrabold tracking-wide ${llmBgClass}`}
        >
          {popup.llmLabel}
        </div>
      </div>
    </div>
  );
}
