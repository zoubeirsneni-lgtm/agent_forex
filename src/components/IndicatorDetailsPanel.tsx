import type { TimeframeAnalysis } from '../lib/forexEngine';

interface IndicatorDetailsPanelProps {
  analysis: TimeframeAnalysis | null;
}

export function IndicatorDetailsPanel({ analysis }: IndicatorDetailsPanelProps) {
  if (!analysis) return null;

  return (
    <section className="mt-6 rounded-xl border border-[#1e2633] bg-[#0f131a] p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-[#1e2633] pb-3">
        <div className="flex items-baseline gap-3">
          <h3 className="text-base font-bold text-slate-100">
            Détail des 8 indicateurs — {analysis.pair} ({analysis.timeframe})
          </h3>
          <span className="text-xs font-medium text-slate-400">
            {analysis.zone.zoneLabel} · Pivot {analysis.zone.pivotHtf}
          </span>
        </div>
        <div className="font-mono text-xs text-slate-300 tabular-nums">
          Achat : {analysis.buyCount}/8 · Vente : {analysis.sellCount}/8
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {analysis.indicators.map((ind) => {
          const isBuy = ind.vote === 1;
          return (
            <div
              key={ind.name}
              className="flex items-center justify-between gap-3 rounded-lg border border-[#1a2230] bg-[#090c11] px-3.5 py-2.5"
            >
              <div className="min-w-0">
                <div className="truncate text-xs font-semibold text-slate-200">{ind.name}</div>
                <div className="truncate font-mono text-xs text-slate-400 tabular-nums">
                  {ind.summary}
                </div>
              </div>
              <span
                className={`shrink-0 rounded px-2 py-1 font-mono text-xs font-bold tabular-nums ${
                  isBuy
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-red-500/15 text-red-400'
                }`}
              >
                {isBuy ? '+1 ACHAT' : '-1 VENTE'}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
