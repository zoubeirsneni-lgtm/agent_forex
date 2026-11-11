import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Code2, RefreshCw, Settings } from 'lucide-react';
import {
  type ForexPair,
  type LlmCellState,
  PAIRS,
  TIMEFRAMES,
  type Timeframe,
  type TimeframeAnalysis,
} from './lib/forexEngine';
import { type ConfirmedPopupData, GiantSignalPopup } from './components/GiantSignalPopup';
import { IndicatorDetailsPanel } from './components/IndicatorDetailsPanel';
import { PythonExportModal } from './components/PythonExportModal';
import { type DashboardSettings, SettingsModal } from './components/SettingsModal';

const STORAGE_PAIR_KEY = 'forex_agent_selected_pair';
const STORAGE_DISMISSED_KEY = 'forex_agent_dismissed_signatures';
const REFRESH_SECONDS = 15;
const LLM_CACHE_MS = 60_000;
const LLM_429_COOLDOWN_MS = 60_000;

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

function readDismissedSignatures(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_DISMISSED_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

function formatTimeHHMMSS(date: Date): string {
  return date.toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export default function App() {
  const [selectedPair, setSelectedPair] = useState<ForexPair>(readInitialPair);
  const [selectedTfDetail, setSelectedTfDetail] = useState<Timeframe>('1m');
  const [dismissedSignatures, setDismissedSignatures] = useState<string[]>(readDismissedSignatures);

  const [analysisByPair, setAnalysisByPair] = useState<Record<ForexPair, TimeframeAnalysis[]> | null>(null);
  const [mt5WaitMode, setMt5WaitMode] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<string>('En attente de synchronisation...');

  // Synchronisation au démarrage à la 59e seconde
  const [isSynced, setIsSynced] = useState<boolean>(() => new Date().getSeconds() === 59);
  const [syncWaitRemaining, setSyncWaitRemaining] = useState<number>(() => {
    const s = new Date().getSeconds();
    return s === 59 ? 0 : 59 - s;
  });
  const [syncTargetStr, setSyncTargetStr] = useState<string>(() => {
    const now = new Date();
    const wait = now.getSeconds() === 59 ? 0 : 59 - now.getSeconds();
    return formatTimeHHMMSS(new Date(now.getTime() + wait * 1000));
  });

  const [nextRefreshIn, setNextRefreshIn] = useState<number>(REFRESH_SECONDS);
  const [isFetching, setIsFetching] = useState<boolean>(false);

  const [llmVerdicts, setLlmVerdicts] = useState<Record<string, LlmCellState>>({});
  const llmCacheRef = useRef<
    Record<string, { signalLabel: string; state: LlmCellState; expiresAt: number }>
  >({});
  const lastCalledSignalRef = useRef<Record<string, string>>({});
  const llmCooldownUntilRef = useRef<number>(0);

  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [pythonModalOpen, setPythonModalOpen] = useState<boolean>(false);
  const [settings, setSettings] = useState<DashboardSettings>({
    marketSource: 'live',
    mt5BridgeUrl: 'http://127.0.0.1:8765',
    llmRouterUrl: 'http://127.0.0.1:31415/v1/messages',
    llmApiKey: 'freellmapi-XXXXX',
    llmTestMode: 'real',
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

  // Réinitialiser le cache LLM quand on change le mode de test LLM
  const handleSettingsChange = (next: DashboardSettings) => {
    if (next.llmTestMode !== settings.llmTestMode || next.llmRouterUrl !== settings.llmRouterUrl) {
      llmCacheRef.current = {};
      lastCalledSignalRef.current = {};
      llmCooldownUntilRef.current = 0;
      setLlmVerdicts({});
    }
    setSettings(next);
  };

  // Évaluation LLM restrictive (max 1 appel par cycle de 15s, EURUSDm, 1m/3m, >= 6/8, signal changé, cache 60s, backoff 429 60s)
  const evaluateRestrictiveLlm = useCallback(
    async (dataByPair: Record<ForexPair, TimeframeAnalysis[]>) => {
      const now = Date.now();
      const eurRows = dataByPair['EURUSDm'] || [];
      const nextStates: Record<string, LlmCellState> = {};

      for (const pair of PAIRS) {
        const rows = dataByPair[pair] || [];
        for (const row of rows) {
          const key = `${pair}|${row.timeframe}`;
          if (pair !== 'EURUSDm' || (row.timeframe !== '1m' && row.timeframe !== '3m') || row.confluence < 6) {
            nextStates[key] = { kind: 'NON_REQUIS' };
          }
        }
      }

      let candidateToCall: TimeframeAnalysis | null = null;

      for (const row of eurRows) {
        if (row.timeframe !== '1m' && row.timeframe !== '3m') continue;
        const key = `EURUSDm|${row.timeframe}`;
        if (row.confluence < 6) {
          nextStates[key] = { kind: 'NON_REQUIS' };
          continue;
        }

        const cached = llmCacheRef.current[key];
        // Cache valide >= 60s
        if (cached && now < cached.expiresAt) {
          nextStates[key] = cached.state;
          continue;
        }

        // Signal inchangé depuis le dernier appel réussi
        if (lastCalledSignalRef.current[key] === row.signalLabel && cached) {
          nextStates[key] = cached.state;
          continue;
        }

        // Rate-limit 429 pendant 60s sans réessayer
        if (now < llmCooldownUntilRef.current) {
          nextStates[key] = {
            kind: 'ERREUR',
            message: 'ERREUR LLM',
            retryAfter: llmCooldownUntilRef.current,
          };
          continue;
        }

        if (!candidateToCall) {
          candidateToCall = row;
          nextStates[key] = { kind: 'EN_COURS' };
        } else {
          // Maximum 1 appel par cycle de 15s
          nextStates[key] = cached ? cached.state : { kind: 'EN_COURS' };
        }
      }

      setLlmVerdicts((prev) => ({ ...prev, ...nextStates }));

      if (!candidateToCall) return;

      const callKey = `EURUSDm|${candidateToCall.timeframe}`;
      try {
        const res = await fetch('/api/llm-verdict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pair: candidateToCall.pair,
            timeframe: candidateToCall.timeframe,
            signalLabel: candidateToCall.signalLabel,
            confluenceLabel: candidateToCall.confluenceLabel,
            indicators: candidateToCall.indicators.map((i) => ({
              name: i.name,
              vote: i.vote,
            })),
            routerUrl: settings.llmRouterUrl,
            apiKey: settings.llmApiKey,
            testMode: settings.llmTestMode,
          }),
        });

        const body = await res.json().catch(() => ({}));

        if (res.status === 429 || body?.rateLimited) {
          const until = Date.now() + LLM_429_COOLDOWN_MS;
          llmCooldownUntilRef.current = until;
          const errState: LlmCellState = {
            kind: 'ERREUR',
            message: 'ERREUR LLM',
            retryAfter: until,
          };
          setLlmVerdicts((prev) => ({ ...prev, [callKey]: errState }));
          return;
        }

        if (!res.ok || !body?.ok) {
          const errState: LlmCellState = {
            kind: 'ERREUR',
            message: 'ERREUR LLM',
            retryAfter: Date.now() + REFRESH_SECONDS * 1000,
          };
          setLlmVerdicts((prev) => ({ ...prev, [callKey]: errState }));
          return;
        }

        const verdictState: LlmCellState = {
          kind: 'VERDICT',
          decision: body.decision,
          confiance: body.confiance,
          raison: body.raison || '',
          cachedUntil: Date.now() + LLM_CACHE_MS,
        };
        lastCalledSignalRef.current[callKey] = candidateToCall.signalLabel;
        llmCacheRef.current[callKey] = {
          signalLabel: candidateToCall.signalLabel,
          state: verdictState,
          expiresAt: Date.now() + LLM_CACHE_MS,
        };
        setLlmVerdicts((prev) => ({ ...prev, [callKey]: verdictState }));
      } catch {
        const errState: LlmCellState = {
          kind: 'ERREUR',
          message: 'ERREUR LLM',
          retryAfter: Date.now() + REFRESH_SECONDS * 1000,
        };
        setLlmVerdicts((prev) => ({ ...prev, [callKey]: errState }));
      }
    },
    [settings.llmApiKey, settings.llmRouterUrl, settings.llmTestMode]
  );

  const runCycle = useCallback(async () => {
    setIsFetching(true);
    try {
      const params = new URLSearchParams({
        source: settings.marketSource,
        bridgeUrl: settings.mt5BridgeUrl,
      });
      const res = await fetch(`/api/market-snapshot?${params.toString()}`);
      const data = await res.json();

      if (!data?.ok) {
        setMt5WaitMode(true);
        setLastUpdated(data?.updatedAt || new Date().toLocaleString('fr-FR'));
        return;
      }

      setMt5WaitMode(false);
      setAnalysisByPair(data.analysisByPair);
      setLastUpdated(data.updatedAt);
      await evaluateRestrictiveLlm(data.analysisByPair);
    } catch {
      setMt5WaitMode(true);
      setLastUpdated(new Date().toLocaleString('fr-FR'));
    } finally {
      setIsFetching(false);
      setNextRefreshIn(REFRESH_SECONDS);
    }
  }, [evaluateRestrictiveLlm, settings.marketSource, settings.mt5BridgeUrl]);

  // Phase 1 : Attente jusqu'à la 59e seconde de la minute en cours
  useEffect(() => {
    if (isSynced) return;
    const timer = window.setInterval(() => {
      const now = new Date();
      const sec = now.getSeconds();
      if (sec === 59) {
        setSyncWaitRemaining(0);
        setIsSynced(true);
      } else {
        const remaining = 59 - sec;
        setSyncWaitRemaining(remaining);
        setSyncTargetStr(formatTimeHHMMSS(new Date(now.getTime() + remaining * 1000)));
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, [isSynced]);

  // Phase 2 : Une fois synchronisé à :59, boucle toutes les 15 secondes
  useEffect(() => {
    if (!isSynced) return;
    runCycle();
    const interval = window.setInterval(() => {
      runCycle();
    }, REFRESH_SECONDS * 1000);
    return () => window.clearInterval(interval);
  }, [isSynced, runCycle]);

  // Décompte visuel des 15 secondes
  useEffect(() => {
    if (!isSynced) return;
    const tick = window.setInterval(() => {
      setNextRefreshIn((prev) => (prev > 1 ? prev - 1 : REFRESH_SECONDS));
    }, 1000);
    return () => window.clearInterval(tick);
  }, [isSynced]);

  // Lignes du tableau pour la paire sélectionnée uniquement
  const currentRows: TimeframeAnalysis[] = useMemo(() => {
    if (!analysisByPair) return [];
    return analysisByPair[selectedPair] || [];
  }, [analysisByPair, selectedPair]);

  const activeDetailAnalysis = useMemo(() => {
    if (mt5WaitMode || !isSynced) return null;
    return currentRows.find((r) => r.timeframe === selectedTfDetail) || currentRows[0] || null;
  }, [currentRows, isSynced, mt5WaitMode, selectedTfDetail]);

  // Cohérence stricte Tableau <-> Popup : uniquement basé sur les lignes affichées pour selectedPair
  const activePopup: ConfirmedPopupData | null = useMemo(() => {
    if (mt5WaitMode || !isSynced) return null;
    for (const row of currentRows) {
      if (row.pair !== selectedPair) continue;
      if (row.timeframe !== '1m' && row.timeframe !== '3m') continue;
      const cell = llmVerdicts[`${row.pair}|${row.timeframe}`];
      if (!cell || cell.kind !== 'VERDICT' || cell.decision !== 'CONFIRME') continue;

      const signature = `${row.pair}|${row.timeframe}|${row.signalLabel}|CONFIRME`;
      if (dismissedSignatures.includes(signature)) continue;

      return {
        signature,
        pair: row.pair,
        timeframe: row.timeframe,
        direction: row.direction,
        signalLabel: row.signalLabel,
        confluenceLabel: row.confluenceLabel,
        llmLabel: `CONFIRMÉ ${cell.confiance}%`,
      };
    }
    return null;
  }, [currentRows, dismissedSignatures, isSynced, llmVerdicts, mt5WaitMode, selectedPair]);

  const handleDismissPopup = (signature: string) => {
    setDismissedSignatures((prev) => {
      if (prev.includes(signature)) return prev;
      const next = [...prev, signature].slice(-50);
      try {
        localStorage.setItem(STORAGE_DISMISSED_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const renderLlmBadge = (tf: Timeframe) => {
    if (!isSynced || mt5WaitMode || !analysisByPair) {
      return (
        <span className="inline-block rounded-lg bg-slate-800 px-3.5 py-2 font-mono text-sm font-bold text-amber-400">
          WAIT
        </span>
      );
    }

    const key = `${selectedPair}|${tf}`;
    const state = llmVerdicts[key];

    if (!state || state.kind === 'NON_REQUIS') {
      return (
        <span className="inline-block rounded-lg bg-slate-700/80 px-3.5 py-2 font-mono text-sm font-bold text-slate-200">
          NON_REQUIS
        </span>
      );
    }

    if (state.kind === 'EN_COURS') {
      return (
        <span className="inline-block animate-pulse rounded-lg bg-slate-600 px-3.5 py-2 font-mono text-sm font-bold text-white">
          EN COURS...
        </span>
      );
    }

    if (state.kind === 'ERREUR') {
      return (
        <span className="inline-block rounded-lg border border-neutral-700 bg-neutral-800 px-3.5 py-2 font-mono text-sm font-bold text-red-400">
          ERREUR LLM
        </span>
      );
    }

    if (state.decision === 'CONFIRME') {
      return (
        <span className="inline-block rounded-lg bg-emerald-600 px-3.5 py-2 font-mono text-sm font-bold text-white tabular-nums">
          CONFIRMÉ {state.confiance}%
        </span>
      );
    }

    if (state.decision === 'REFUSE') {
      return (
        <span className="inline-block rounded-lg bg-red-600 px-3.5 py-2 font-mono text-sm font-bold text-white tabular-nums">
          REFUSÉ {state.confiance}%
        </span>
      );
    }

    return (
      <span className="inline-block rounded-lg bg-amber-600 px-3.5 py-2 font-mono text-sm font-bold text-white tabular-nums">
        NEUTRE {state.confiance}%
      </span>
    );
  };

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
              onClick={() => {
                if (!isSynced) setIsSynced(true);
                else runCycle();
              }}
              disabled={isFetching}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs sm:text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-60 whitespace-nowrap cursor-pointer"
            >
              <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
              {!isSynced ? 'Démarrer maintenant' : 'Actualiser'}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-7">
        {/* Barre de sélection des 4 paires (boutons radio) + minuteur cycle */}
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

          <div className="font-mono text-xs sm:text-sm text-slate-300 tabular-nums">
            {!isSynced ? (
              <span className="text-amber-400">
                Synchronisation :59 ({syncTargetStr}) · dans {syncWaitRemaining}s
              </span>
            ) : (
              <span>Prochaine actualisation : {nextRefreshIn}s</span>
            )}
          </div>
        </div>

        {/* Bannière d'attente MT5 si injoignable */}
        {mt5WaitMode && isSynced && (
          <div className="mb-5 rounded-xl border border-amber-500/40 bg-amber-950/25 px-4 py-3 text-sm font-medium text-amber-200">
            MetaTrader 5 est temporairement injoignable — nouvelle tentative automatique toutes les 15 secondes.
          </div>
        )}

        {/* Tableau vertical strict à 4 colonnes et 7 lignes */}
        <div className="overflow-hidden rounded-2xl border border-[#1e2633] bg-[#0f131a]">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[#1e2633] bg-[#0a0d13] text-xs sm:text-sm font-semibold text-slate-400">
                  <th className="px-6 py-4">Timeframe</th>
                  <th className="px-6 py-4">Signal</th>
                  <th className="px-6 py-4">Confluence</th>
                  <th className="px-6 py-4">Verdict LLM</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#171e2b]">
                {TIMEFRAMES.map((tf) => {
                  const row = currentRows.find((r) => r.timeframe === tf);
                  const isWait = !isSynced || mt5WaitMode || !row;
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
                      <td className="px-6 py-4">{renderLlmBadge(tf)}</td>
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
            Exness-MT5Trial16 · {selectedPair} · Cycle 15s
          </span>
        </footer>
      </main>

      {/* Popup Géant (5x) strictement synchronisé avec la paire affichée */}
      <GiantSignalPopup popup={activePopup} onDismiss={handleDismissPopup} />

      {/* Modales Paramètres & Export Script Python MT5 */}
      <SettingsModal
        open={settingsOpen}
        settings={settings}
        onChange={handleSettingsChange}
        onClose={() => setSettingsOpen(false)}
      />
      <PythonExportModal open={pythonModalOpen} onClose={() => setPythonModalOpen(false)} />
    </div>
  );
}
