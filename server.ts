import express from 'express';
import fs from 'fs';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';
import { createServer as createViteServer } from 'vite';
import {
  analyzeTimeframe,
  type Candle,
  type ForexPair,
  PAIRS,
  type PivotHtf,
  TIMEFRAMES,
  type TimeframeAnalysis,
} from './src/lib/forexEngine';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = Number(process.env.PORT) || 3000;

const YAHOO_SYMBOL: Record<ForexPair, string> = {
  EURUSDm: 'EURUSD=X',
  GBPUSDm: 'GBPUSD=X',
  USDJPYm: 'JPY=X',
  AUDUSDm: 'AUDUSD=X',
};

const BASE_SPOT: Record<ForexPair, number> = {
  EURUSDm: 1.0842,
  GBPUSDm: 1.2678,
  USDJPYm: 153.45,
  AUDUSDm: 0.6548,
};

const TF_SECONDS: Record<(typeof TIMEFRAMES)[number], number> = {
  '30s': 30,
  '1m': 60,
  '3m': 180,
  '5m': 300,
  '10m': 600,
  '15m': 900,
};

const HTF_SECONDS: Record<PivotHtf, number> = {
  M15: 900,
  H1: 3600,
  H4: 14400,
  D1: 86400,
};

interface PairMarketState {
  spot: number;
  lastYahooSync: number;
  tfCandles: Record<(typeof TIMEFRAMES)[number], Candle[]>;
  htfCandles: Record<PivotHtf, { high: number; low: number; close: number }>;
  drift: number;
}

const marketStore: Record<ForexPair, PairMarketState> = {} as Record<ForexPair, PairMarketState>;

function pipSize(pair: ForexPair): number {
  return pair === 'USDJPYm' ? 0.01 : 0.0001;
}

function generateInitialSeries(pair: ForexPair, spot: number, stepSec: number, count: number): Candle[] {
  const nowSec = Math.floor(Date.now() / 1000);
  const alignedEnd = nowSec - (nowSec % stepSec);
  const pip = pipSize(pair);
  const volScale = Math.sqrt(stepSec / 60);
  const candles: Candle[] = new Array(count);

  let price = spot;
  // Walk backwards then reverse so latest close matches current spot
  const prices: number[] = [price];
  let momentum = (Math.random() - 0.5) * 0.4;
  for (let i = 1; i <= count; i++) {
    momentum = momentum * 0.75 + (Math.random() - 0.5) * 0.8;
    const delta = momentum * pip * 2.2 * volScale;
    price = Math.max(pip * 10, price - delta);
    prices.push(price);
  }
  prices.reverse();

  for (let i = 0; i < count; i++) {
    const open = prices[i];
    const close = prices[i + 1];
    const spread = Math.abs(close - open) + pip * (0.8 + Math.random() * 2.2) * volScale;
    const high = Math.max(open, close) + spread * (0.3 + Math.random() * 0.6);
    const low = Math.min(open, close) - spread * (0.3 + Math.random() * 0.6);
    const baseVol = Math.round((18 + Math.random() * 55) * Math.max(0.5, volScale));
    candles[i] = {
      time: alignedEnd - (count - 1 - i) * stepSec,
      open,
      high,
      low,
      close,
      tickVolume: baseVol,
    };
  }
  return candles;
}

function initMarketStore() {
  for (const pair of PAIRS) {
    const spot = BASE_SPOT[pair];
    const tfCandles = {} as Record<(typeof TIMEFRAMES)[number], Candle[]>;
    for (const tf of TIMEFRAMES) {
      tfCandles[tf] = generateInitialSeries(pair, spot, TF_SECONDS[tf], 120);
    }
    const pip = pipSize(pair);
    const htfCandles: Record<PivotHtf, { high: number; low: number; close: number }> = {
      M15: { high: spot + pip * 14, low: spot - pip * 12, close: spot - pip * 2 },
      H1: { high: spot + pip * 28, low: spot - pip * 24, close: spot + pip * 3 },
      H4: { high: spot + pip * 52, low: spot - pip * 46, close: spot - pip * 5 },
      D1: { high: spot + pip * 85, low: spot - pip * 78, close: spot + pip * 11 },
    };
    marketStore[pair] = {
      spot,
      lastYahooSync: 0,
      tfCandles,
      htfCandles,
      drift: (Math.random() - 0.5) * 0.3,
    };
  }
}

