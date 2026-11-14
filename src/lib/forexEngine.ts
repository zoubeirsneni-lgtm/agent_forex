export const PAIRS = ['EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm'] as const;
export type ForexPair = (typeof PAIRS)[number];

export const TIMEFRAMES = ['30s', '1m', '3m', '5m', '10m', '15m'] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export type PivotHtf = 'M15' | 'H1' | 'H4' | 'D1';
export type Vote = 1 | 0 | -1;
export type SignalDirection = 'ACHAT' | 'VENTE' | 'NEUTRE';

export interface Candle {
  time: number; // Unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  tickVolume: number;
}

export interface ZoneConfig {
  zoneId: 1 | 2 | 3 | 4 | 5;
  zoneLabel: string;
  emaShort: number;
  emaLong: number;
  bbPeriod: number;
  bbStd: number;
  rsiPeriod: number;
  rsiOverbought: number;
  rsiOversold: number;
  macdFast: number;
  macdSlow: number;
  macdSignal: number;
  stochK: number;
  stochSmooth: number;
  stochD: number;
  atrPeriod: number;
  tickVolMa: number;
  pivotHtf: PivotHtf;
}

export const ZONE_CONFIG_BY_TF: Record<Timeframe, ZoneConfig> = {
  '30s': {
    zoneId: 1,
    zoneLabel: 'Zone 1 (30s)',
    emaShort: 8,
    emaLong: 21,
    bbPeriod: 10,
    bbStd: 1.5,
    rsiPeriod: 5,
    rsiOverbought: 80,
    rsiOversold: 20,
    macdFast: 5,
    macdSlow: 13,
    macdSignal: 3,
    stochK: 5,
    stochSmooth: 3,
    stochD: 3,
    atrPeriod: 7,
    tickVolMa: 10,
    pivotHtf: 'M15',
  },
  '1m': {
    zoneId: 2,
    zoneLabel: 'Zone 2 (1m, 3m)',
    emaShort: 9,
    emaLong: 21,
    bbPeriod: 14,
    bbStd: 2.0,
    rsiPeriod: 7,
    rsiOverbought: 75,
    rsiOversold: 25,
    macdFast: 8,
    macdSlow: 17,
    macdSignal: 5,
    stochK: 8,
    stochSmooth: 3,
    stochD: 3,
    atrPeriod: 10,
    tickVolMa: 14,
    pivotHtf: 'H1',
  },
  '3m': {
    zoneId: 2,
    zoneLabel: 'Zone 2 (1m, 3m)',
    emaShort: 9,
    emaLong: 21,
    bbPeriod: 14,
    bbStd: 2.0,
    rsiPeriod: 7,
    rsiOverbought: 75,
    rsiOversold: 25,
    macdFast: 8,
    macdSlow: 17,
    macdSignal: 5,
    stochK: 8,
    stochSmooth: 3,
    stochD: 3,
    atrPeriod: 10,
    tickVolMa: 14,
    pivotHtf: 'H1',
  },
  '5m': {
    zoneId: 3,
    zoneLabel: 'Zone 3 (5m)',
    emaShort: 12,
    emaLong: 26,
    bbPeriod: 16,
    bbStd: 2.0,
    rsiPeriod: 10,
    rsiOverbought: 70,
    rsiOversold: 30,
    macdFast: 10,
    macdSlow: 21,
    macdSignal: 7,
    stochK: 10,
    stochSmooth: 3,
    stochD: 3,
    atrPeriod: 12,
    tickVolMa: 16,
    pivotHtf: 'H4',
  },
  '10m': {
    zoneId: 4,
    zoneLabel: 'Zone 4 (10m)',
    emaShort: 13,
    emaLong: 34,
    bbPeriod: 20,
    bbStd: 2.0,
    rsiPeriod: 14,
    rsiOverbought: 70,
    rsiOversold: 30,
    macdFast: 12,
    macdSlow: 26,
    macdSignal: 9,
    stochK: 14,
    stochSmooth: 3,
    stochD: 3,
    atrPeriod: 14,
    tickVolMa: 20,
    pivotHtf: 'H4',
  },
  '15m': {
    zoneId: 5,
    zoneLabel: 'Zone 5 (15m)',
    emaShort: 21,
    emaLong: 50,
    bbPeriod: 20,
    bbStd: 2.0,
    rsiPeriod: 14,
    rsiOverbought: 70,
    rsiOversold: 30,
    macdFast: 12,
    macdSlow: 26,
    macdSignal: 9,
    stochK: 14,
    stochSmooth: 3,
    stochD: 3,
    atrPeriod: 14,
    tickVolMa: 20,
    pivotHtf: 'D1',
  },
};

