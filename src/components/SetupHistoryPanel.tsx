import { type ForexPair, getPairDigits } from '../lib/forexEngine';

export interface SetupHistoryEntry {
  id: string;
  time: string;
  pair: ForexPair;
  timeframe: '1m' | '3m';
  direction: 'ACHAT' | 'VENTE';
  price: number;
  spreadPips: number | null;
  srNote: string;
  triggeredAtSec?: number;
  pineNote?: string;
  outcomeStatus?: 'PENDING' | 'WIN' | 'LOSS';
  outcomePips?: number | null;
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
  const resolved = entries.filter(
    (e) => e.outcomeStatus === 'WIN' || e.outcomeStatus === 'LOSS'
  );
  const wins = resolved.filter((e) => e.outcomeStatus === 'WIN').length;
  const winRatePct =
    resolved.length > 0 ? Math.round((wins / resolved.length) * 100) : null;

  return (
    <section className="mt-6 rounded-xl border border-[#1e2633] bg-[#0f131a] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[#1e2633] pb-3">
        <div className="flex flex-wrap items-baseline gap-3">
          <h3 className="text-base font-bold text-slate-100">
            Derniers Setups Prêts (max 10)
          </h3>
          <span className="font-mono text-xs text-slate-400 tabular-nums">
            {entries.length} / 10
          </span>
          {winRatePct !== null && (
            <>
              <span aria-hidden="true" className="text-slate-600">
                ·
              </span>
              <span
                className={`font-mono text-xs font-semibold tabular-nums ${
                  winRatePct >= 50 ? 'text-emerald-400' : 'text-amber-300'
                }`}
              >
                Taux : {wins}/{resolved.length} ({winRatePct}%)
              </span>
            </>
          )}
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
                <th className="py-2 pr-4">Accord Pine</th>
                <th className="py-2 pr-4">Contexte S/R</th>
                <th className="py-2">Résultat (3 bougies)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#171e2b]">
              {entries.map((entry) => {
                const digits = getPairDigits(entry.pair);
                const isBuy = entry.direction === 'ACHAT';
                const pineText = entry.pineNote || '—';
                const pineTone = pineText.includes('Hausse')
                  ? 'text-emerald-400 font-semibold'
                  : pineText.includes('Baisse')
                    ? 'text-red-400 font-semibold'
                    : 'text-slate-400';

                let outcomeNode = <span className="text-slate-500">—</span>;
                if (entry.outcomeStatus === 'PENDING') {
                  outcomeNode = (
                    <span className="font-mono text-slate-400">En cours</span>
                  );
                } else if (
                  entry.outcomeStatus === 'WIN' &&
                  typeof entry.outcomePips === 'number'
                ) {
                  outcomeNode = (
                    <span className="font-mono font-semibold text-emerald-400 tabular-nums">
                      +{Math.abs(entry.outcomePips).toFixed(1)} pips · Gagnant
                    </span>
                  );
                } else if (
                  entry.outcomeStatus === 'LOSS' &&
                  typeof entry.outcomePips === 'number'
                ) {
                  const formatted =
                    entry.outcomePips <= 0
                      ? entry.outcomePips.toFixed(1)
                      : `-${entry.outcomePips.toFixed(1)}`;
                  outcomeNode = (
                    <span className="font-mono font-semibold text-red-400 tabular-nums">
                      {formatted} pips · Perdant
                    </span>
                  );
                }

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
                      {entry.spreadPips !== null
                        ? `${entry.spreadPips.toFixed(1)} pips`
                        : '—'}
                    </td>
                    <td className={`py-2.5 pr-4 font-mono whitespace-nowrap ${pineTone}`}>
                      {pineText}
                    </td>
                    <td className="py-2.5 pr-4 text-slate-400 whitespace-nowrap">
                      {entry.srNote}
                    </td>
                    <td className="py-2.5 whitespace-nowrap">{outcomeNode}</td>
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
