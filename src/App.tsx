import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Code2, RefreshCw, Settings, Volume2, VolumeX } from 'lucide-react';
import {
  evaluatePairSetup,
  type ForexPair,
  PAIRS,
  type PairSetupEvaluation,
  type SupportResistanceInfo,
  TIMEFRAMES,
  type Timeframe,
  type TimeframeAnalysis,
} from './lib/forexEngine';
import { IndicatorDetailsPanel } from './components/IndicatorDetailsPanel';
import { PriceChartPanel, type PricePoint } from './components/PriceChartPanel';
import { PythonExportModal } from './components/PythonExportModal';
import { SetupHistoryPanel, type SetupHistoryEntry } from './components/SetupHistoryPanel';
import { type DashboardSettings, SettingsModal } from './components/SettingsModal';
import { playSetupChime, unlockAudioContext } from './lib/soundAlert';

const STORAGE_PAIR_KEY = 'forex_agent_selected_pair';
const STORAGE_TF_KEY = 'forex_agent_selected_tf';
const STORAGE_SOUND_KEY = 'forex_agent_sound_enabled';
const STORAGE_HISTORY_KEY = 'forex_agent_setup_history';
const STORAGE_SIGS_KEY = 'forex_agent_last_setup_sigs';

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

function readInitialTf(): Timeframe {
  try {
    const saved = localStorage.getItem(STORAGE_TF_KEY);
    if (saved && (TIMEFRAMES as readonly string[]).includes(saved)) {
      return saved as Timeframe;
    }
  } catch {
    // ignore storage errors
  }
  return '1m';
}

function readInitialSound(): boolean {
  try {
    const saved = localStorage.getItem(STORAGE_SOUND_KEY);
    if (saved === '0') return false;
  } catch {
    // ignore storage errors
  }
  return true;
}

function readInitialHistory(): SetupHistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.slice(0, 10) as SetupHistoryEntry[];
    }
  } catch {
    // ignore storage errors
  }
  return [];
}

function readInitialSigs(): Partial<Record<ForexPair, string>> {
  try {
    const raw = localStorage.getItem(STORAGE_SIGS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      return parsed as Partial<Record<ForexPair, string>>;
    }
  } catch {
    // ignore storage errors
  }
  return {};
}