export interface IndicatorResult {
  name: string;
  vote: Vote;
  summary: string;
}

export interface TimeframeAnalysis {
  pair: ForexPair;
  timeframe: Timeframe;
  zone: ZoneConfig;
  price: number;
  direction: SignalDirection;
  signalPct: number;
  signalLabel: string;
  buyCount: number;
  sellCount: number;
  neutralCount: number;
  confluence: number;
  confluenceLabel: string;
  core5Alignment: 'ACHAT' | 'VENTE' | null;
  atrRatio: number;
  volRatio: number;
  indicators: IndicatorResult[];
}

// --- Technical Indicator Math ---

function computeEmaSeries(values: number[], period: number): number[] {
  if (values.length === 0) return [];
  const k = 2 / (period + 1);
  const result: number[] = new Array(values.length);
  const seedLen = Math.min(period, values.length);
  let sum = 0;
  for (let i = 0; i < seedLen; i++) sum += values[i];
  let ema = sum / seedLen;
  for (let i = 0; i < seedLen; i++) {
    result[i] = ema;
  }
  for (let i = seedLen; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    result[i] = ema;
  }
  return result;
}

function computeSma(values: number[], period: number): number {
  const slice = values.slice(-period);
  if (slice.length === 0) return 0;
  return slice.reduce((acc, v) => acc + v, 0) / slice.length;
}

function computeStdDev(values: number[], period: number, mean: number): number {
  const slice = values.slice(-period);
  if (slice.length === 0) return 0;
  const variance = slice.reduce((acc, v) => acc + (v - mean) ** 2, 0) / slice.length;
  return Math.sqrt(variance);
}

function computeRsi(closes: number[], period: number): number {
  if (closes.length < period + 1) return 50;
  let gainSum = 0;
  let lossSum = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gainSum += diff;
    else lossSum += -diff;
  }
  let avgGain = gainSum / period;
  let avgLoss = lossSum / period;

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }

  if (avgLoss === 0) return avgGain === 0 ? 50 : 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function computeMacdHistogram(closes: number[], fast: number, slow: number, signalPeriod: number): number {
  const emaFast = computeEmaSeries(closes, fast);
  const emaSlow = computeEmaSeries(closes, slow);
  const macdLine = emaFast.map((f, idx) => f - emaSlow[idx]);
  const signalLine = computeEmaSeries(macdLine, signalPeriod);
  const lastIdx = macdLine.length - 1;
  return macdLine[lastIdx] - signalLine[lastIdx];
}

function computeStochastic(
  candles: Candle[],
  kPeriod: number,
  smoothK: number,
  dPeriod: number
): { k: number; d: number } {
  const rawK: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    const start = Math.max(0, i - kPeriod + 1);
    let highest = -Infinity;
    let lowest = Infinity;
    for (let j = start; j <= i; j++) {
      if (candles[j].high > highest) highest = candles[j].high;
      if (candles[j].low < lowest) lowest = candles[j].low;
    }
    const span = highest - lowest;
    rawK.push(span === 0 ? 50 : ((candles[i].close - lowest) / span) * 100);
  }

  const slowedK: number[] = [];
  for (let i = 0; i < rawK.length; i++) {
    const start = Math.max(0, i - smoothK + 1);
    const slice = rawK.slice(start, i + 1);
    slowedK.push(slice.reduce((a, b) => a + b, 0) / slice.length);
  }

  const lastK = slowedK[slowedK.length - 1] ?? 50;
  const dSlice = slowedK.slice(-dPeriod);
  const lastD = dSlice.length > 0 ? dSlice.reduce((a, b) => a + b, 0) / dSlice.length : 50;
  return { k: lastK, d: lastD };
}

