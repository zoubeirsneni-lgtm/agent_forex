// server.ts
import express from "express";
import fs from "fs";
import http from "http";
import path from "path";
import { fileURLToPath } from "url";
import { createServer as createViteServer } from "vite";

// src/lib/pineForecast.ts
function computeEmaSeries(values, period) {
  const n = values.length;
  if (n === 0) return [];
  const k = 2 / (period + 1);
  const out = new Array(n);
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
function computeRmaSeries(values, period) {
  const n = values.length;
  if (n === 0) return [];
  const out = new Array(n);
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
function computeSmaSeries(values, period) {
  const n = values.length;
  if (n === 0) return [];
  const out = new Array(n);
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
function computeRsiLast(closes, period) {
  const n = closes.length;
  if (n < 2) return 50;
  const gains = new Array(n).fill(0);
  const losses = new Array(n).fill(0);
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
function computeTrueRangeSeries(candles) {
  const n = candles.length;
  if (n === 0) return [];
  const tr = new Array(n);
  tr[0] = candles[0].high - candles[0].low;
  for (let i = 1; i < n; i++) {
    const c = candles[i];
    const pc = candles[i - 1].close;
    tr[i] = Math.max(c.high - c.low, Math.abs(c.high - pc), Math.abs(c.low - pc));
  }
  return tr;
}
function computeNextCandlePredictor(candles) {
  const n = candles.length;
  if (n < 5) {
    return { longPct: 50, shortPct: 50, bias: "NEUTRE", strongSetup: false };
  }
  const closes = candles.map((c) => c.close);
  const vols = candles.map((c) => c.tickVolume);
  const trSeries = computeTrueRangeSeries(candles);
  const trendAtr = computeRmaSeries(trSeries, 10);
  let upperBand = 0;
  let lowerBand = 0;
  let trendDirection = 1;
  for (let i = 0; i < n; i++) {
    const hl2 = (candles[i].high + candles[i].low) / 2;
    const upperRaw = hl2 + 3 * trendAtr[i];
    const lowerRaw = hl2 - 3 * trendAtr[i];
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
  const volumeDeltas = new Array(n);
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const rng = c.high - c.low;
    const buyVol = rng > 0 ? c.tickVolume * (c.close - c.low) / rng : c.tickVolume * 0.5;
    const sellVol = rng > 0 ? c.tickVolume * (c.high - c.close) / rng : c.tickVolume * 0.5;
    volumeDeltas[i] = buyVol - sellVol;
  }
  const deltaEmaSeries = computeEmaSeries(volumeDeltas, 10);
  const volumeDelta = volumeDeltas[n - 1];
  const deltaEma = deltaEmaSeries[n - 1];
  const deltaMomentum = volumeDelta > deltaEma;
  const deltaBullish = volumeDelta > 0;
  const deltaBearish = volumeDelta < 0;
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
  const stochRaw = new Array(n);
  for (let i = 0; i < n; i++) {
    const start = Math.max(0, i - 14 + 1);
    let hi = -Infinity;
    let lo = Infinity;
    for (let j = start; j <= i; j++) {
      if (candles[j].high > hi) hi = candles[j].high;
      if (candles[j].low < lo) lo = candles[j].low;
    }
    const span = hi - lo;
    stochRaw[i] = span > 0 ? (candles[i].close - lo) / span * 100 : 50;
  }
  const stochDSeries = computeSmaSeries(stochRaw, 3);
  const stochK = stochRaw[n - 1];
  const stochD = stochDSeries[n - 1];
  const volSmaSeries = computeSmaSeries(vols, 20);
  const volSma = volSmaSeries[n - 1];
  const volRatio = volSma > 0 ? vols[n - 1] / volSma : 1;
  const plusDM = new Array(n).fill(0);
  const minusDM = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    const upMove = candles[i].high - candles[i - 1].high;
    const downMove = candles[i - 1].low - candles[i].low;
    plusDM[i] = upMove > downMove && upMove > 0 ? upMove : 0;
    minusDM[i] = downMove > upMove && downMove > 0 ? downMove : 0;
  }
  const plusRma = computeRmaSeries(plusDM, 14);
  const minusRma = computeRmaSeries(minusDM, 14);
  const dxSeries = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    const t = atrSeries[i];
    const diPlus = t > 0 ? 100 * plusRma[i] / t : 0;
    const diMinus = t > 0 ? 100 * minusRma[i] / t : 0;
    const denom = diPlus + diMinus;
    dxSeries[i] = denom > 0 ? 100 * Math.abs(diPlus - diMinus) / denom : 0;
  }
  const adxSeries = computeRmaSeries(dxSeries, 14);
  const adxValue = adxSeries[n - 1];
  let atrPercentile = 50;
  if (n >= 2) {
    const endIdx = n - 2;
    const startIdx = Math.max(0, endIdx - 99);
    const count = endIdx - startIdx + 1;
    let leCount = 0;
    for (let i = startIdx; i <= endIdx; i++) {
      if (atrSeries[i] <= atrNow) leCount += 1;
    }
    atrPercentile = leCount / count * 100;
  }
  const volMultiplier = atrPercentile > 75 ? 0.85 : atrPercentile < 25 ? 1.15 : 1;
  const dynamicThreshold = adxValue > 30 ? 55 : adxValue > 25 ? 60 : adxValue > 20 ? 65 : 70;
  const macdScoreLong = macdLine > signalLine && macdHist > 0 ? 100 : macdLine > signalLine ? 70 : macdHist > 0 ? 50 : 20;
  const macdScoreShort = macdLine < signalLine && macdHist < 0 ? 100 : macdLine < signalLine ? 70 : macdHist < 0 ? 50 : 20;
  const rsiScoreLong = rsi < 30 ? 100 : rsi < 40 ? 85 : rsi < 50 ? 70 : rsi < 60 ? 50 : 25;
  const rsiScoreShort = rsi > 70 ? 100 : rsi > 60 ? 85 : rsi > 50 ? 70 : rsi > 40 ? 50 : 25;
  const stochScoreLong = stochK > stochD && stochK < 20 ? 100 : stochK > stochD && stochK < 50 ? 85 : stochK > stochD ? 65 : 25;
  const stochScoreShort = stochK < stochD && stochK > 80 ? 100 : stochK < stochD && stochK > 50 ? 85 : stochK < stochD ? 65 : 25;
  const volScore = volRatio > 2 ? 100 : volRatio > 1.5 ? 80 : volRatio > 1 ? 60 : volRatio > 0.8 ? 45 : 25;
  const deltaScoreLong = volumeDelta > 0 && deltaMomentum ? 100 : volumeDelta > 0 ? 75 : volumeDelta > -Math.abs(deltaEma) ? 40 : 20;
  const deltaScoreShort = volumeDelta < 0 && !deltaMomentum ? 100 : volumeDelta < 0 ? 75 : volumeDelta < Math.abs(deltaEma) ? 40 : 20;
  const adxScore = adxValue > 35 ? 100 : adxValue > 30 ? 85 : adxValue > 25 ? 70 : adxValue > 20 ? 50 : 30;
  const trendScoreLong = isUptrend && ema8 > ema21 && ema21 > ema50 ? 100 : isUptrend && ema8 > ema21 ? 80 : isUptrend ? 60 : 0;
  const trendScoreShort = isDowntrend && ema8 < ema21 && ema21 < ema50 ? 100 : isDowntrend && ema8 < ema21 ? 80 : isDowntrend ? 60 : 0;
  const longScoreRaw = trendScoreLong * 0.23 + macdScoreLong * 0.18 + deltaScoreLong * 0.15 + rsiScoreLong * 0.12 + stochScoreLong * 0.12 + adxScore * 0.1 + volScore * 0.1;
  const shortScoreRaw = trendScoreShort * 0.23 + macdScoreShort * 0.18 + deltaScoreShort * 0.15 + rsiScoreShort * 0.12 + stochScoreShort * 0.12 + adxScore * 0.1 + volScore * 0.1;
  const longScore = Math.round(Math.min(100, Math.max(0, longScoreRaw * volMultiplier)));
  const shortScore = Math.round(Math.min(100, Math.max(0, shortScoreRaw * volMultiplier)));
  const totalRaw = longScore + shortScore;
  const longPct = totalRaw > 0 ? Math.round(longScore / totalRaw * 100) : 50;
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
  const longPerfect = isUptrend && longPct >= dynamicThreshold && confluenceLong >= 5 && volumeOk && rsiAbove50 && deltaBullish;
  const shortPerfect = isDowntrend && shortPct >= dynamicThreshold && confluenceShort >= 5 && volumeOk && rsiBelow50 && deltaBearish;
  const bias = longPct > shortPct ? "HAUSSE" : shortPct > longPct ? "BAISSE" : "NEUTRE";
  return {
    longPct,
    shortPct,
    bias,
    strongSetup: longPerfect || shortPerfect
  };
}
function computeBreakoutProbability(candles) {
  const n = candles.length;
  if (n < 3) {
    return { upPct: 50, dnPct: 50, bias: "NEUTRE", winRate: null };
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
      a1 = Number((ghh / gTotal * 100).toFixed(2));
    }
    if (green && ll && gTotal > 0) {
      gll += 1;
      b1 = Number((gll / gTotal * 100).toFixed(2));
    }
    if (red && hh && rTotal > 0) {
      rhh += 1;
      a2 = Number((rhh / rTotal * 100).toFixed(2));
    }
    if (red && ll && rTotal > 0) {
      rll += 1;
      b2 = Number((rll / rTotal * 100).toFixed(2));
    }
    const v = green ? Math.max(a1, b1) === a1 ? prev.high : prev.low : Math.max(a2, b2) === a2 ? prev.high : prev.low;
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
  const rawUp = lastGreen ? hasGreen ? ghh / gTotal * 100 : 50 : hasRed ? rhh / rTotal * 100 : hasGreen ? ghh / gTotal * 100 : 50;
  const rawDn = lastGreen ? hasGreen ? gll / gTotal * 100 : 50 : hasRed ? rll / rTotal * 100 : hasGreen ? gll / gTotal * 100 : 50;
  const upPct = Number(rawUp.toFixed(1));
  const dnPct = Number(rawDn.toFixed(1));
  const bias = upPct > dnPct ? "HAUSSE" : dnPct > upPct ? "BAISSE" : "NEUTRE";
  const totalTrades = wins + losses;
  const winRate = totalTrades > 0 ? Number((wins / totalTrades * 100).toFixed(1)) : null;
  return { upPct, dnPct, bias, winRate };
}
function computeLevelsStrengthIndex(candles) {
  const n = candles.length;
  if (n < 2) {
    return { bullPct: 50, bearPct: 50, bias: "NEUTRE" };
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
  const bias = clamped > 5 ? "HAUSSE" : clamped < 5 ? "BAISSE" : "NEUTRE";
  return { bullPct, bearPct, bias };
}
function computePineForecast(candles) {
  return {
    nextCandle: computeNextCandlePredictor(candles),
    breakout: computeBreakoutProbability(candles),
    levelsStrength: computeLevelsStrengthIndex(candles)
  };
}

// src/lib/forexEngine.ts
var PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"];
var TIMEFRAMES = ["30s", "1m", "3m", "5m", "10m", "15m"];
var ZONE_CONFIG_BY_TF = {
  "30s": {
    zoneId: 1,
    zoneLabel: "Zone 1 (30s)",
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
    pivotHtf: "M15"
  },
  "1m": {
    zoneId: 2,
    zoneLabel: "Zone 2 (1m, 3m)",
    emaShort: 9,
    emaLong: 21,
    bbPeriod: 14,
    bbStd: 2,
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
    pivotHtf: "H1"
  },
  "3m": {
    zoneId: 2,
    zoneLabel: "Zone 2 (1m, 3m)",
    emaShort: 9,
    emaLong: 21,
    bbPeriod: 14,
    bbStd: 2,
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
    pivotHtf: "H1"
  },
  "5m": {
    zoneId: 3,
    zoneLabel: "Zone 3 (5m)",
    emaShort: 12,
    emaLong: 26,
    bbPeriod: 16,
    bbStd: 2,
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
    pivotHtf: "H4"
  },
  "10m": {
    zoneId: 4,
    zoneLabel: "Zone 4 (10m)",
    emaShort: 13,
    emaLong: 34,
    bbPeriod: 20,
    bbStd: 2,
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
    pivotHtf: "H4"
  },
  "15m": {
    zoneId: 5,
    zoneLabel: "Zone 5 (15m)",
    emaShort: 21,
    emaLong: 50,
    bbPeriod: 20,
    bbStd: 2,
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
    pivotHtf: "D1"
  }
};
function computeEmaSeries2(values, period) {
  if (values.length === 0) return [];
  const k = 2 / (period + 1);
  const result = new Array(values.length);
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
function computeSma(values, period) {
  const slice = values.slice(-period);
  if (slice.length === 0) return 0;
  return slice.reduce((acc, v) => acc + v, 0) / slice.length;
}
function computeStdDev(values, period, mean) {
  const slice = values.slice(-period);
  if (slice.length === 0) return 0;
  const variance = slice.reduce((acc, v) => acc + (v - mean) ** 2, 0) / slice.length;
  return Math.sqrt(variance);
}
function computeRsi(closes, period) {
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
function computeMacdHistogram(closes, fast, slow, signalPeriod) {
  const emaFast = computeEmaSeries2(closes, fast);
  const emaSlow = computeEmaSeries2(closes, slow);
  const macdLine = emaFast.map((f, idx) => f - emaSlow[idx]);
  const signalLine = computeEmaSeries2(macdLine, signalPeriod);
  const lastIdx = macdLine.length - 1;
  return macdLine[lastIdx] - signalLine[lastIdx];
}
function computeStochastic(candles, kPeriod, smoothK, dPeriod) {
  const rawK = [];
  for (let i = 0; i < candles.length; i++) {
    const start = Math.max(0, i - kPeriod + 1);
    let highest = -Infinity;
    let lowest = Infinity;
    for (let j = start; j <= i; j++) {
      if (candles[j].high > highest) highest = candles[j].high;
      if (candles[j].low < lowest) lowest = candles[j].low;
    }
    const span = highest - lowest;
    rawK.push(span === 0 ? 50 : (candles[i].close - lowest) / span * 100);
  }
  const slowedK = [];
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
function computeAtrStats(candles, period) {
  if (candles.length < 2) return { atrNow: 0, atrRatio: 1 };
  const trs = [];
  for (let i = 1; i < candles.length; i++) {
    const cur = candles[i];
    const prevClose = candles[i - 1].close;
    const tr = Math.max(cur.high - cur.low, Math.abs(cur.high - prevClose), Math.abs(cur.low - prevClose));
    trs.push(tr);
  }
  const seedLen = Math.min(period, trs.length);
  let atr = trs.slice(0, seedLen).reduce((a, b) => a + b, 0) / seedLen;
  const atrSeries = [atr];
  for (let i = seedLen; i < trs.length; i++) {
    atr = (atr * (period - 1) + trs[i]) / period;
    atrSeries.push(atr);
  }
  const atrNow = atrSeries[atrSeries.length - 1] ?? 0;
  const baselineSlice = atrSeries.slice(-20);
  const atrMean = baselineSlice.length > 0 ? baselineSlice.reduce((acc, v) => acc + v, 0) / baselineSlice.length : atrNow;
  const atrRatio = atrMean > 0 ? atrNow / atrMean : 1;
  return { atrNow, atrRatio };
}
function analyzeTimeframe(pair, timeframe, candles, htfPivotCandle) {
  const zone = ZONE_CONFIG_BY_TF[timeframe];
  const closes = candles.map((c) => c.close);
  const volumes = candles.map((c) => c.tickVolume);
  const current = candles[candles.length - 1];
  const prev = candles[candles.length - 2] ?? current;
  const digits = pair === "USDJPYm" ? 3 : 5;
  const isEntryTf = timeframe === "30s" || timeframe === "1m" || timeframe === "3m";
  const emaShortArr = computeEmaSeries2(closes, zone.emaShort);
  const emaLongArr = computeEmaSeries2(closes, zone.emaLong);
  const emaShort = emaShortArr[emaShortArr.length - 1];
  const emaLong = emaLongArr[emaLongArr.length - 1];
  const emaVote = emaShort > emaLong ? 1 : emaShort < emaLong ? -1 : 0;
  const bbMiddle = computeSma(closes, zone.bbPeriod);
  const bbStd = computeStdDev(closes, zone.bbPeriod, bbMiddle);
  const bbUpper = bbMiddle + zone.bbStd * bbStd;
  const bbLower = bbMiddle - zone.bbStd * bbStd;
  let bbVote;
  let bbTag = "";
  if (isEntryTf && current.close >= bbUpper) {
    bbVote = 0;
    bbTag = " \xB7 Hors bande +";
  } else if (isEntryTf && current.close <= bbLower) {
    bbVote = 0;
    bbTag = " \xB7 Hors bande -";
  } else {
    bbVote = current.close > bbMiddle ? 1 : current.close < bbMiddle ? -1 : 0;
  }
  const rsi = computeRsi(closes, zone.rsiPeriod);
  let rsiVote;
  let rsiTag = "";
  if (rsi >= zone.rsiOverbought) {
    rsiVote = 0;
    rsiTag = " [Surachat]";
  } else if (rsi <= zone.rsiOversold) {
    rsiVote = 0;
    rsiTag = " [Survente]";
  } else if (rsi > 50) {
    rsiVote = 1;
  } else if (rsi < 50) {
    rsiVote = -1;
  } else {
    rsiVote = 0;
  }
  const macdHist = computeMacdHistogram(closes, zone.macdFast, zone.macdSlow, zone.macdSignal);
  const macdVote = macdHist > 0 ? 1 : macdHist < 0 ? -1 : 0;
  const stoch = computeStochastic(candles, zone.stochK, zone.stochSmooth, zone.stochD);
  const stochVote = stoch.k > stoch.d ? 1 : stoch.k < stoch.d ? -1 : 0;
  const { atrNow, atrRatio } = computeAtrStats(candles, zone.atrPeriod);
  let atrVote;
  let atrTag = "";
  if (atrRatio < 0.85) {
    atrVote = 0;
    atrTag = " (Calme)";
  } else if (!isEntryTf && Math.abs(current.close - prev.close) < 0.25 * atrNow) {
    atrVote = 0;
    atrTag = " (Neutre)";
  } else if (current.close > prev.close) {
    atrVote = 1;
  } else if (current.close < prev.close) {
    atrVote = -1;
  } else {
    atrVote = 0;
  }
  const volMa = computeSma(volumes, zone.tickVolMa);
  const volRatio = volMa > 0 ? current.tickVolume / volMa : 1;
  let volVote;
  let volTag = "";
  if (volRatio <= 1) {
    volVote = 0;
    volTag = " (Faible)";
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
  const pivotP = (htfPivotCandle.high + htfPivotCandle.low + htfPivotCandle.close) / 3;
  const pivotVote = current.close > pivotP ? 1 : current.close < pivotP ? -1 : 0;
  const indicators = [
    {
      name: `EMA (${zone.emaShort}/${zone.emaLong})`,
      vote: emaVote,
      summary: `${emaShort.toFixed(digits)} vs ${emaLong.toFixed(digits)}`
    },
    {
      name: `Bollinger (${zone.bbPeriod}, ${zone.bbStd})`,
      vote: bbVote,
      summary: `M=${bbMiddle.toFixed(digits)} [${bbLower.toFixed(digits)}\u2013${bbUpper.toFixed(digits)}]${bbTag}`
    },
    {
      name: `RSI (${zone.rsiPeriod}) [${zone.rsiOverbought}/${zone.rsiOversold}]`,
      vote: rsiVote,
      summary: `${rsi.toFixed(1)}${rsiTag}`
    },
    {
      name: `MACD (${zone.macdFast}/${zone.macdSlow}/${zone.macdSignal})`,
      vote: macdVote,
      summary: `Hist=${macdHist >= 0 ? "+" : ""}${macdHist.toFixed(digits + 1)}`
    },
    {
      name: `Stochastique (${zone.stochK}/${zone.stochSmooth}/${zone.stochD})`,
      vote: stochVote,
      summary: `%K=${stoch.k.toFixed(1)} / %D=${stoch.d.toFixed(1)}`
    },
    {
      name: `ATR (${zone.atrPeriod})`,
      vote: atrVote,
      summary: `${atrNow.toFixed(digits)} (${atrRatio.toFixed(2)}x)${atrTag}`
    },
    {
      name: `Tick Volume (MA ${zone.tickVolMa})`,
      vote: volVote,
      summary: `Ratio=${volRatio.toFixed(2)}x${volTag}`
    },
    {
      name: `Pivot Points (${zone.pivotHtf})`,
      vote: pivotVote,
      summary: `P=${pivotP.toFixed(digits)}`
    }
  ];
  const buyCount = indicators.reduce((acc, ind) => acc + (ind.vote === 1 ? 1 : 0), 0);
  const sellCount = indicators.reduce((acc, ind) => acc + (ind.vote === -1 ? 1 : 0), 0);
  const neutralCount = 8 - buyCount - sellCount;
  const confluence = Math.max(buyCount, sellCount);
  let direction = "NEUTRE";
  let signalPct = Math.round(confluence / 8 * 100);
  let signalLabel = "NEUTRE";
  if (buyCount >= 5 && buyCount > sellCount) {
    direction = "ACHAT";
    signalPct = Math.round(buyCount / 8 * 100);
    signalLabel = `${signalPct}% ACHAT`;
  } else if (sellCount >= 5 && sellCount > buyCount) {
    direction = "VENTE";
    signalPct = Math.round(sellCount / 8 * 100);
    signalLabel = `${signalPct}% VENTE`;
  }
  const core5Votes = [emaVote, bbVote, rsiVote, macdVote, stochVote];
  const core5Alignment = core5Votes.every((v) => v === 1) ? "ACHAT" : core5Votes.every((v) => v === -1) ? "VENTE" : null;
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
    atrValue: atrNow,
    atrRatio,
    volRatio,
    indicators,
    pineForecast: computePineForecast(candles)
  };
}
function collectSwingCandidates(candles, tfLabel, lookback) {
  const slice = candles.slice(-lookback);
  const out = [];
  if (slice.length < 7) return out;
  const w = 2;
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
    if (isSwingHigh) out.push({ price: h, kind: "resistance", source: `Sommet ${tfLabel}` });
    if (isSwingLow) out.push({ price: l, kind: "support", source: `Creux ${tfLabel}` });
  }
  const closed = slice.slice(0, -1);
  if (closed.length > 0) {
    let maxH = -Infinity;
    let minL = Infinity;
    for (const c of closed) {
      if (c.high > maxH) maxH = c.high;
      if (c.low < minL) minL = c.low;
    }
    if (Number.isFinite(maxH)) out.push({ price: maxH, kind: "resistance", source: `Haut ${tfLabel}` });
    if (Number.isFinite(minL)) out.push({ price: minL, kind: "support", source: `Bas ${tfLabel}` });
  }
  return out;
}
function computeSupportResistance(pair, currentPrice, candles1m, candles5m, h1Candle, h4Candle) {
  const pip = pair === "USDJPYm" ? 0.01 : 1e-4;
  const candidates = [];
  for (const s of collectSwingCandidates(candles1m, "1m", 80)) {
    candidates.push({ price: s.price, source: s.source });
  }
  for (const s of collectSwingCandidates(candles5m, "5m", 60)) {
    candidates.push({ price: s.price, source: s.source });
  }
  for (const [label, bar] of [
    ["H1", h1Candle],
    ["H4", h4Candle]
  ]) {
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
  let bestSupport = null;
  let bestResistance = null;
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
  const support = bestSupport ? {
    price: bestSupport.price,
    distancePips: Number(((currentPrice - bestSupport.price) / pip).toFixed(1)),
    source: bestSupport.source
  } : null;
  const resistance = bestResistance ? {
    price: bestResistance.price,
    distancePips: Number(((bestResistance.price - currentPrice) / pip).toFixed(1)),
    source: bestResistance.source
  } : null;
  const nearSupport = bestSupport !== null && currentPrice - bestSupport.price <= thresholdPrice;
  const nearResistance = bestResistance !== null && bestResistance.price - currentPrice <= thresholdPrice;
  let proximityAlert = "CLEAR";
  if (nearSupport && nearResistance) proximityAlert = "NEAR_BOTH";
  else if (nearResistance) proximityAlert = "NEAR_RESISTANCE";
  else if (nearSupport) proximityAlert = "NEAR_SUPPORT";
  return {
    support,
    resistance,
    proximityAlert,
    thresholdPips
  };
}

// server.ts
var __filename = fileURLToPath(import.meta.url);
var __dirname = path.dirname(__filename);
var PORT = Number(process.env.PORT) || 3e3;
var YAHOO_SYMBOL = {
  EURUSDm: "EURUSD=X",
  GBPUSDm: "GBPUSD=X",
  USDJPYm: "JPY=X",
  AUDUSDm: "AUDUSD=X"
};
var BASE_SPOT = {
  EURUSDm: 1.0842,
  GBPUSDm: 1.2678,
  USDJPYm: 153.45,
  AUDUSDm: 0.6548
};
var BASE_SPREAD_PIPS = {
  EURUSDm: 0.7,
  GBPUSDm: 1,
  USDJPYm: 0.8,
  AUDUSDm: 1.1
};
var TF_SECONDS = {
  "30s": 30,
  "1m": 60,
  "3m": 180,
  "5m": 300,
  "10m": 600,
  "15m": 900
};
var HTF_SECONDS = {
  M15: 900,
  H1: 3600,
  H4: 14400,
  D1: 86400
};
var marketStore = {};
function pipSize(pair) {
  return pair === "USDJPYm" ? 0.01 : 1e-4;
}
function generateInitialSeries(pair, spot, stepSec, count) {
  const nowSec = Math.floor(Date.now() / 1e3);
  const alignedEnd = nowSec - nowSec % stepSec;
  const pip = pipSize(pair);
  const volScale = Math.sqrt(stepSec / 60);
  const candles = new Array(count);
  let price = spot;
  const prices = [price];
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
      tickVolume: baseVol
    };
  }
  return candles;
}
function initMarketStore() {
  for (const pair of PAIRS) {
    const spot = BASE_SPOT[pair];
    const tfCandles = {};
    for (const tf of TIMEFRAMES) {
      tfCandles[tf] = generateInitialSeries(pair, spot, TF_SECONDS[tf], 300);
    }
    const pip = pipSize(pair);
    const htfCandles = {
      M15: { high: spot + pip * 14, low: spot - pip * 12, close: spot - pip * 2 },
      H1: { high: spot + pip * 28, low: spot - pip * 24, close: spot + pip * 3 },
      H4: { high: spot + pip * 52, low: spot - pip * 46, close: spot - pip * 5 },
      D1: { high: spot + pip * 85, low: spot - pip * 78, close: spot + pip * 11 }
    };
    marketStore[pair] = {
      spot,
      lastYahooSync: 0,
      tfCandles,
      htfCandles,
      drift: (Math.random() - 0.5) * 0.3
    };
  }
}
initMarketStore();
async function fetchYahooChart(pair) {
  const symbol = YAHOO_SYMBOL[pair];
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1m&range=1d`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { "User-Agent": "Mozilla/5.0" }
    });
    if (!res.ok) return null;
    const json = await res.json();
    const result = json?.chart?.result?.[0];
    if (!result) return null;
    const metaPrice = Number(result.meta?.regularMarketPrice);
    const timestamps = result.timestamp || [];
    const quote = result.indicators?.quote?.[0];
    const candles1m = [];
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
            tickVolume: Math.max(10, Number(quote.volume?.[i] || 25 + i % 17 * 3))
          });
        }
      }
    }
    const spot = Number.isFinite(metaPrice) && metaPrice > 0 ? metaPrice : candles1m.length > 0 ? candles1m[candles1m.length - 1].close : 0;
    if (spot <= 0) return null;
    return { spot, candles1m: candles1m.length >= 60 ? candles1m.slice(-300) : void 0 };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
async function advancePairMarket(pair) {
  const state = marketStore[pair];
  const nowMs = Date.now();
  const nowSec = Math.floor(nowMs / 1e3);
  const pip = pipSize(pair);
  if (nowMs - state.lastYahooSync > 3e4) {
    state.lastYahooSync = nowMs;
    const live = await fetchYahooChart(pair);
    if (live) {
      state.spot = live.spot;
      if (live.candles1m) {
        state.tfCandles["1m"] = live.candles1m;
      }
      const recent = state.tfCandles["1m"].slice(-15);
      if (recent.length > 0) {
        state.htfCandles.M15 = {
          high: Math.max(...recent.map((c) => c.high)),
          low: Math.min(...recent.map((c) => c.low)),
          close: recent[recent.length - 1].close
        };
      }
    }
  }
  state.drift = state.drift * 0.85 + (Math.random() - 0.5) * 0.65;
  const delta = state.drift * pip * 1.4;
  state.spot = Math.max(pip * 10, state.spot + delta);
  for (const tf of TIMEFRAMES) {
    const step = TF_SECONDS[tf];
    const bucket = nowSec - nowSec % step;
    const list = state.tfCandles[tf];
    const last = list[list.length - 1];
    const tickBump = Math.round(8 + Math.random() * 24);
    if (!last || bucket > last.time) {
      const open = last ? last.close : state.spot;
      const close = state.spot;
      const newCandle = {
        time: bucket,
        open,
        high: Math.max(open, close) + pip * Math.random() * 0.8,
        low: Math.min(open, close) - pip * Math.random() * 0.8,
        close,
        tickVolume: tickBump
      };
      list.push(newCandle);
      if (list.length > 300) list.shift();
    } else {
      last.close = state.spot;
      last.high = Math.max(last.high, state.spot);
      last.low = Math.min(last.low, state.spot);
      last.tickVolume += tickBump;
    }
  }
  for (const htf of ["M15", "H1", "H4", "D1"]) {
    const step = HTF_SECONDS[htf];
    if (nowSec % step < 20) {
      const span = pip * (htf === "M15" ? 14 : htf === "H1" ? 28 : htf === "H4" ? 50 : 85);
      state.htfCandles[htf] = {
        high: state.spot + span * 0.55,
        low: state.spot - span * 0.45,
        close: state.spot - delta * 0.5
      };
    }
  }
}
async function startServer() {
  const app = express();
  const httpServer = http.createServer(app);
  app.use(express.json({ limit: "1mb" }));
  app.get("/api/market-snapshot", async (req, res) => {
    const source = String(req.query.source || "live");
    const bridgeUrl = String(req.query.bridgeUrl || "").trim();
    const updatedAt = (/* @__PURE__ */ new Date()).toLocaleString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
    if (source === "mt5_offline") {
      res.json({
        ok: false,
        status: "WAIT",
        message: "MetaTrader 5 temporairement injoignable",
        updatedAt
      });
      return;
    }
    if (source === "mt5_bridge" && bridgeUrl) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3500);
      try {
        const bridgeRes = await fetch(`${bridgeUrl.replace(/\/$/, "")}/snapshot`, {
          signal: controller.signal
        });
        if (!bridgeRes.ok) throw new Error(`HTTP ${bridgeRes.status}`);
        const bridgeData = await bridgeRes.json();
        res.json({ ok: true, ...bridgeData, updatedAt });
        return;
      } catch {
        res.json({
          ok: false,
          status: "WAIT",
          message: "Bridge MT5 local injoignable",
          updatedAt
        });
        return;
      } finally {
        clearTimeout(timer);
      }
    }
    const tfsParam = String(req.query.tfs || "").trim();
    const requestedTfs = tfsParam ? tfsParam.split(",").map((t) => t.trim()).filter((t) => TIMEFRAMES.includes(t)) : [...TIMEFRAMES];
    const targetTfs = requestedTfs.length > 0 ? requestedTfs : [...TIMEFRAMES];
    await Promise.all(PAIRS.map((pair) => advancePairMarket(pair)));
    const analysisByPair = {};
    const priceHistoryByPair = {};
    const supportResistanceByPair = {};
    const spreadByPair = {};
    for (const pair of PAIRS) {
      const state = marketStore[pair];
      analysisByPair[pair] = targetTfs.map((tf) => {
        const candles = state.tfCandles[tf];
        const htfCandle = state.htfCandles[tf === "30s" ? "M15" : tf === "1m" || tf === "3m" ? "H1" : tf === "5m" || tf === "10m" ? "H4" : "D1"];
        return analyzeTimeframe(pair, tf, candles, htfCandle);
      });
      priceHistoryByPair[pair] = state.tfCandles["30s"].slice(-40).map((c) => ({
        time: new Date(c.time * 1e3).toLocaleTimeString("fr-FR", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit"
        }),
        price: c.close
      }));
      supportResistanceByPair[pair] = computeSupportResistance(
        pair,
        state.spot,
        state.tfCandles["1m"],
        state.tfCandles["5m"],
        state.htfCandles.H1,
        state.htfCandles.H4
      );
      spreadByPair[pair] = Number(
        Math.max(0.4, BASE_SPREAD_PIPS[pair] + (Math.random() - 0.5) * 0.4).toFixed(1)
      );
    }
    res.json({
      ok: true,
      source: "live",
      updatedAt,
      analysisByPair,
      priceHistoryByPair,
      supportResistanceByPair,
      spreadByPair
    });
  });
  app.get("/api/python-agent", (_req, res) => {
    try {
      const pyDir = path.join(__dirname, "python_agent");
      const forexAgentPy = fs.readFileSync(path.join(pyDir, "forex_agent.py"), "utf-8");
      const requirementsTxt = fs.readFileSync(path.join(pyDir, "requirements.txt"), "utf-8");
      const launcherBat = fs.readFileSync(path.join(pyDir, "lancer_forex_agent.bat"), "utf-8");
      res.json({
        ok: true,
        files: [
          { name: "forex_agent.py", content: forexAgentPy },
          { name: "requirements.txt", content: requirementsTxt },
          { name: "lancer_forex_agent.bat", content: launcherBat }
        ]
      });
    } catch {
      res.status(500).json({ ok: false, error: "Fichiers Python introuvables" });
    }
  });
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        hmr: process.env.DISABLE_HMR === "true" ? false : { server: httpServer }
      },
      appType: "spa"
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(__dirname, "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }
  httpServer.listen(PORT, "0.0.0.0", () => {
    console.log(`[Forex Agent Dashboard] Serveur actif sur http://0.0.0.0:${PORT}`);
  });
  const shutdown = () => {
    console.log("\n[ARRET] Fermeture propre du serveur Forex Agent Dashboard...");
    httpServer.close(() => process.exit(0));
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
startServer();
