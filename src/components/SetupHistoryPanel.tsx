import type { ForexPair } from '../lib/forexEngine';

export interface SetupHistoryEntry {
  id: string;
  time: string;
  pair: ForexPair;
  timeframe: '1m' | '3m';
  direction: 'ACHAT' | 'VENTE';
  price: number;
  spreadPips: number | null;
  srNote: string;
}

interface SetupHistoryPanelProps {
  entries: SetupHistoryEntry[];
  onClear: () => void;
  onSelectPair: (pair: ForexPair) => void;
}

export function SetupHistoryPanel({
  entries,
  onClear,
  onSelectPair,
}: SetupHistoryPanelProps) {
  return (
    <section className="mt-6 rounded-xl border border-[#1e2633] bg-[#0f131a] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[#1e2633] pb-3">
        <div className="flex items-baseline gap-3">
          <h3 className="text-base font-bold text-slate-100">
            Derniers Setups Prêts (max 10)
          </h3>
          <span className="font-mono text-xs text-slate-400 tabular-nums">
            {entries.length} / 10
          </span>
        </div>

        {entries.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="rounded-lg border border-[#1e2633] bg-[#090c11] px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:border-slate-600 hover:text-white cursor-pointer"
          >
            Effacer
          </button>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="text-xs sm:text-sm text-slate-400">
          Aucun Setup Prêt 1m/3m détecté pour le moment durant cette session.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs sm:text-sm">
            <thead>
              <tr className="border-b border-[#1a2230] text-xs font-semibold text-slate-400">
                <th className="py-2 pr-4">Heure</th>
                <th className="py-2 pr-4">Paire</th>
                <th className="py-2 pr-4">TF</th>
                <th className="py-2 pr-4">Sens</th>
                <th className="py-2 pr-4">Prix</th>
                <th className="py-2 pr-4">Spread</th>
                <th className="py-2">Contexte S/R</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#171e2b]">
              {entries.map((entry) => {
                const digits = entry.pair === 'USDJPYm' ? 3 : 5;
                const isBuy = entry.direction === 'ACHAT';
                return (
                  <tr
                    key={entry.id}
                    onClick={() => onSelectPair(entry.pair)}
                    className="transition-colors hover:bg-[#121822] cursor-pointer"
                  >
                    <td className="py-2.5 pr-4 font-mono text-slate-300 tabular-nums whitespace-nowrap">
                      {entry.time}
                    </td>
                    <td className="py-2.5 pr-4 font-mono font-bold text-slate-100 whitespace-nowrap">
                      {entry.pair}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-slate-300 tabular-nums whitespace-nowrap">
                      {entry.timeframe}
                    </td>
                    <td
                      className={`py-2.5 pr-4 font-mono font-bold whitespace-nowrap ${
                        isBuy ? 'text-emerald-400' : 'text-red-400'
                      }`}
                    >
                      {entry.direction}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-slate-200 tabular-nums whitespace-nowrap">
                      {entry.price.toFixed(digits)}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-slate-300 tabular-nums whitespace-nowrap">
                      {entry.spreadPips !== null ? `${entry.spreadPips.toFixed(1)} pips` : '—'}
                    </td>
                    <td className="py-2.5 text-slate-400 whitespace-nowrap">
                      {entry.srNote}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