function computeAtrStats(candles: Candle[], period: number): { atrNow: number; atrRatio: number } {
  if (candles.length < 2) return { atrNow: 0, atrRatio: 1 };
  const trs: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const cur = candles[i];
    const prevClose = candles[i - 1].close;
    const tr = Math.max(cur.high - cur.low, Math.abs(cur.high - prevClose), Math.abs(cur.low - prevClose));
    trs.push(tr);
  }
  const seedLen = Math.min(period, trs.length);
  let atr = trs.slice(0, seedLen).reduce((a, b) => a + b, 0) / seedLen;
  const atrSeries: number[] = [atr];
  for (let i = seedLen; i < trs.length; i++) {
    atr = (atr * (period - 1) + trs[i]) / period;
    atrSeries.push(atr);
  }
  const atrNow = atrSeries[atrSeries.length - 1] ?? 0;
  const baselineSlice = atrSeries.slice(-20);
  const atrMean =
    baselineSlice.length > 0
      ? baselineSlice.reduce((acc, v) => acc + v, 0) / baselineSlice.length
      : atrNow;
  const atrRatio = atrMean > 0 ? atrNow / atrMean : 1;
  return { atrNow, atrRatio };
}

export function analyzeTimeframe(
  pair: ForexPair,
  timeframe: Timeframe,
  candles: Candle[],
  htfPivotCandle: { high: number; low: number; close: number }
): TimeframeAnalysis {
  const zone = ZONE_CONFIG_BY_TF[timeframe];
  const closes = candles.map((c) => c.close);
  const volumes = candles.map((c) => c.tickVolume);
  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2] ?? current;
  const digits = pair === 'USDJPYm' ? 3 : 5;
  const isEntryTf = timeframe === '30s' || timeframe === '1m' || timeframe === '3m';

  // 1. EMA: +1 if emaShort > emaLong, -1 if <, 0 if equal
  const emaShortArr = computeEmaSeries(closes, zone.emaShort);
  const emaLongArr = computeEmaSeries(closes, zone.emaLong);
  const emaShort = emaShortArr[emaShortArr.length - 1];
  const emaLong = emaLongArr[emaLongArr.length - 1];
  const emaVote: Vote = emaShort > emaLong ? 1 : emaShort < emaLong ? -1 : 0;

  // 2. Bollinger Bands: block to 0 if outside outer bands on entry timeframes (30s, 1m, 3m)
  const bbMiddle = computeSma(closes, zone.bbPeriod);
  const bbStd = computeStdDev(closes, zone.bbPeriod, bbMiddle);
  const bbUpper = bbMiddle + zone.bbStd * bbStd;
  const bbLower = bbMiddle - zone.bbStd * bbStd;
  let bbVote: Vote;
  let bbTag = '';
  if (isEntryTf && current.close >= bbUpper) {
    bbVote = 0;
    bbTag = ' · Hors bande +';
  } else if (isEntryTf && current.close <= bbLower) {
    bbVote = 0;
    bbTag = ' · Hors bande -';
  } else {
    bbVote = current.close > bbMiddle ? 1 : current.close < bbMiddle ? -1 : 0;
  }

  // 3. RSI: block to 0 in overbought/oversold extreme zones
  const rsi = computeRsi(closes, zone.rsiPeriod);
  let rsiVote: Vote;
  let rsiTag = '';
  if (rsi >= zone.rsiOverbought) {
    rsiVote = 0;
    rsiTag = ' [Surachat]';
  } else if (rsi <= zone.rsiOversold) {
    rsiVote = 0;
    rsiTag = ' [Survente]';
  } else if (rsi > 50) {
    rsiVote = 1;
  } else if (rsi < 50) {
    rsiVote = -1;
  } else {
    rsiVote = 0;
  }

  // 4. MACD: +1 if histogram > 0, -1 if < 0, 0 otherwise
  const macdHist = computeMacdHistogram(closes, zone.macdFast, zone.macdSlow, zone.macdSignal);
  const macdVote: Vote = macdHist > 0 ? 1 : macdHist < 0 ? -1 : 0;

  // 5. Stochastic: +1 if %K > %D, -1 if <, 0 if equal
  const stoch = computeStochastic(candles, zone.stochK, zone.stochSmooth, zone.stochD);
  const stochVote: Vote = stoch.k > stoch.d ? 1 : stoch.k < stoch.d ? -1 : 0;

  // 6. ATR: real volatility filter (0 when market is too calm / flat)
  const { atrNow, atrRatio } = computeAtrStats(candles, zone.atrPeriod);
  let atrVote: Vote;
  let atrTag = '';
  if (atrRatio < 0.85) {
    atrVote = 0;
    atrTag = ' (Calme)';
  } else if (!isEntryTf && Math.abs(current.close - prev.close) < 0.25 * atrNow) {
    atrVote = 0;
    atrTag = ' (Neutre)';
  } else if (current.close > prev.close) {
    atrVote = 1;
  } else if (current.close < prev.close) {
    atrVote = -1;
  } else {
    atrVote = 0;
  }

  // 7. Tick Volume: real volume confirmation filter (0 when volume ratio <= 1.0)
  const volMa = computeSma(volumes, zone.tickVolMa);
  const volRatio = volMa > 0 ? current.tickVolume / volMa : 1.0;
  let volVote: Vote;
  let volTag = '';
  if (volRatio <= 1.0) {
    volVote = 0;
    volTag = ' (Faible)';
  } else if (current.close > current.open) {
    volVote = 1;
  } else if (current.close < current.open) {
    volVote = -1;
  } else if (current.close > prev.close) {
    volVote = 1;
  } else if (current.close < prev.close) {
    volVote = -1;
  } else {
    volVote = 0;
  }

  // 8. Pivot Points: +1 if close > pivotP, -1 if <, 0 if equal
  const pivotP = (htfPivotCandle.high + htfPivotCandle.low + htfPivotCandle.close) / 3;
  const pivotVote: Vote = current.close > pivotP ? 1 : current.close < pivotP ? -1 : 0;

  const indicators: IndicatorResult[] = [
    {
      name: `EMA (${zone.emaShort}/${zone.emaLong})`,
      vote: emaVote,
      summary: `${emaShort.toFixed(digits)} vs ${emaLong.toFixed(digits)}`,
    },
    {
      name: `Bollinger (${zone.bbPeriod}, ${zone.bbStd})`,
      vote: bbVote,
      summary: `M=${bbMiddle.toFixed(digits)} [${bbLower.toFixed(digits)}–${bbUpper.toFixed(digits)}]${bbTag}`,
    },
    {
      name: `RSI (${zone.rsiPeriod}) [${zone.rsiOverbought}/${zone.rsiOversold}]`,
      vote: rsiVote,
      summary: `${rsi.toFixed(1)}${rsiTag}`,
    },
    {
      name: `MACD (${zone.macdFast}/${zone.macdSlow}/${zone.macdSignal})`,
      vote: macdVote,
      summary: `Hist=${macdHist >= 0 ? '+' : ''}${macdHist.toFixed(digits + 1)}`,
    },
    {
      name: `Stochastique (${zone.stochK}/${zone.stochSmooth}/${zone.stochD})`,
      vote: stochVote,
      summary: `%K=${stoch.k.toFixed(1)} / %D=${stoch.d.toFixed(1)}`,
    },
    {
      name: `ATR (${zone.atrPeriod})`,
      vote: atrVote,
      summary: `${atrNow.toFixed(digits)} (${atrRatio.toFixed(2)}x)${atrTag}`,
    },
    {
      name: `Tick Volume (MA ${zone.tickVolMa})`,
      vote: volVote,
      summary: `Ratio=${volRatio.toFixed(2)}x${volTag}`,
    },
    {
      name: `Pivot Points (${zone.pivotHtf})`,
      vote: pivotVote,
      summary: `P=${pivotP.toFixed(digits)}`,
    },
  ];

  const buyCount = indicators.reduce((acc, ind) => acc + (ind.vote === 1 ? 1 : 0), 0);
  const sellCount = indicators.reduce((acc, ind) => acc + (ind.vote === -1 ? 1 : 0), 0);
  const neutralCount = 8 - buyCount - sellCount;
  const confluence = Math.max(buyCount, sellCount);

  let direction: SignalDirection = 'NEUTRE';
  let signalPct = Math.round((confluence / 8) * 100);
  let signalLabel = 'NEUTRE';

  if (buyCount >= 5 && buyCount > sellCount) {
    direction = 'ACHAT';
    signalPct = Math.round((buyCount / 8) * 100);
    signalLabel = `${signalPct}% ACHAT`;
  } else if (sellCount >= 5 && sellCount > buyCount) {
    direction = 'VENTE';
    signalPct = Math.round((sellCount / 8) * 100);
    signalLabel = `${signalPct}% VENTE`;
  }

  const core5Votes: Vote[] = [emaVote, bbVote, rsiVote, macdVote, stochVote];
  const core5Alignment: 'ACHAT' | 'VENTE' | null = core5Votes.every((v) => v === 1)
    ? 'ACHAT'
    : core5Votes.every((v) => v === -1)
      ? 'VENTE'
      : null;

  return {
    pair,
    timeframe,
    zone,
    price: current.close,
    direction,
    signalPct,
    signalLabel,
    buyCount,
    sellCount,
    neutralCount,
    confluence,
    confluenceLabel: `${confluence}/8`,
    core5Alignment,
    atrRatio,
    volRatio,
    indicators,
  };
}