initMarketStore();

async function fetchYahooChart(pair: ForexPair): Promise<{ spot: number; candles1m?: Candle[] } | null> {
  const symbol = YAHOO_SYMBOL[pair];
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1m&range=1d`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { 'User-Agent': 'Mozilla/5.0' },
    });
    if (!res.ok) return null;
    const json: any = await res.json();
    const result = json?.chart?.result?.[0];
    if (!result) return null;
    const metaPrice = Number(result.meta?.regularMarketPrice);
    const timestamps: number[] = result.timestamp || [];
    const quote = result.indicators?.quote?.[0];
    const candles1m: Candle[] = [];

    if (quote && timestamps.length > 35) {
      for (let i = 0; i < timestamps.length; i++) {
        const o = quote.open?.[i];
        const h = quote.high?.[i];
        const l = quote.low?.[i];
        const c = quote.close?.[i];
        if (o != null && h != null && l != null && c != null) {
          candles1m.push({
            time: timestamps[i],
            open: Number(o),
            high: Number(h),
            low: Number(l),
            close: Number(c),
            tickVolume: Math.max(10, Number(quote.volume?.[i] || 25 + (i % 17) * 3)),
          });
        }
      }
    }

    const spot = Number.isFinite(metaPrice) && metaPrice > 0
      ? metaPrice
      : candles1m.length > 0
        ? candles1m[candles1m.length - 1].close
        : 0;

    if (spot <= 0) return null;
    return { spot, candles1m: candles1m.length >= 60 ? candles1m.slice(-120) : undefined };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function advancePairMarket(pair: ForexPair): Promise<void> {
  const state = marketStore[pair];
  const nowMs = Date.now();
  const nowSec = Math.floor(nowMs / 1000);
  const pip = pipSize(pair);

  // Sync with real Yahoo Finance FX feed at most every 30s
  if (nowMs - state.lastYahooSync > 30000) {
    state.lastYahooSync = nowMs;
    const live = await fetchYahooChart(pair);
    if (live) {
      state.spot = live.spot;
      if (live.candles1m) {
        state.tfCandles['1m'] = live.candles1m;
      }
      // Update H1/M15 pivot anchor around real spot
      const recent = state.tfCandles['1m'].slice(-15);
      if (recent.length > 0) {
        state.htfCandles.M15 = {
          high: Math.max(...recent.map((c) => c.high)),
          low: Math.min(...recent.map((c) => c.low)),
          close: recent[recent.length - 1].close,
        };
      }
    }
  }

  // Micro-tick evolution so 30s/1m/3m/5m/10m/15m progress smoothly every cycle
  state.drift = state.drift * 0.85 + (Math.random() - 0.5) * 0.65;
  const delta = state.drift * pip * 1.4;
  state.spot = Math.max(pip * 10, state.spot + delta);

  for (const tf of TIMEFRAMES) {
    const step = TF_SECONDS[tf];
    const bucket = nowSec - (nowSec % step);
    const list = state.tfCandles[tf];
    const last = list[list.length - 1];
    const tickBump = Math.round(8 + Math.random() * 24);

    if (!last || bucket > last.time) {
      const open = last ? last.close : state.spot;
      const close = state.spot;
      const newCandle: Candle = {
        time: bucket,
        open,
        high: Math.max(open, close) + pip * Math.random() * 0.8,
        low: Math.min(open, close) - pip * Math.random() * 0.8,
        close,
        tickVolume: tickBump,
      };
      list.push(newCandle);
      if (list.length > 140) list.shift();
    } else {
      last.close = state.spot;
      last.high = Math.max(last.high, state.spot);
      last.low = Math.min(last.low, state.spot);
      last.tickVolume += tickBump;
    }
  }

  // Refresh HTF pivot reference periodically
  for (const htf of ['M15', 'H1', 'H4', 'D1'] as PivotHtf[]) {
    const step = HTF_SECONDS[htf];
    if (nowSec % step < 20) {
      const span = pip * (htf === 'M15' ? 14 : htf === 'H1' ? 28 : htf === 'H4' ? 50 : 85);
      state.htfCandles[htf] = {
        high: state.spot + span * 0.55,
        low: state.spot - span * 0.45,
        close: state.spot - delta * 0.5,
      };
    }
  }
}

async function startServer() {
  const app = express();
  const httpServer = http.createServer(app);
  app.use(express.json({ limit: '1mb' }));

  // 1. Snapshot de marché multi-paires / multi-timeframes
  app.get('/api/market-snapshot', async (req, res) => {
    const source = String(req.query.source || 'live');
    const bridgeUrl = String(req.query.bridgeUrl || '').trim();
    const updatedAt = new Date().toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });

    if (source === 'mt5_offline') {
      res.json({
        ok: false,
        status: 'WAIT',
        message: 'MetaTrader 5 temporairement injoignable',
        updatedAt,
      });
      return;
    }

    if (source === 'mt5_bridge' && bridgeUrl) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3500);
      try {
        const bridgeRes = await fetch(`${bridgeUrl.replace(/\/$/, '')}/snapshot`, {
          signal: controller.signal,
        });
        if (!bridgeRes.ok) throw new Error(`HTTP ${bridgeRes.status}`);
        const bridgeData = await bridgeRes.json();
        res.json({ ok: true, ...bridgeData, updatedAt });
        return;
      } catch {
        res.json({
          ok: false,
          status: 'WAIT',
          message: 'Bridge MT5 local injoignable',
          updatedAt,
        });
        return;
      } finally {
        clearTimeout(timer);
      }
    }

    const tfsParam = String(req.query.tfs || '').trim();
    const requestedTfs = tfsParam
      ? tfsParam
          .split(',')
          .map((t) => t.trim())
          .filter((t): t is (typeof TIMEFRAMES)[number] => (TIMEFRAMES as readonly string[]).includes(t))
      : [...TIMEFRAMES];
    const targetTfs = requestedTfs.length > 0 ? requestedTfs : [...TIMEFRAMES];

    await Promise.all(PAIRS.map((pair) => advancePairMarket(pair)));

    const analysisByPair: Record<ForexPair, TimeframeAnalysis[]> = {} as Record<ForexPair, TimeframeAnalysis[]>;
    for (const pair of PAIRS) {
      const state = marketStore[pair];
      analysisByPair[pair] = targetTfs.map((tf) => {
        const candles = state.tfCandles[tf];
        const htfCandle = state.htfCandles[
          tf === '30s'
            ? 'M15'
            : tf === '1m' || tf === '3m'
              ? 'H1'
              : tf === '5m' || tf === '10m'
                ? 'H4'
                : 'D1'
        ];
        return analyzeTimeframe(pair, tf, candles, htfCandle);
      });
    }

    res.json({
      ok: true,
      source: 'live',
      updatedAt,
      analysisByPair,
    });
  });

  // 2. Export des scripts Windows 10 / MetaTrader 5
  app.get('/api/python-agent', (_req, res) => {
    try {
      const pyDir = path.join(__dirname, 'python_agent');
      const forexAgentPy = fs.readFileSync(path.join(pyDir, 'forex_agent.py'), 'utf-8');
      const requirementsTxt = fs.readFileSync(path.join(pyDir, 'requirements.txt'), 'utf-8');
      const launcherBat = fs.readFileSync(path.join(pyDir, 'lancer_forex_agent.bat'), 'utf-8');
      res.json({
        ok: true,
        files: [
          { name: 'forex_agent.py', content: forexAgentPy },
          { name: 'requirements.txt', content: requirementsTxt },
          { name: 'lancer_forex_agent.bat', content: launcherBat },
        ],
      });
    } catch {
      res.status(500).json({ ok: false, error: 'Fichiers Python introuvables' });
    }
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        hmr: process.env.DISABLE_HMR === 'true' ? false : { server: httpServer },
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(__dirname, 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  httpServer.listen(PORT, '0.0.0.0', () => {
    console.log(`[Forex Agent Dashboard] Serveur actif sur http://0.0.0.0:${PORT}`);
  });

  const shutdown = () => {
    console.log('\n[ARRET] Fermeture propre du serveur Forex Agent Dashboard...');
    httpServer.close(() => process.exit(0));
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

startServer();
