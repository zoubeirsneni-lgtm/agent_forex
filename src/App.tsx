import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Code2, RefreshCw, Settings } from 'lucide-react';
import {
  type ForexPair,
  PAIRS,
  TIMEFRAMES,
  type Timeframe,
  type TimeframeAnalysis,
} from './lib/forexEngine';
import { IndicatorDetailsPanel } from './components/IndicatorDetailsPanel';
import { PythonExportModal } from './components/PythonExportModal';
import { type DashboardSettings, SettingsModal } from './components/SettingsModal';

const STORAGE_PAIR_KEY = 'forex_agent_selected_pair';

function readInitialPair(): ForexPair {
  try {
    const saved = localStorage.getItem(STORAGE_PAIR_KEY);
    if (saved && (PAIRS as readonly string[]).includes(saved)) {
      return saved as ForexPair;
    }
  } catch {
    // ignore storage errors
  }
  return 'EURUSDm';
}

function getNextTargetEpochSec(tf: Timeframe, afterEpochSec: number): number {
  const base = new Date(afterEpochSec * 1000);
  const year = base.getFullYear();
  const month = base.getMonth();
  const day = base.getDate();
  const hour = base.getHours();
  const minute = base.getMinutes();

  if (tf === '30s') {
    const t25 = Math.floor(new Date(year, month, day, hour, minute, 25, 0).getTime() / 1000);
    if (t25 > afterEpochSec) return t25;
    const t55 = Math.floor(new Date(year, month, day, hour, minute, 55, 0).getTime() / 1000);
    if (t55 > afterEpochSec) return t55;
    return Math.floor(new Date(year, month, day, hour, minute + 1, 25, 0).getTime() / 1000);
  }

  if (tf === '1m' || tf === '3m' || tf === '5m') {
    const t55 = Math.floor(new Date(year, month, day, hour, minute, 55, 0).getTime() / 1000);
    if (t55 > afterEpochSec) return t55;
    return Math.floor(new Date(year, month, day, hour, minute + 1, 55, 0).getTime() / 1000);
  }

  if (tf === '10m') {
    for (let offset = 0; offset <= 2; offset++) {
      const candDate = new Date(year, month, day, hour, minute + offset, 55, 0);
      const candSec = Math.floor(candDate.getTime() / 1000);
      if (candDate.getMinutes() % 2 === 1 && candSec > afterEpochSec) {
        return candSec;
      }
    }
  }

  // 15m : :55 des minutes 02, 05, 08, 11, 14, 17, 20... (minute % 3 === 2)
  for (let offset = 0; offset <= 3; offset++) {
    const candDate = new Date(year, month, day, hour, minute + offset, 55, 0);
    const candSec = Math.floor(candDate.getTime() / 1000);
    if (candDate.getMinutes() % 3 === 2 && candSec > afterEpochSec) {
      return candSec;
    }
  }

  return afterEpochSec + 180;
}

function buildInitialTargets(nowEpochSec: number): Record<Timeframe, number> {
  const targets = {} as Record<Timeframe, number>;
  for (const tf of TIMEFRAMES) {
    targets[tf] = getNextTargetEpochSec(tf, nowEpochSec);
  }
  return targets;
}

function computeRemainingByTf(
  targets: Record<Timeframe, number>,
  nowEpochSec: number
): Record<Timeframe, number> {
  const result = {} as Record<Timeframe, number>;
  for (const tf of TIMEFRAMES) {
    result[tf] = Math.max(0, targets[tf] - nowEpochSec);
  }
  return result;
}