export interface SRLevel {
  price: number;
  distancePips: number;
  source: string;
}

export type SRProximityAlert = 'NEAR_RESISTANCE' | 'NEAR_SUPPORT' | 'NEAR_BOTH' | 'CLEAR';

export interface SupportResistanceInfo {
  support: SRLevel | null;
  resistance: SRLevel | null;
  proximityAlert: SRProximityAlert;
  thresholdPips: number;
}

function collectSwingCandidates(
  candles: Candle[],
  tfLabel: string,
  lookback: number
): { price: number; kind: 'support' | 'resistance'; source: string }[] {
  const slice = candles.slice(-lookback);
  const out: { price: number; kind: 'support' | 'resistance'; source: string }[] = [];
  if (slice.length < 7) return out;

  const w = 2;
  // Exclut la dernière bougie en cours pour éviter un faux swing sur le tick actif
  for (let i = w; i < slice.length - 1 - w; i++) {
    const h = slice[i].high;
    const l = slice[i].low;
    let isSwingHigh = true;
    let isSwingLow = true;
    for (let k = i - w; k <= i + w; k++) {
      if (k === i) continue;
      if (slice[k].high >= h) isSwingHigh = false;
      if (slice[k].low <= l) isSwingLow = false;
    }
    if (isSwingHigh) out.push({ price: h, kind: 'resistance', source: `Sommet ${tfLabel}` });
    if (isSwingLow) out.push({ price: l, kind: 'support', source: `Creux ${tfLabel}` });
  }

  // Secours : plus haut et plus bas récents des bougies clôturées
  const closed = slice.slice(0, -1);
  if (closed.length > 0) {
    let maxH = -Infinity;
    let minL = Infinity;
    for (const c of closed) {
      if (c.high > maxH) maxH = c.high;
      if (c.low < minL) minL = c.low;
    }
    if (Number.isFinite(maxH)) out.push({ price: maxH, kind: 'resistance', source: `Haut ${tfLabel}` });
    if (Number.isFinite(minL)) out.push({ price: minL, kind: 'support', source: `Bas ${tfLabel}` });
  }

  return out;
}

