export const PAIRS = ['EURUSDm', 'GBPUSDm', 'USDJPYm', 'AUDUSDm'] as const;
export type ForexPair = (typeof PAIRS)[number];

export const TIMEFRAMES = ['30s', '1m', '3m', '5m', '10m', '15m'] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export type PivotHtf = 'M15' | 'H1' | 'H4' | 'D1';
export type Vote = 1 | -1;
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
  zoneId: 1 | 2 | 3 | 4;
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
    emaShort: 5,
    emaLong: 13,
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
    zoneLabel: 'Zone 3 (5m, 10m)',
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
  '10m': {
    zoneId: 3,
    zoneLabel: 'Zone 3 (5m, 10m)',
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
    zoneId: 4,
    zoneLabel: 'Zone 4 (15m)',
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
  confluence: number;
  confluenceLabel: string;
  core5Alignment: 'ACHAT' | 'VENTE' | null;
  indicators: IndicatorResult[];
}

// --- Technical Indicator Math ---

function computeEmaSeries(values: number[], period: number): number[] {
  if (values.length === 0) return [];
  const k = 2 / (period + 1);
  const result: number[] = new Array(values.length);
  let seedLen = Math.min(period, values.length);
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

function computeAtr(candles: Candle[], period: number): number {
  if (candles.length < 2) return 0;
  const trs: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const cur = candles[i];
    const prevClose = candles[i - 1].close;
    const tr = Math.max(cur.high - cur.low, Math.abs(cur.high - prevClose), Math.abs(cur.low - prevClose));
    trs.push(tr);
  }
  const seedLen = Math.min(period, trs.length);
  let atr = trs.slice(0, seedLen).reduce((a, b) => a + b, 0) / seedLen;
  for (let i = seedLen; i < trs.length; i++) {
    atr = (atr * (period - 1) + trs[i]) / period;
  }
  return atr;
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

  // 1. EMA: +1 if ema_courte > ema_longue, -1 otherwise
  const emaShortArr = computeEmaSeries(closes, zone.emaShort);
  const emaLongArr = computeEmaSeries(closes, zone.emaLong);
  const emaShort = emaShortArr[emaShortArr.length - 1];
  const emaLong = emaLongArr[emaLongArr.length - 1];
  const emaVote: Vote = emaShort > emaLong ? 1 : -1;

  // 2. Bollinger Bands: +1 if close > bb_moyenne, -1 otherwise
  const bbMiddle = computeSma(closes, zone.bbPeriod);
  const bbStd = computeStdDev(closes, zone.bbPeriod, bbMiddle);
  const bbUpper = bbMiddle + zone.bbStd * bbStd;
  const bbLower = bbMiddle - zone.bbStd * bbStd;
  const bbVote: Vote = current.close > bbMiddle ? 1 : -1;

  // 3. RSI: +1 if rsi >= 50, -1 otherwise
  const rsi = computeRsi(closes, zone.rsiPeriod);
  const rsiVote: Vote = rsi >= 50 ? 1 : -1;

  // 4. MACD: +1 if macd_histogramme > 0, -1 otherwise
  const macdHist = computeMacdHistogram(closes, zone.macdFast, zone.macdSlow, zone.macdSignal);
  const macdVote: Vote = macdHist > 0 ? 1 : -1;

  // 5. Stochastic: +1 if %K > %D, -1 otherwise
  const stoch = computeStochastic(candles, zone.stochK, zone.stochSmooth, zone.stochD);
  const stochVote: Vote = stoch.k > stoch.d ? 1 : -1;

  // 6. ATR: +1 if close > (close_prec + atr), -1 if close < (close_prec - atr), else price direction
  const atr = computeAtr(candles, zone.atrPeriod);
  let atrVote: Vote;
  if (current.close > prev.close + atr) {
    atrVote = 1;
  } else if (current.close < prev.close - atr) {
    atrVote = -1;
  } else {
    atrVote = current.close >= prev.close ? 1 : -1;
  }

  // 7. Tick Volume: +1 if vol_ratio > 1.0 && close > open, -1 if vol_ratio > 1.0 && close < open, else price direction
  const volMa = computeSma(volumes, zone.tickVolMa);
  const volRatio = volMa > 0 ? current.tickVolume / volMa : 1.0;
  let volVote: Vote;
  if (volRatio > 1.0 && current.close > current.open) {
    volVote = 1;
  } else if (volRatio > 1.0 && current.close < current.open) {
    volVote = -1;
  } else if (current.close !== current.open) {
    volVote = current.close > current.open ? 1 : -1;
  } else {
    volVote = current.close >= prev.close ? 1 : -1;
  }

  // 8. Pivot Points: +1 if close > pivot_P, -1 otherwise
  const pivotP = (htfPivotCandle.high + htfPivotCandle.low + htfPivotCandle.close) / 3;
  const pivotVote: Vote = current.close > pivotP ? 1 : -1;

  const indicators: IndicatorResult[] = [
    {
      name: `EMA (${zone.emaShort}/${zone.emaLong})`,
      vote: emaVote,
      summary: `${emaShort.toFixed(digits)} vs ${emaLong.toFixed(digits)}`,
    },
    {
      name: `Bollinger (${zone.bbPeriod}, ${zone.bbStd})`,
      vote: bbVote,
      summary: `M=${bbMiddle.toFixed(digits)} [${bbLower.toFixed(digits)}–${bbUpper.toFixed(digits)}]`,
    },
    {
      name: `RSI (${zone.rsiPeriod}) [${zone.rsiOverbought}/${zone.rsiOversold}]`,
      vote: rsiVote,
      summary: `${rsi.toFixed(1)}`,
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
      summary: `${atr.toFixed(digits)}`,
    },
    {
      name: `Tick Volume (MA ${zone.tickVolMa})`,
      vote: volVote,
      summary: `Ratio=${volRatio.toFixed(2)}x`,
    },
    {
      name: `Pivot Points (${zone.pivotHtf})`,
      vote: pivotVote,
      summary: `P=${pivotP.toFixed(digits)}`,
    },
  ];

  const buyCount = indicators.reduce((acc, ind) => acc + (ind.vote === 1 ? 1 : 0), 0);
  const sellCount = 8 - buyCount;
  const buyPct = Math.round((buyCount / 8) * 100);
  const sellPct = Math.round((sellCount / 8) * 100);
  const confluence = Math.max(buyCount, sellCount);

  let direction: SignalDirection = 'NEUTRE';
  let signalPct = 50;
  let signalLabel = '50% NEUTRE';

  if (buyPct > 50) {
    direction = 'ACHAT';
    signalPct = buyPct;
    signalLabel = `${buyPct}% ACHAT`;
  } else if (sellPct > 50) {
    direction = 'VENTE';
    signalPct = sellPct;
    signalLabel = `${sellPct}% VENTE`;
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
    confluence,
    confluenceLabel: `${confluence}/8`,
    core5Alignment,
    indicators,
  };
}