function formatMmSs(totalSeconds: number): string {
  const clamped = Math.max(0, Math.floor(totalSeconds));
  const mm = String(Math.floor(clamped / 60)).padStart(2, '0');
  const ss = String(clamped % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

export default function App() {
  const [selectedPair, setSelectedPair] = useState<ForexPair>(readInitialPair);
  const [selectedTfDetail, setSelectedTfDetail] = useState<Timeframe>('1m');

  const [analysisByPair, setAnalysisByPair] = useState<Record<ForexPair, TimeframeAnalysis[]> | null>(null);
  const [mt5WaitMode, setMt5WaitMode] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<string>('Chargement...');

  const initialEpochSec = Math.floor(Date.now() / 1000);
  const targetsRef = useRef<Record<Timeframe, number>>(buildInitialTargets(initialEpochSec));
  const [remainingByTf, setRemainingByTf] = useState<Record<Timeframe, number>>(() =>
    computeRemainingByTf(targetsRef.current, initialEpochSec)
  );

  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [pythonModalOpen, setPythonModalOpen] = useState<boolean>(false);
  const [settings, setSettings] = useState<DashboardSettings>({
    marketSource: 'live',
    mt5BridgeUrl: 'http://127.0.0.1:8765',
  });

  // Persister le choix de paire
  const handleSelectPair = (pair: ForexPair) => {
    setSelectedPair(pair);
    try {
      localStorage.setItem(STORAGE_PAIR_KEY, pair);
    } catch {
      // ignore
    }
  };

  const fetchTimeframes = useCallback(
    async (tfs: readonly Timeframe[], showSpinner: boolean) => {
      if (showSpinner) setIsFetching(true);
      try {
        const params = new URLSearchParams({
          source: settings.marketSource,
          bridgeUrl: settings.mt5BridgeUrl,
          tfs: tfs.join(','),
        });
        const res = await fetch(`/api/market-snapshot?${params.toString()}`);
        const data = await res.json();

        if (!data?.ok) {
          setMt5WaitMode(true);
          setLastUpdated(data?.updatedAt || new Date().toLocaleString('fr-FR'));
          return;
        }

        setMt5WaitMode(false);
        const incoming = data.analysisByPair as Record<ForexPair, TimeframeAnalysis[]>;
        setAnalysisByPair((prev) => {
          if (!prev) return incoming;
          const next = { ...prev };
          for (const pair of PAIRS) {
            const existingRows = prev[pair] || [];
            const incomingRows = incoming[pair] || [];
            const incomingMap = new Map(incomingRows.map((r) => [r.timeframe, r]));
            const existingMap = new Map(existingRows.map((r) => [r.timeframe, r]));
            next[pair] = TIMEFRAMES.map((tf) => incomingMap.get(tf) || existingMap.get(tf)).filter(
              (r): r is TimeframeAnalysis => Boolean(r)
            );
          }
          return next;
        });
        setLastUpdated(data.updatedAt);
      } catch {
        setMt5WaitMode(true);
        setLastUpdated(new Date().toLocaleString('fr-FR'));
      } finally {
        if (showSpinner) setIsFetching(false);
      }
    },
    [settings.marketSource, settings.mt5BridgeUrl]
  );

  // Chargement initial complet des 6 timeframes au démarrage ou changement de source
  useEffect(() => {
    fetchTimeframes(TIMEFRAMES, true);
  }, [fetchTimeframes]);

  // Horloge temps réel par ligne : compte à rebours indépendant et recalcul exact aux moments prévus
  useEffect(() => {
    let lastCheckedSec = Math.floor(Date.now() / 1000);

    const timer = window.setInterval(() => {
      const nowSec = Math.floor(Date.now() / 1000);
      if (nowSec === lastCheckedSec) return;
      lastCheckedSec = nowSec;

      const dueTfs: Timeframe[] = [];
      for (const tf of TIMEFRAMES) {
        if (nowSec >= targetsRef.current[tf]) {
          dueTfs.push(tf);
          targetsRef.current[tf] = getNextTargetEpochSec(tf, nowSec);
        }
      }

      setRemainingByTf(computeRemainingByTf(targetsRef.current, nowSec));

      if (dueTfs.length > 0) {
        fetchTimeframes(dueTfs, false);
      }
    }, 250);

    return () => window.clearInterval(timer);
  }, [fetchTimeframes]);

  // Bouton Actualiser : recalcule immédiatement les 6 timeframes sans toucher aux comptes à rebours
  const handleManualRefresh = () => {
    fetchTimeframes(TIMEFRAMES, true);
  };

  // Lignes du tableau pour la paire sélectionnée uniquement
  const currentRows: TimeframeAnalysis[] = useMemo(() => {
    if (!analysisByPair) return [];
    return analysisByPair[selectedPair] || [];
  }, [analysisByPair, selectedPair]);

  const activeDetailAnalysis = useMemo(() => {
    if (mt5WaitMode) return null;
    return currentRows.find((r) => r.timeframe === selectedTfDetail) || currentRows[0] || null;
  }, [currentRows, mt5WaitMode, selectedTfDetail]);

  return (
    <div className="min-h-screen bg-[#07090d] text-slate-100">
      <header className="border-b border-[#1e2633] bg-[#0a0d13]">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-4">
          <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-white whitespace-nowrap shrink-0">
            Forex Agent Dashboard
          </h1>

          <div className="flex items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={() => setPythonModalOpen(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-[#1e2633] bg-[#0f131a] px-3.5 py-2 text-xs sm:text-sm font-semibold text-slate-200 transition-colors hover:border-slate-600 hover:text-white whitespace-nowrap cursor-pointer"
            >
              <Code2 className="h-4 w-4 text-emerald-400" />
              Script Python MT5
            </button>

            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-[#1e2633] bg-[#0f131a] px-3.5 py-2 text-xs sm:text-sm font-semibold text-slate-200 transition-colors hover:border-slate-600 hover:text-white whitespace-nowrap cursor-pointer"
            >
              <Settings className="h-4 w-4 text-slate-400" />
              Paramètres
            </button>

            <button
              type="button"
              onClick={handleManualRefresh}
              disabled={isFetching}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs sm:text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-60 whitespace-nowrap cursor-pointer"
            >
              <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
              Actualiser
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-7">
        {/* Barre de sélection des 4 paires (boutons radio) */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <fieldset aria-label="Sélection de la paire Forex" className="flex flex-wrap items-center gap-2.5">
            {PAIRS.map((pair) => {
              const checked = selectedPair === pair;
              return (
                <label
                  key={pair}
                  className={`inline-flex items-center gap-2.5 rounded-xl border px-5 py-3 text-sm sm:text-base font-bold transition-colors cursor-pointer select-none ${
                    checked
                      ? 'border-emerald-500 bg-emerald-950/50 text-emerald-300'
                      : 'border-[#1e2633] bg-[#0f131a] text-slate-300 hover:border-slate-600 hover:text-white'
                  }`}
                >
                  <input
                    type="radio"
                    name="forex-pair"
                    value={pair}
                    checked={checked}
                    onChange={() => handleSelectPair(pair)}
                    className="h-4 w-4 accent-emerald-500 cursor-pointer"
                  />
                  <span className="font-mono tracking-tight">{pair}</span>
                </label>
              );
            })}
          </fieldset>
        </div>

        {/* Bannière d'attente MT5 si injoignable */}
        {mt5WaitMode && (
          <div className="mb-5 rounded-xl border border-amber-500/40 bg-amber-950/25 px-4 py-3 text-sm font-medium text-amber-200">
            MetaTrader 5 est temporairement injoignable — nouvelle tentative automatique aux prochains créneaux.
          </div>
        )}

        {/* Tableau vertical à 4 colonnes et 6 lignes */}
        <div className="overflow-hidden rounded-2xl border border-[#1e2633] bg-[#0f131a]">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[#1e2633] bg-[#0a0d13] text-xs sm:text-sm font-semibold text-slate-400">
                  <th className="px-6 py-4">Timeframe</th>
                  <th className="px-6 py-4">Signal</th>
                  <th className="px-6 py-4">Confluence</th>
                  <th className="px-6 py-4">Prochaine MAJ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#171e2b]">
                {TIMEFRAMES.map((tf) => {
                  const row = currentRows.find((r) => r.timeframe === tf);
                  const isWait = mt5WaitMode || !row;
                  const isSelectedDetail = selectedTfDetail === tf;

                  let signalButtonClass = 'bg-slate-800 text-amber-400';
                  let signalText = 'WAIT';
                  let confluenceText = 'WAIT';

                  if (!isWait && row) {
                    signalText = row.signalLabel;
                    confluenceText = row.confluenceLabel;
                    if (row.direction === 'ACHAT') {
                      signalButtonClass = 'bg-emerald-600 text-white';
                    } else if (row.direction === 'VENTE') {
                      signalButtonClass = 'bg-red-600 text-white';
                    } else {
                      signalButtonClass = 'bg-slate-700 text-slate-100';
                    }
                  }

                  return (
                    <tr
                      key={tf}
                      onClick={() => setSelectedTfDetail(tf)}
                      className={`transition-colors cursor-pointer ${
                        isSelectedDetail ? 'bg-[#141b26]' : 'hover:bg-[#121822]'
                      }`}
                    >
                      <td className="px-6 py-4 font-mono text-lg sm:text-xl font-bold text-slate-100 tabular-nums">
                        {tf}
                      </td>
                      <td className="px-6 py-3.5">
                        <span
                          className={`inline-flex min-w-[200px] items-center justify-center rounded-xl px-5 py-2.5 font-mono text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums ${signalButtonClass}`}
                        >
                          {signalText}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono text-xl sm:text-2xl font-bold text-white tabular-nums">
                        {confluenceText}
                      </td>
                      <td className="px-6 py-4 font-mono text-lg sm:text-xl font-bold text-slate-300 tabular-nums">
                        {formatMmSs(remainingByTf[tf])}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Détail des 8 indicateurs + Zone pour la ligne sélectionnée */}
        <IndicatorDetailsPanel analysis={activeDetailAnalysis} />

        {/* Pied de page avec date de dernière mise à jour */}
        <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm text-slate-400">
          <span className="font-mono tabular-nums">
            Dernière mise à jour : {lastUpdated}
          </span>
          <span>
            Exness-MT5Trial16 · {selectedPair}
          </span>
        </footer>
      </main>

      {/* Modales Paramètres & Export Script Python MT5 */}
      <SettingsModal
        open={settingsOpen}
        settings={settings}
        onChange={setSettings}
        onClose={() => setSettingsOpen(false)}
      />
      <PythonExportModal open={pythonModalOpen} onClose={() => setPythonModalOpen(false)} />
    </div>
  );
}