export function computeSupportResistance(
  pair: ForexPair,
  currentPrice: number,
  candles1m: Candle[],
  candles5m: Candle[],
  h1Candle: { high: number; low: number; close: number },
  h4Candle: { high: number; low: number; close: number }
): SupportResistanceInfo {
  const pip = pair === 'USDJPYm' ? 0.01 : 0.0001;
  const candidates: { price: number; source: string }[] = [];

  for (const s of collectSwingCandidates(candles1m, '1m', 80)) {
    candidates.push({ price: s.price, source: s.source });
  }
  for (const s of collectSwingCandidates(candles5m, '5m', 60)) {
    candidates.push({ price: s.price, source: s.source });
  }

  for (const [label, bar] of [
    ['H1', h1Candle],
    ['H4', h4Candle],
  ] as const) {
    const p = (bar.high + bar.low + bar.close) / 3;
    const r1 = 2 * p - bar.low;
    const s1 = 2 * p - bar.high;
    const r2 = p + (bar.high - bar.low);
    const s2 = p - (bar.high - bar.low);
    candidates.push(
      { price: p, source: `Pivot ${label}` },
      { price: r1, source: `R1 ${label}` },
      { price: r2, source: `R2 ${label}` },
      { price: s1, source: `S1 ${label}` },
      { price: s2, source: `S2 ${label}` }
    );
  }

  let bestSupport: { price: number; source: string } | null = null;
  let bestResistance: { price: number; source: string } | null = null;
  const minGap = pip * 0.05;

  for (const c of candidates) {
    if (!Number.isFinite(c.price) || c.price <= 0) continue;
    if (c.price < currentPrice - minGap) {
      if (!bestSupport || c.price > bestSupport.price) {
        bestSupport = c;
      }
    } else if (c.price > currentPrice + minGap) {
      if (!bestResistance || c.price < bestResistance.price) {
        bestResistance = c;
      }
    }
  }

  const { atrNow } = computeAtrStats(candles1m, 10);
  const thresholdPrice = Math.max(2 * pip, 0.75 * atrNow);
  const thresholdPips = Number((thresholdPrice / pip).toFixed(1));

  const support: SRLevel | null = bestSupport
    ? {
        price: bestSupport.price,
        distancePips: Number(((currentPrice - bestSupport.price) / pip).toFixed(1)),
        source: bestSupport.source,
      }
    : null;

  const resistance: SRLevel | null = bestResistance
    ? {
        price: bestResistance.price,
        distancePips: Number(((bestResistance.price - currentPrice) / pip).toFixed(1)),
        source: bestResistance.source,
      }
    : null;

  const nearSupport = bestSupport !== null && currentPrice - bestSupport.price <= thresholdPrice;
  const nearResistance = bestResistance !== null && bestResistance.price - currentPrice <= thresholdPrice;

  let proximityAlert: SRProximityAlert = 'CLEAR';
  if (nearSupport && nearResistance) proximityAlert = 'NEAR_BOTH';
  else if (nearResistance) proximityAlert = 'NEAR_RESISTANCE';
  else if (nearSupport) proximityAlert = 'NEAR_SUPPORT';

  return {
    support,
    resistance,
    proximityAlert,
    thresholdPips,
  };
}

