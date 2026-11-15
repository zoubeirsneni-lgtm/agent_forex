import type { Candle } from './forexEngine';

export type PineForecastBias = 'HAUSSE' | 'BAISSE' | 'NEUTRE';

export interface PineForecastInfo {
  nextCandle: {
    longPct: number;
    shortPct: number;
    bias: PineForecastBias;
    strongSetup: boolean;
  };
  breakout: {
    upPct: number;
    dnPct: number;
    bias: PineForecastBias;
    winRate: number | null;
  };
  levelsStrength: {
    bullPct: number;
    bearPct: number;
    bias: PineForecastBias;
  };
}

function computeEmaSeries(values: number[], period: number): number[] {
  const n = values.length;
  if (n === 0) return [];
  const k = 2 / (period + 1);
  const out = new Array<number>(n);
  const seedLen = Math.min(period, n);
  let sum = 0;
  for (let i = 0; i < seedLen; i++) sum += values[i];
  let ema = sum / seedLen;
  for (let i = 0; i < seedLen; i++) out[i] = ema;
  for (let i = seedLen; i < n; i++) {
    ema = values[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

function computeRmaSeries(values: number[], period: number): number[] {
  const n = values.length;
  if (n === 0) return [];
  const out = new Array<number>(n);
  const seedLen = Math.min(period, n);
  let sum = 0;
  for (let i = 0; i < seedLen; i++) {
    sum += values[i];
    out[i] = sum / (i + 1);
  }
  let rma = out[seedLen - 1];
  for (let i = seedLen; i < n; i++) {
    rma = (rma * (period - 1) + values[i]) / period;
    out[i] = rma;
  }
  return out;
}

function computeSmaSeries(values: number[], period: number): number[] {
  const n = values.length;
  if (n === 0) return [];
  const out = new Array<number>(n);
  let runningSum = 0;
  for (let i = 0; i < n; i++) {
    runningSum += values[i];
    if (i >= period) {
      runningSum -= values[i - period];
    }
    const count = Math.min(i + 1, period);
    out[i] = runningSum / count;
  }
  return out;
}

function computeRsiLast(closes: number[], period: number): number {
  const n = closes.length;
  if (n < 2) return 50;
  const gains = new Array<number>(n).fill(0);
  const losses = new Array<number>(n).fill(0);
  for (let i = 1; i < n; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains[i] = diff;
    else if (diff < 0) losses[i] = -diff;
  }
  const avgGain = computeRmaSeries(gains.slice(1), period);
  const avgLoss = computeRmaSeries(losses.slice(1), period);
  const g = avgGain[avgGain.length - 1] ?? 0;
  const l = avgLoss[avgLoss.length - 1] ?? 0;
  if (l === 0) return g === 0 ? 50 : 100;
  const rs = g / l;
  return 100 - 100 / (1 + rs);
}

function computeTrueRangeSeries(candles: Candle[]): number[] {
  const n = candles.length;
  if (n === 0) return [];
  const tr = new Array<number>(n);
  tr[0] = candles[0].high - candles[0].low;
  for (let i = 1; i < n; i++) {
    const c = candles[i];
    const pc = candles[i - 1].close;
    tr[i] = Math.max(c.high - c.low, Math.abs(c.high - pc), Math.abs(c.low - pc));
  }
  return tr;
}

function computeNextCandlePredictor(candles: Candle[]): PineForecastInfo['nextCandle'] {
  const n = candles.length;
  if (n < 5) {
    return { longPct: 50, shortPct: 50, bias: 'NEUTRE', strongSetup: false };
  }

  const closes = candles.map((c) => c.close);
  const vols = candles.map((c) => c.tickVolume);
  const trSeries = computeTrueRangeSeries(candles);

  // 1. Custom Supertrend (period = 10, factor = 3.0)
  const trendAtr = computeRmaSeries(trSeries, 10);
  let upperBand = 0;
  let lowerBand = 0;
  let trendDirection = 1;
  for (let i = 0; i < n; i++) {
    const hl2 = (candles[i].high + candles[i].low) / 2;
    const upperRaw = hl2 + 3.0 * trendAtr[i];
    const lowerRaw = hl2 - 3.0 * trendAtr[i];
    if (i === 0) {
      upperBand = upperRaw;
      lowerBand = lowerRaw;
      trendDirection = 1;
    } else {
      const prevClose = candles[i - 1].close;
      const prevUpper = upperBand;
      const prevLower = lowerBand;
      const prevDir = trendDirection;
      lowerBand = prevClose > prevLower ? Math.max(lowerRaw, prevLower) : lowerRaw;
      upperBand = prevClose < prevUpper ? Math.min(upperRaw, prevUpper) : upperRaw;
      if (prevDir === -1) {
        trendDirection = candles[i].close < lowerBand ? 1 : -1;
      } else {
        trendDirection = candles[i].close > upperBand ? -1 : 1;
      }
    }
  }
  const isUptrend = trendDirection === -1;
  const isDowntrend = trendDirection === 1;

  // 2. Estimated Volume Pressure
  const volumeDeltas = new Array<number>(n);
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const rng = c.high - c.low;
    const buyVol = rng > 0 ? (c.tickVolume * (c.close - c.low)) / rng : c.tickVolume * 0.5;
    const sellVol = rng > 0 ? (c.tickVolume * (c.high - c.close)) / rng : c.tickVolume * 0.5;
    volumeDeltas[i] = buyVol - sellVol;
  }
  const deltaEmaSeries = computeEmaSeries(volumeDeltas, 10);
  const volumeDelta = volumeDeltas[n - 1];
  const deltaEma = deltaEmaSeries[n - 1];
  const deltaMomentum = volumeDelta > deltaEma;
  const deltaBullish = volumeDelta > 0;
  const deltaBearish = volumeDelta < 0;

  // 3. Standard indicators
  const atrSeries = computeRmaSeries(trSeries, 14);
  const atrNow = atrSeries[n - 1];

  const ema8 = computeEmaSeries(closes, 8)[n - 1];
  const ema21 = computeEmaSeries(closes, 21)[n - 1];
  const ema50 = computeEmaSeries(closes, 50)[n - 1];

  const rsi = computeRsiLast(closes, 14);
  const rsiAbove50 = rsi > 50;
  const rsiBelow50 = rsi < 50;

  const ema12Series = computeEmaSeries(closes, 12);
  const ema26Series = computeEmaSeries(closes, 26);
  const macdSeries = ema12Series.map((v, idx) => v - ema26Series[idx]);
  const signalSeries = computeEmaSeries(macdSeries, 9);
  const macdLine = macdSeries[n - 1];
  const signalLine = signalSeries[n - 1];
  const macdHist = macdLine - signalLine;

  const stochRaw = new Array<number>(n);
  for (let i = 0; i < n; i++) {
    const start = Math.max(0, i - 14 + 1);
    let hi = -Infinity;
    let lo = Infinity;
    for (let j = start; j <= i; j++) {
      if (candles[j].high > hi) hi = candles[j].high;
      if (candles[j].low < lo) lo = candles[j].low;
    }
    const span = hi - lo;
    stochRaw[i] = span > 0 ? ((candles[i].close - lo) / span) * 100 : 50;
  }
  const stochDSeries = computeSmaSeries(stochRaw, 3);
  const stochK = stochRaw[n - 1];
  const stochD = stochDSeries[n - 1];

  const volSmaSeries = computeSmaSeries(vols, 20);
  const volSma = volSmaSeries[n - 1];
  const volRatio = volSma > 0 ? vols[n - 1] / volSma : 1.0;

  // 4. ADX / DMI (14, 14)
  const plusDM = new Array<number>(n).fill(0);
  const minusDM = new Array<number>(n).fill(0);
  for (let i = 1; i < n; i++) {
    const upMove = candles[i].high - candles[i - 1].high;
    const downMove = candles[i - 1].low - candles[i].low;
    plusDM[i] = upMove > downMove && upMove > 0 ? upMove : 0;
    minusDM[i] = downMove > upMove && downMove > 0 ? downMove : 0;
  }
  const plusRma = computeRmaSeries(plusDM, 14);
  const minusRma = computeRmaSeries(minusDM, 14);
  const dxSeries = new Array<number>(n).fill(0);
  for (let i = 0; i < n; i++) {
    const t = atrSeries[i];
    const diPlus = t > 0 ? (100 * plusRma[i]) / t : 0;
    const diMinus = t > 0 ? (100 * minusRma[i]) / t : 0;
    const denom = diPlus + diMinus;
    dxSeries[i] = denom > 0 ? (100 * Math.abs(diPlus - diMinus)) / denom : 0;
  }
  const adxSeries = computeRmaSeries(dxSeries, 14);
  const adxValue = adxSeries[n - 1];

  // 5. Volatility Regime (ta.percentrank(atr, 100))
  let atrPercentile = 50;
  if (n >= 2) {
    const endIdx = n - 2;
    const startIdx = Math.max(0, endIdx - 99);
    const count = endIdx - startIdx + 1;
    let leCount = 0;
    for (let i = startIdx; i <= endIdx; i++) {
      if (atrSeries[i] <= atrNow) leCount += 1;
    }
    atrPercentile = (leCount / count) * 100;
  }
  const volMultiplier = atrPercentile > 75 ? 0.85 : atrPercentile < 25 ? 1.15 : 1.0;
  const dynamicThreshold = adxValue > 30 ? 55 : adxValue > 25 ? 60 : adxValue > 20 ? 65 : 70;

  // 6. Scoring System
  const macdScoreLong =
    macdLine > signalLine && macdHist > 0 ? 100 : macdLine > signalLine ? 70 : macdHist > 0 ? 50 : 20;
  const macdScoreShort =
    macdLine < signalLine && macdHist < 0 ? 100 : macdLine < signalLine ? 70 : macdHist < 0 ? 50 : 20;

  const rsiScoreLong = rsi < 30 ? 100 : rsi < 40 ? 85 : rsi < 50 ? 70 : rsi < 60 ? 50 : 25;
  const rsiScoreShort = rsi > 70 ? 100 : rsi > 60 ? 85 : rsi > 50 ? 70 : rsi > 40 ? 50 : 25;

  const stochScoreLong =
    stochK > stochD && stochK < 20 ? 100 : stochK > stochD && stochK < 50 ? 85 : stochK > stochD ? 65 : 25;
  const stochScoreShort =
    stochK < stochD && stochK > 80 ? 100 : stochK < stochD && stochK > 50 ? 85 : stochK < stochD ? 65 : 25;

  const volScore = volRatio > 2.0 ? 100 : volRatio > 1.5 ? 80 : volRatio > 1.0 ? 60 : volRatio > 0.8 ? 45 : 25;

  const deltaScoreLong =
    volumeDelta > 0 && deltaMomentum
      ? 100
      : volumeDelta > 0
        ? 75
        : volumeDelta > -Math.abs(deltaEma)
          ? 40
          : 20;
  const deltaScoreShort =
    volumeDelta < 0 && !deltaMomentum
      ? 100
      : volumeDelta < 0
        ? 75
        : volumeDelta < Math.abs(deltaEma)
          ? 40
          : 20;

  const adxScore = adxValue > 35 ? 100 : adxValue > 30 ? 85 : adxValue > 25 ? 70 : adxValue > 20 ? 50 : 30;

  const trendScoreLong =
    isUptrend && ema8 > ema21 && ema21 > ema50 ? 100 : isUptrend && ema8 > ema21 ? 80 : isUptrend ? 60 : 0;
  const trendScoreShort =
    isDowntrend && ema8 < ema21 && ema21 < ema50
      ? 100
      : isDowntrend && ema8 < ema21
        ? 80
        : isDowntrend
          ? 60
          : 0;

  const longScoreRaw =
    trendScoreLong * 0.23 +
    macdScoreLong * 0.18 +
    deltaScoreLong * 0.15 +
    rsiScoreLong * 0.12 +
    stochScoreLong * 0.12 +
    adxScore * 0.1 +
    volScore * 0.1;
  const shortScoreRaw =
    trendScoreShort * 0.23 +
    macdScoreShort * 0.18 +
    deltaScoreShort * 0.15 +
    rsiScoreShort * 0.12 +
    stochScoreShort * 0.12 +
    adxScore * 0.1 +
    volScore * 0.1;

  const longScore = Math.round(Math.min(100, Math.max(0, longScoreRaw * volMultiplier)));
  const shortScore = Math.round(Math.min(100, Math.max(0, shortScoreRaw * volMultiplier)));
  const totalRaw = longScore + shortScore;
  const longPct = totalRaw > 0 ? Math.round((longScore / totalRaw) * 100) : 50;
  const shortPct = 100 - longPct;

  let confluenceLong = 0;
  if (isUptrend) confluenceLong += 1;
  if (ema8 > ema21) confluenceLong += 1;
  if (macdLine > signalLine) confluenceLong += 1;
  if (stochK > stochD) confluenceLong += 1;
  if (volRatio >= 0.8) confluenceLong += 1;
  if (adxValue > 25) confluenceLong += 1;
  if (rsiAbove50) confluenceLong += 1;
  if (deltaBullish) confluenceLong += 1;

  let confluenceShort = 0;
  if (isDowntrend) confluenceShort += 1;
  if (ema8 < ema21) confluenceShort += 1;
  if (macdLine < signalLine) confluenceShort += 1;
  if (stochK < stochD) confluenceShort += 1;
  if (volRatio >= 0.8) confluenceShort += 1;
  if (adxValue > 25) confluenceShort += 1;
  if (rsiBelow50) confluenceShort += 1;
  if (deltaBearish) confluenceShort += 1;

  const volumeOk = volRatio >= 0.8;
  const longPerfect =
    isUptrend && longPct >= dynamicThreshold && confluenceLong >= 5 && volumeOk && rsiAbove50 && deltaBullish;
  const shortPerfect =
    isDowntrend && shortPct >= dynamicThreshold && confluenceShort >= 5 && volumeOk && rsiBelow50 && deltaBearish;

  const bias: PineForecastBias = longPct > shortPct ? 'HAUSSE' : shortPct > longPct ? 'BAISSE' : 'NEUTRE';

  return {
    longPct,
    shortPct,
    bias,
    strongSetup: longPerfect || shortPerfect,
  };
}

function computeBreakoutProbability(candles: Candle[]): PineForecastInfo['breakout'] {
  const n = candles.length;
  if (n < 3) {
    return { upPct: 50, dnPct: 50, bias: 'NEUTRE', winRate: null };
  }

  let gTotal = 0;
  let rTotal = 0;
  let ghh = 0;
  let gll = 0;
  let rhh = 0;
  let rll = 0;
  let a1 = 0;
  let b1 = 0;
  let a2 = 0;
  let b2 = 0;
  let wins = 0;
  let losses = 0;
  let lastGreen = false;

  for (let i = 1; i < n; i++) {
    const prev = candles[i - 1];
    const cur = candles[i];
    const green = prev.close > prev.open;
    const red = prev.close < prev.open;
    lastGreen = green;

    if (green) gTotal += 1;
    if (red) rTotal += 1;

    const hh = cur.high >= prev.high;
    const ll = cur.low <= prev.low;

    if (green && hh && gTotal > 0) {
      ghh += 1;
      a1 = Number(((ghh / gTotal) * 100).toFixed(2));
    }
    if (green && ll && gTotal > 0) {
      gll += 1;
      b1 = Number(((gll / gTotal) * 100).toFixed(2));
    }
    if (red && hh && rTotal > 0) {
      rhh += 1;
      a2 = Number(((rhh / rTotal) * 100).toFixed(2));
    }
    if (red && ll && rTotal > 0) {
      rll += 1;
      b2 = Number(((rll / rTotal) * 100).toFixed(2));
    }

    const v = green
      ? Math.max(a1, b1) === a1
        ? prev.high
        : prev.low
      : Math.max(a2, b2) === a2
        ? prev.high
        : prev.low;

    if (v === prev.high) {
      if (cur.high >= v) wins += 1;
      else losses += 1;
    } else {
      if (cur.low <= v) wins += 1;
      else losses += 1;
    }
  }

  const hasGreen = gTotal > 0;
  const hasRed = rTotal > 0;
  const rawUp = lastGreen
    ? hasGreen
      ? (ghh / gTotal) * 100
      : 50
    : hasRed
      ? (rhh / rTotal) * 100
      : hasGreen
        ? (ghh / gTotal) * 100
        : 50;
  const rawDn = lastGreen
    ? hasGreen
      ? (gll / gTotal) * 100
      : 50
    : hasRed
      ? (rll / rTotal) * 100
      : hasGreen
        ? (gll / gTotal) * 100
        : 50;

  const upPct = Number(rawUp.toFixed(1));
  const dnPct = Number(rawDn.toFixed(1));
  const bias: PineForecastBias = upPct > dnPct ? 'HAUSSE' : dnPct > upPct ? 'BAISSE' : 'NEUTRE';
  const totalTrades = wins + losses;
  const winRate = totalTrades > 0 ? Number(((wins / totalTrades) * 100).toFixed(1)) : null;

  return { upPct, dnPct, bias, winRate };
}

function computeLevelsStrengthIndex(candles: Candle[]): PineForecastInfo['levelsStrength'] {
  const n = candles.length;
  if (n < 2) {
    return { bullPct: 50, bearPct: 50, bias: 'NEUTRE' };
  }

  const length = 20;
  const prevEnd = n - 2;
  const prevStart = Math.max(0, prevEnd - length + 1);
  let prevUpper = -Infinity;
  for (let i = prevStart; i <= prevEnd; i++) {
    if (candles[i].high > prevUpper) prevUpper = candles[i].high;
  }

  const curEnd = n - 1;
  const curStart = Math.max(0, curEnd - length + 1);
  let lowerBand = Infinity;
  let upperBand = -Infinity;
  for (let i = curStart; i <= curEnd; i++) {
    if (candles[i].low < lowerBand) lowerBand = candles[i].low;
    if (candles[i].high > upperBand) upperBand = candles[i].high;
  }

  const step = (upperBand - lowerBand) / 10;
  const srcNow = candles[curEnd].close;
  const srcPrev = candles[prevEnd].close;

  let strength = 0;
  for (let i = 0; i <= 10; i++) {
    const lvl = lowerBand + step * i;
    const crossUp = srcNow > lvl && srcPrev <= prevUpper;
    const crossDn = srcNow < lvl && srcPrev >= prevUpper;
    if (crossUp) strength += 1;
    if (crossDn) strength -= 1;
  }

  const clamped = Math.max(0, Math.min(10, strength));
  const bullPct = clamped * 10;
  const bearPct = 100 - bullPct;
  const bias: PineForecastBias = clamped > 5 ? 'HAUSSE' : clamped < 5 ? 'BAISSE' : 'NEUTRE';

  return { bullPct, bearPct, bias };
}

export interface PineConsensusInfo {
  label: string;
  bias: PineForecastBias;
  bullCount: number;
  bearCount: number;
}

export function getPineConsensus(pf?: PineForecastInfo | null): PineConsensusInfo {
  if (!pf) {
    return { label: '—', bias: 'NEUTRE', bullCount: 0, bearCount: 0 };
  }
  const biases: PineForecastBias[] = [
    pf.nextCandle.bias,
    pf.breakout.bias,
    pf.levelsStrength.bias,
  ];
  const bullCount = biases.filter((b) => b === 'HAUSSE').length;
  const bearCount = biases.filter((b) => b === 'BAISSE').length;

  if (bullCount === 3) {
    return { label: '3/3 Hausse', bias: 'HAUSSE', bullCount, bearCount };
  }
  if (bearCount === 3) {
    return { label: '3/3 Baisse', bias: 'BAISSE', bullCount, bearCount };
  }
  if (bullCount === 2 && bearCount <= 1) {
    return { label: '2/3 Hausse', bias: 'HAUSSE', bullCount, bearCount };
  }
  if (bearCount === 2 && bullCount <= 1) {
    return { label: '2/3 Baisse', bias: 'BAISSE', bullCount, bearCount };
  }
  return { label: 'Partagé', bias: 'NEUTRE', bullCount, bearCount };
}

export function computePineForecast(candles: Candle[]): PineForecastInfo {
  return {
    nextCandle: computeNextCandlePredictor(candles),
    breakout: computeBreakoutProbability(candles),
    levelsStrength: computeLevelsStrengthIndex(candles),
  };
}