function formatSrNote(sr?: SupportResistanceInfo): string {
  if (!sr) return 'S/R —';
  if (sr.proximityAlert === 'NEAR_BOTH') return 'Compression S/R';
  if (sr.proximityAlert === 'NEAR_RESISTANCE' && sr.resistance) {
    return `Proche Résistance (${sr.resistance.distancePips.toFixed(1)} pips)`;
  }
  if (sr.proximityAlert === 'NEAR_SUPPORT' && sr.support) {
    return `Proche Support (${sr.support.distancePips.toFixed(1)} pips)`;
  }
  return 'Zone libre';
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

function formatClockHHMMSS(date: Date): string {
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  const ss = String(date.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

export default function App() {
  const [selectedPair, setSelectedPair] = useState<ForexPair>(readInitialPair);
  const [selectedTfDetail, setSelectedTfDetail] = useState<Timeframe>(readInitialTf);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(readInitialSound);
  const [setupHistory, setSetupHistory] = useState<SetupHistoryEntry[]>(readInitialHistory);
  const lastSetupSigsRef = useRef<Partial<Record<ForexPair, string>>>(readInitialSigs());
  const [currentClock, setCurrentClock] = useState<string>(() => formatClockHHMMSS(new Date()));

  const [analysisByPair, setAnalysisByPair] = useState<Record<ForexPair, TimeframeAnalysis[]> | null>(null);
  const [priceHistoryByPair, setPriceHistoryByPair] = useState<Record<ForexPair, PricePoint[]>>({
    EURUSDm: [],
    GBPUSDm: [],
    USDJPYm: [],
    AUDUSDm: [],
  });
  const [supportResistanceByPair, setSupportResistanceByPair] = useState<
    Partial<Record<ForexPair, SupportResistanceInfo>>
  >({});
  const [spreadByPair, setSpreadByPair] = useState<Partial<Record<ForexPair, number>>>({});
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

  // Persister le choix de timeframe du détail
  const handleSelectTfDetail = (tf: Timeframe) => {
    setSelectedTfDetail(tf);
    try {
      localStorage.setItem(STORAGE_TF_KEY, tf);
    } catch {
      // ignore
    }
  };

  const handleToggleSound = () => {
    unlockAudioContext();
    setSoundEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_SOUND_KEY, next ? '1' : '0');
      } catch {
        // ignore
      }
      return next;
    });
  };

  const handleClearHistory = () => {
    setSetupHistory([]);
    try {
      localStorage.removeItem(STORAGE_HISTORY_KEY);
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
        if (data.priceHistoryByPair) {
          setPriceHistoryByPair(data.priceHistoryByPair as Record<ForexPair, PricePoint[]>);
        } else {
          const nowLabel = new Date().toLocaleTimeString('fr-FR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          });
          setPriceHistoryByPair((prev) => {
            const next = { ...prev };
            for (const pair of PAIRS) {
              const latestRow = incoming[pair]?.[0];
              if (latestRow) {
                next[pair] = [...(prev[pair] || []), { time: nowLabel, price: latestRow.price }].slice(-40);
              }
            }
            return next;
          });
        }
        if (data.supportResistanceByPair) {
          setSupportResistanceByPair(
            data.supportResistanceByPair as Partial<Record<ForexPair, SupportResistanceInfo>>
          );
        }
        if (data.spreadByPair) {
          setSpreadByPair(data.spreadByPair as Partial<Record<ForexPair, number>>);
        }
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
      setCurrentClock(formatClockHHMMSS(new Date(nowSec * 1000)));

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

  const setupByPair = useMemo(() => {
    const map = {} as Record<ForexPair, PairSetupEvaluation>;
    for (const pair of PAIRS) {
      if (mt5WaitMode || !analysisByPair) {
        map[pair] = evaluatePairSetup([]);
      } else {
        map[pair] = evaluatePairSetup(analysisByPair[pair] || []);
      }
    }
    return map;
  }, [analysisByPair, mt5WaitMode]);

  // Suivi multi-paires des nouveaux Setups Prêts : historique (max 10) + son optionnel
  useEffect(() => {
    if (mt5WaitMode || !analysisByPair) return;

    const newEntries: SetupHistoryEntry[] = [];
    let sigsChanged = false;
    const nowTime = formatClockHHMMSS(new Date());

    for (const pair of PAIRS) {
      const setup = setupByPair[pair];
      const sig =
        (setup.status === 'READY_BUY' || setup.status === 'READY_SELL') &&
        setup.direction &&
        setup.triggerTf
          ? `${setup.direction}:${setup.triggerTf}`
          : 'NONE';

      const prevSig = lastSetupSigsRef.current[pair];
      if (
        sig !== 'NONE' &&
        prevSig !== sig &&
        setup.direction &&
        setup.triggerTf &&
        setup.triggerPrice !== null
      ) {
        const rawSpread = spreadByPair[pair];
        newEntries.push({
          id: `${Date.now()}-${pair}-${Math.random().toString(36).slice(2, 6)}`,
          time: nowTime,
          pair,
          timeframe: setup.triggerTf,
          direction: setup.direction,
          price: setup.triggerPrice,
          spreadPips: typeof rawSpread === 'number' ? rawSpread : null,
          srNote: formatSrNote(supportResistanceByPair[pair]),
        });
      }

      if (prevSig !== sig) {
        lastSetupSigsRef.current[pair] = sig;
        sigsChanged = true;
      }
    }

    if (sigsChanged) {
      try {
        localStorage.setItem(STORAGE_SIGS_KEY, JSON.stringify(lastSetupSigsRef.current));
      } catch {
        // ignore
      }
    }

    if (newEntries.length > 0) {
      setSetupHistory((prev) => {
        const next = [...newEntries, ...prev].slice(0, 10);
        try {
          localStorage.setItem(STORAGE_HISTORY_KEY, JSON.stringify(next));
        } catch {
          // ignore
        }
        return next;
      });

      if (soundEnabled) {
        playSetupChime(newEntries[0].direction);
      }
    }
  }, [analysisByPair, mt5WaitMode, setupByPair, soundEnabled, spreadByPair, supportResistanceByPair]);

  const currentSpread = useMemo(() => {
    if (mt5WaitMode) return null;
    const val = spreadByPair[selectedPair];
    return typeof val === 'number' ? val : null;
  }, [mt5WaitMode, selectedPair, spreadByPair]);

  const bannerInfo = useMemo(() => {
    if (mt5WaitMode || currentRows.length === 0) {
      return {
        setupText: 'En attente des données MT5',
        setupTone: 'text-amber-400',
        marketText: 'WAIT',
        marketTone: 'text-amber-400',
        ratiosText: '',
      };
    }

    const setup = setupByPair[selectedPair];
    let setupTone = 'text-slate-300';
    if (setup.status === 'READY_BUY') setupTone = 'text-emerald-400 font-bold';
    else if (setup.status === 'READY_SELL') setupTone = 'text-red-400 font-bold';
    else if (setup.status === 'CALM_BLOCKED' || setup.status === 'COUNTER_TREND') {
      setupTone = 'text-amber-300 font-semibold';
    }

    return {
      setupText: setup.setupText,
      setupTone,
      marketText: setup.isMarketActive ? 'Marché actif' : 'Marché calme / plat',
      marketTone: setup.isMarketActive ? 'text-emerald-400 font-semibold' : 'text-amber-300 font-semibold',
      ratiosText: `ATR ${setup.atrRatio.toFixed(2)}x · Vol ${setup.volRatio.toFixed(2)}x`,
    };
  }, [currentRows.length, mt5WaitMode, selectedPair, setupByPair]);

  const currentSR = useMemo(() => {
    if (mt5WaitMode) return null;
    return supportResistanceByPair[selectedPair] ?? null;
  }, [mt5WaitMode, selectedPair, supportResistanceByPair]);

  const srDigits = selectedPair === 'USDJPYm' ? 3 : 5;

  const srBanner = useMemo(() => {
    if (mt5WaitMode || !currentSR) {
      return {
        alertText: 'En attente des niveaux S/R',
        alertTone: 'text-slate-400',
      };
    }
    if (currentSR.proximityAlert === 'NEAR_BOTH') {
      return {
        alertText: 'Compression entre Support et Résistance · Prudence',
        alertTone: 'text-amber-300 font-semibold',
      };
    }
    if (currentSR.proximityAlert === 'NEAR_RESISTANCE' && currentSR.resistance) {
      return {
        alertText: `Prudence ACHAT · Proche Résistance (${currentSR.resistance.distancePips.toFixed(1)} pips)`,
        alertTone: 'text-amber-300 font-semibold',
      };
    }
    if (currentSR.proximityAlert === 'NEAR_SUPPORT' && currentSR.support) {
      return {
        alertText: `Prudence VENTE · Proche Support (${currentSR.support.distancePips.toFixed(1)} pips)`,
        alertTone: 'text-amber-300 font-semibold',
      };
    }
    return {
      alertText: 'Zone libre entre Support et Résistance',
      alertTone: 'text-slate-400',
    };
  }, [currentSR, mt5WaitMode]);

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
              onClick={handleToggleSound}
              aria-pressed={soundEnabled}
              title={soundEnabled ? 'Couper l’alerte sonore' : 'Activer l’alerte sonore'}
              className="inline-flex items-center gap-2 rounded-lg border border-[#1e2633] bg-[#0f131a] px-3.5 py-2 text-xs sm:text-sm font-semibold text-slate-200 transition-colors hover:border-slate-600 hover:text-white whitespace-nowrap shrink-0 cursor-pointer"
            >
              {soundEnabled ? (
                <Volume2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <VolumeX className="h-4 w-4 text-slate-400" />
              )}
              {soundEnabled ? 'Son activé' : 'Son coupé'}
            </button>

            <button
              type="button"
              onClick={() => setPythonModalOpen(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-[#1e2633] bg-[#0f131a] px-3.5 py-2 text-xs sm:text-sm font-semibold text-slate-200 transition-colors hover:border-slate-600 hover:text-white whitespace-nowrap shrink-0 cursor-pointer"
            >
              <Code2 className="h-4 w-4 text-emerald-400" />
              Script Python MT5
            </button>

            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-[#1e2633] bg-[#0f131a] px-3.5 py-2 text-xs sm:text-sm font-semibold text-slate-200 transition-colors hover:border-slate-600 hover:text-white whitespace-nowrap shrink-0 cursor-pointer"
            >
              <Settings className="h-4 w-4 text-slate-400" />
              Paramètres
            </button>

            <button
              type="button"
              onClick={handleManualRefresh}
              disabled={isFetching}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs sm:text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-60 whitespace-nowrap shrink-0 cursor-pointer"
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
              const pairSetup = setupByPair[pair];
              const isReadyBuy = !mt5WaitMode && pairSetup?.status === 'READY_BUY';
              const isReadySell = !mt5WaitMode && pairSetup?.status === 'READY_SELL';
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
                  {(isReadyBuy || isReadySell) && (
                    <>
                      <span aria-hidden="true" className="text-slate-600">·</span>
                      <span
                        className={`text-xs font-semibold whitespace-nowrap ${
                          isReadyBuy ? 'text-emerald-400' : 'text-red-400'
                        }`}
                      >
                        {isReadyBuy ? 'Prêt ACHAT' : 'Prêt VENTE'}
                      </span>
                    </>
                  )}
                </label>
              );
            })}
          </fieldset>

          <div
            aria-label="Heure actuelle"
            className="font-mono text-lg sm:text-xl font-bold text-slate-200 tabular-nums"
          >
            {currentClock}
          </div>
        </div>

        {/* Bandeau compact Setup 1m/3m, État du marché et Support / Résistance */}
        <div className="mb-5 rounded-xl border border-[#1e2633] bg-[#0f131a] px-5 py-3.5 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-slate-400 font-medium">Setup 1m/3m</span>
              <span aria-hidden="true" className="text-slate-600">·</span>
              <span className={bannerInfo.setupTone}>{bannerInfo.setupText}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-slate-400 font-medium">État du marché</span>
              <span aria-hidden="true" className="text-slate-600">·</span>
              <span className={bannerInfo.marketTone}>{bannerInfo.marketText}</span>
              {bannerInfo.ratiosText && (
                <>
                  <span aria-hidden="true" className="text-slate-600">·</span>
                  <span className="font-mono text-xs text-slate-400 tabular-nums">{bannerInfo.ratiosText}</span>
                </>
              )}
              {currentSpread !== null && (
                <>
                  <span aria-hidden="true" className="text-slate-600">·</span>
                  <span
                    className={`font-mono text-xs tabular-nums ${
                      currentSpread >= 2.0 ? 'text-amber-300 font-semibold' : 'text-slate-300'
                    }`}
                  >
                    Spread {currentSpread.toFixed(1)} pips{currentSpread >= 2.0 ? ' · Spread large' : ''}
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3 border-t border-[#1a2230] pt-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-slate-400 font-medium">Support / Résistance</span>
              <span aria-hidden="true" className="text-slate-600">·</span>
              {currentSR?.support ? (
                <span className="font-mono text-xs sm:text-sm text-emerald-400 tabular-nums">
                  S {currentSR.support.price.toFixed(srDigits)} (-{currentSR.support.distancePips.toFixed(1)} pips · {currentSR.support.source})
                </span>
              ) : (
                <span className="font-mono text-xs text-slate-500">S —</span>
              )}
              <span aria-hidden="true" className="text-slate-600">·</span>
              {currentSR?.resistance ? (
                <span className="font-mono text-xs sm:text-sm text-red-400 tabular-nums">
                  R {currentSR.resistance.price.toFixed(srDigits)} (+{currentSR.resistance.distancePips.toFixed(1)} pips · {currentSR.resistance.source})
                </span>
              ) : (
                <span className="font-mono text-xs text-slate-500">R —</span>
              )}
            </div>
            <div className={srBanner.alertTone}>{srBanner.alertText}</div>
          </div>
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
                  let core5Alignment: 'ACHAT' | 'VENTE' | null = null;

                  if (!isWait && row) {
                    signalText = row.signalLabel;
                    confluenceText = row.confluenceLabel;
                    if (row.core5Alignment === 'ACHAT' || row.core5Alignment === 'VENTE') {
                      core5Alignment = row.core5Alignment;
                    } else if (row.indicators.length >= 5) {
                      const first5 = row.indicators.slice(0, 5);
                      if (first5.every((ind) => ind.vote === 1)) core5Alignment = 'ACHAT';
                      else if (first5.every((ind) => ind.vote === -1)) core5Alignment = 'VENTE';
                    }
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
                      onClick={() => handleSelectTfDetail(tf)}
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
                        <span className="inline-flex items-center gap-2.5">
                          <span>{confluenceText}</span>
                          {core5Alignment && (
                            <span
                              title={
                                core5Alignment === 'ACHAT'
                                  ? '5/5 alignés ACHAT (EMA, Bollinger, RSI, MACD, Stochastique)'
                                  : '5/5 alignés VENTE (EMA, Bollinger, RSI, MACD, Stochastique)'
                              }
                              aria-label={
                                core5Alignment === 'ACHAT'
                                  ? 'Alignement ACHAT des 5 indicateurs'
                                  : 'Alignement VENTE des 5 indicateurs'
                              }
                              className={`inline-block h-3 w-3 rounded-full shrink-0 ${
                                core5Alignment === 'ACHAT'
                                  ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.75)]'
                                  : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.75)]'
                              }`}
                            />
                          )}
                        </span>
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

        {/* Graphique prix en temps réel (Recharts) pour la paire sélectionnée */}
        <PriceChartPanel
          pair={selectedPair}
          data={priceHistoryByPair[selectedPair] || []}
          supportResistance={currentSR}
          isWait={mt5WaitMode}
        />

        {/* Mini historique des 10 derniers setups forts de la session */}
        <SetupHistoryPanel
          entries={setupHistory}
          onClear={handleClearHistory}
          onSelectPair={handleSelectPair}
        />

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