export interface PairSetupEvaluation {
  status: 'READY_BUY' | 'READY_SELL' | 'CALM_BLOCKED' | 'COUNTER_TREND' | 'WAITING';
  direction: 'ACHAT' | 'VENTE' | null;
  triggerTf: '1m' | '3m' | null;
  triggerPrice: number | null;
  setupText: string;
  atrRatio: number;
  volRatio: number;
  isMarketActive: boolean;
}

export function evaluatePairSetup(rows: TimeframeAnalysis[]): PairSetupEvaluation {
  if (!rows || rows.length === 0) {
    return {
      status: 'WAITING',
      direction: null,
      triggerTf: null,
      triggerPrice: null,
      setupText: 'En attente des données MT5',
      atrRatio: 1,
      volRatio: 1,
      isMarketActive: true,
    };
  }

  const rowMap = new Map(rows.map((r) => [r.timeframe, r]));
  const r1m = rowMap.get('1m');
  const r3m = rowMap.get('3m');
  const htfRows = [rowMap.get('5m'), rowMap.get('10m'), rowMap.get('15m')].filter(
    (r): r is TimeframeAnalysis => Boolean(r)
  );

  const htfBuys = htfRows.filter((r) => r.direction === 'ACHAT').length;
  const htfSells = htfRows.filter((r) => r.direction === 'VENTE').length;
  const htfTrend: 'ACHAT' | 'VENTE' | null =
    htfBuys >= 2 && htfSells === 0 ? 'ACHAT' : htfSells >= 2 && htfBuys === 0 ? 'VENTE' : null;

  const marketRef = r1m || r3m || rows[0];
  const atrRatio = typeof marketRef?.atrRatio === 'number' ? marketRef.atrRatio : 1;
  const volRatio = typeof marketRef?.volRatio === 'number' ? marketRef.volRatio : 1;
  const isMarketActive = atrRatio >= 0.85;

  const entryRows = [r1m, r3m].filter((r): r is TimeframeAnalysis => Boolean(r));
  const readyBuyRow =
    htfTrend === 'ACHAT'
      ? entryRows.find((r) => r.direction === 'ACHAT' && r.core5Alignment === 'ACHAT')
      : undefined;
  const readySellRow =
    htfTrend === 'VENTE'
      ? entryRows.find((r) => r.direction === 'VENTE' && r.core5Alignment === 'VENTE')
      : undefined;
  const isCounterTrend =
    (htfTrend === 'ACHAT' && entryRows.some((r) => r.direction === 'VENTE')) ||
    (htfTrend === 'VENTE' && entryRows.some((r) => r.direction === 'ACHAT'));

  if (readyBuyRow && isMarketActive) {
    return {
      status: 'READY_BUY',
      direction: 'ACHAT',
      triggerTf: readyBuyRow.timeframe as '1m' | '3m',
      triggerPrice: readyBuyRow.price,
      setupText: 'Prêt ACHAT (aligné 5m–15m)',
      atrRatio,
      volRatio,
      isMarketActive,
    };
  }
  if (readySellRow && isMarketActive) {
    return {
      status: 'READY_SELL',
      direction: 'VENTE',
      triggerTf: readySellRow.timeframe as '1m' | '3m',
      triggerPrice: readySellRow.price,
      setupText: 'Prêt VENTE (aligné 5m–15m)',
      atrRatio,
      volRatio,
      isMarketActive,
    };
  }
  if (readyBuyRow || readySellRow) {
    return {
      status: 'CALM_BLOCKED',
      direction: null,
      triggerTf: null,
      triggerPrice: null,
      setupText: `Aligné ${htfTrend}, mais marché trop calme`,
      atrRatio,
      volRatio,
      isMarketActive,
    };
  }
  if (isCounterTrend) {
    return {
      status: 'COUNTER_TREND',
      direction: null,
      triggerTf: null,
      triggerPrice: null,
      setupText: 'Contre-tendance 5m–15m · Prudence',
      atrRatio,
      volRatio,
      isMarketActive,
    };
  }
  return {
    status: 'WAITING',
    direction: null,
    triggerTf: null,
    triggerPrice: null,
    setupText: "En attente d'alignement 1m/3m + 5m–15m",
    atrRatio,
    volRatio,
    isMarketActive,
  };
}


