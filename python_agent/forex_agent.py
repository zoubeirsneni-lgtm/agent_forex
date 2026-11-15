#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forex Agent Dashboard - Agent autonome Windows 10 + MetaTrader 5 (Exness-MT5Trial16)
Surveillance temps réel de paires Forex et Or (dynamiques, jusqu'à 8 paires)
sur 6 timeframes (30s, 1m, 3m, 5m, 10m, 15m) avec 8 indicateurs techniques.
"""

import json
import os
import re
import signal
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # Permet de démarrer et d'afficher WAIT si MetaTrader5 n'est pas encore installé

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
DASHBOARD_HTML_PATH = DASHBOARD_DIR / "forex_dashboard.html"
PAIRS_CONFIG_PATH = DASHBOARD_DIR / "pairs_config.json"

MT5_SERVER = "Exness-MT5Trial16"
DEFAULT_PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"]
SUGGESTED_PAIRS = [
    "EURUSDm",
    "GBPUSDm",
    "USDJPYm",
    "AUDUSDm",
    "USDCADm",
    "USDCHFm",
    "NZDUSDm",
    "EURJPYm",
    "GBPJPYm",
    "EURGBPm",
    "AUDJPYm",
    "XAUUSDm",
]
MAX_ACTIVE_PAIRS = 8
HTTP_PORT_START = 8765
HTTP_PORT_END = 8775
TIMEFRAMES = ["30s", "1m", "3m", "5m", "10m", "15m"]


def normalize_symbol(raw: str) -> str:
    cleaned = re.sub(r"\s+", "", str(raw or "").strip())
    if not cleaned:
        return ""
    if re.fullmatch(r"[A-Za-z]{6}", cleaned):
        return cleaned.upper() + "m"
    if re.fullmatch(r"[A-Za-z]{6}[mM]", cleaned):
        return cleaned[:6].upper() + "m"
    return cleaned[:16]


def is_valid_trading_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{3,16}", symbol))


def get_pip_size(symbol: str) -> float:
    upper = symbol.upper()
    if "XAU" in upper or "GOLD" in upper:
        return 0.1
    if "JPY" in upper:
        return 0.01
    return 0.0001


def get_digits(symbol: str) -> int:
    upper = symbol.upper()
    if "XAU" in upper or "GOLD" in upper:
        return 2
    if "JPY" in upper:
        return 3
    return 5


def load_pairs_config() -> List[str]:
    try:
        if PAIRS_CONFIG_PATH.exists():
            raw = json.loads(PAIRS_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                cleaned: List[str] = []
                for item in raw:
                    if isinstance(item, str):
                        sym = normalize_symbol(item)
                        if sym and is_valid_trading_symbol(sym) and sym not in cleaned:
                            cleaned.append(sym)
                            if len(cleaned) >= MAX_ACTIVE_PAIRS:
                                break
                if cleaned:
                    return cleaned
    except Exception as exc:
        print(f"[INFO] Lecture pairs_config.json ignorée : {exc}")
    return list(DEFAULT_PAIRS)


def save_pairs_config(pairs: List[str]) -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = DASHBOARD_DIR / "pairs_config.tmp.json"
    tmp_path.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, PAIRS_CONFIG_PATH)


PAIRS = load_pairs_config()

# Paramètres stricts par zone
ZONES: Dict[str, Dict[str, Any]] = {
    "30s": {
        "zone": 1,
        "ema_short": 8, "ema_long": 21,
        "bb_period": 10, "bb_std": 1.5,
        "rsi_period": 5, "rsi_ob": 80, "rsi_os": 20,
        "macd_fast": 5, "macd_slow": 13, "macd_signal": 3,
        "stoch_k": 5, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 7,
        "vol_ma": 10,
        "pivot_htf": "M15",
    },
    "1m": {
        "zone": 2,
        "ema_short": 9, "ema_long": 21,
        "bb_period": 14, "bb_std": 2.0,
        "rsi_period": 7, "rsi_ob": 75, "rsi_os": 25,
        "macd_fast": 8, "macd_slow": 17, "macd_signal": 5,
        "stoch_k": 8, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 10,
        "vol_ma": 14,
        "pivot_htf": "H1",
    },
    "3m": {
        "zone": 2,
        "ema_short": 9, "ema_long": 21,
        "bb_period": 14, "bb_std": 2.0,
        "rsi_period": 7, "rsi_ob": 75, "rsi_os": 25,
        "macd_fast": 8, "macd_slow": 17, "macd_signal": 5,
        "stoch_k": 8, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 10,
        "vol_ma": 14,
        "pivot_htf": "H1",
    },
    "5m": {
        "zone": 3,
        "ema_short": 12, "ema_long": 26,
        "bb_period": 16, "bb_std": 2.0,
        "rsi_period": 10, "rsi_ob": 70, "rsi_os": 30,
        "macd_fast": 10, "macd_slow": 21, "macd_signal": 7,
        "stoch_k": 10, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 12,
        "vol_ma": 16,
        "pivot_htf": "H4",
    },
    "10m": {
        "zone": 4,
        "ema_short": 13, "ema_long": 34,
        "bb_period": 20, "bb_std": 2.0,
        "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "stoch_k": 14, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 14,
        "vol_ma": 20,
        "pivot_htf": "H4",
    },
    "15m": {
        "zone": 5,
        "ema_short": 21, "ema_long": 50,
        "bb_period": 20, "bb_std": 2.0,
        "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "stoch_k": 14, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 14,
        "vol_ma": 20,
        "pivot_htf": "D1",
    },
}

RUNNING = True
STATE_LOCK = threading.Lock()
ACTIVE_PAIRS: List[str] = list(PAIRS)
LATEST_RESULTS: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {p: {} for p in ACTIVE_PAIRS}
LATEST_SR: Dict[str, Optional[Dict[str, Any]]] = {p: None for p in ACTIVE_PAIRS}
LATEST_SPREAD: Dict[str, Optional[float]] = {p: None for p in ACTIVE_PAIRS}
LATEST_MT5_OK: bool = False
LATEST_UPDATED_AT: str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
LATEST_HTML: str = ""
HTTP_SERVER: Optional[ThreadingHTTPServer] = None


def handle_sigint(signum, frame):
    global RUNNING
    RUNNING = False
    print("\n[ARRET] Interruption Ctrl+C détectée. Fermeture propre de MetaTrader 5...")
    if HTTP_SERVER is not None:
        try:
            HTTP_SERVER.shutdown()
            HTTP_SERVER.server_close()
        except Exception:
            pass
    if mt5 is not None:
        try:
            mt5.shutdown()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigint)


# ==============================================================================
# CONNEXION & DONNÉES MT5
# ==============================================================================
def ensure_mt5_connected(pairs_list: Optional[List[str]] = None) -> bool:
    if mt5 is None:
        return False
    info = mt5.terminal_info()
    if info is None or mt5.account_info() is None:
        if not mt5.initialize():
            return False
        acct = mt5.account_info()
        if acct is None:
            return False
        if acct.server != MT5_SERVER:
            print(f"[INFO] Serveur MT5 actif : {acct.server} (attendu : {MT5_SERVER})")
    target_pairs = pairs_list if pairs_list is not None else ACTIVE_PAIRS
    for sym in target_pairs:
        mt5.symbol_select(sym, True)
    return True


def fetch_subminute_candles(symbol: str, seconds: int, count: int = 120) -> Optional[pd.DataFrame]:
    """Construit des bougies 30s à partir des ticks MT5."""
    if mt5 is None:
        return None
    now = datetime.now()
    lookback = timedelta(seconds=seconds * (count + 10))
    ticks = mt5.copy_ticks_from(symbol, now - lookback, 100000, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) < 10:
        return None
    df_ticks = pd.DataFrame(ticks)
    df_ticks["dt"] = pd.to_datetime(df_ticks["time"], unit="s")
    df_ticks["price"] = np.where(df_ticks["bid"] > 0, df_ticks["bid"], df_ticks["last"])
    df_ticks = df_ticks[df_ticks["price"] > 0].set_index("dt")
    if df_ticks.empty:
        return None
    rule = f"{seconds}s"
    ohlc = df_ticks["price"].resample(rule).ohlc().dropna()
    vol = df_ticks["price"].resample(rule).count().reindex(ohlc.index).fillna(1)
    ohlc["tick_volume"] = vol
    if len(ohlc) < 30:
        return None
    return ohlc.tail(count).reset_index()


def fetch_mt5_rates(symbol: str, tf_code: int, count: int = 150) -> Optional[pd.DataFrame]:
    if mt5 is None:
        return None
    rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, count)
    if rates is None or len(rates) < 30:
        return None
    return pd.DataFrame(rates)


def fetch_pivot_htf_candle(symbol: str, pivot_htf: str) -> Optional[Dict[str, float]]:
    if mt5 is None:
        return None
    tf_map = {
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    rates = mt5.copy_rates_from_pos(symbol, tf_map[pivot_htf], 1, 1)
    if rates is None or len(rates) == 0:
        rates = mt5.copy_rates_from_pos(symbol, tf_map[pivot_htf], 0, 1)
    if rates is None or len(rates) == 0:
        return None
    bar = rates[0]
    return {"high": float(bar["high"]), "low": float(bar["low"]), "close": float(bar["close"])}


# ==============================================================================
# CALCUL DES 8 INDICATEURS TECHNIQUES (VOTE 3 ÉTATS : +1 / 0 / -1)
# ==============================================================================
def compute_rsi(series: pd.Series, period: int) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    last_loss = float(avg_loss.iloc[-1])
    last_gain = float(avg_gain.iloc[-1])
    if last_loss == 0:
        return 50.0 if last_gain == 0 else 100.0
    rs = last_gain / last_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def compute_atr_stats(df: pd.DataFrame, period: int) -> Tuple[float, float]:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.ewm(alpha=1 / period, adjust=False).mean()
    atr_now = float(atr_series.iloc[-1])
    atr_mean = float(atr_series.tail(20).mean())
    atr_ratio = (atr_now / atr_mean) if atr_mean > 0 else 1.0
    return atr_now, atr_ratio


def _pf_ema(values: List[float], period: int) -> List[float]:
    n = len(values)
    if n == 0:
        return []
    k = 2.0 / (period + 1)
    out = [0.0] * n
    seed_len = min(period, n)
    ema = sum(values[:seed_len]) / seed_len
    for i in range(seed_len):
        out[i] = ema
    for i in range(seed_len, n):
        ema = values[i] * k + ema * (1.0 - k)
        out[i] = ema
    return out


def _pf_rma(values: List[float], period: int) -> List[float]:
    n = len(values)
    if n == 0:
        return []
    out = [0.0] * n
    seed_len = min(period, n)
    acc = 0.0
    for i in range(seed_len):
        acc += values[i]
        out[i] = acc / (i + 1)
    rma = out[seed_len - 1]
    for i in range(seed_len, n):
        rma = (rma * (period - 1) + values[i]) / period
        out[i] = rma
    return out


def _pf_sma(values: List[float], period: int) -> List[float]:
    n = len(values)
    if n == 0:
        return []
    out = [0.0] * n
    running = 0.0
    for i in range(n):
        running += values[i]
        if i >= period:
            running -= values[i - period]
        cnt = min(i + 1, period)
        out[i] = running / cnt
    return out


def _pf_rsi_last(closes: List[float], period: int) -> float:
    n = len(closes)
    if n < 2:
        return 50.0
    gains = [0.0] * (n - 1)
    losses = [0.0] * (n - 1)
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains[i - 1] = diff
        elif diff < 0:
            losses[i - 1] = -diff
    avg_gain = _pf_rma(gains, period)[-1]
    avg_loss = _pf_rma(losses, period)[-1]
    if avg_loss == 0.0:
        return 50.0 if avg_gain == 0.0 else 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_pine_forecast(df: pd.DataFrame) -> Dict[str, Any]:
    opens = df["open"].astype(float).tolist()
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    closes = df["close"].astype(float).tolist()
    vols = df["tick_volume"].astype(float).tolist()
    n = len(closes)

    # 1. Next Candle Predictor V4.1
    if n < 5:
        nc_res = {"longPct": 50, "shortPct": 50, "bias": "NEUTRE", "strongSetup": False}
    else:
        tr = [highs[0] - lows[0]]
        for i in range(1, n):
            pc = closes[i - 1]
            tr.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))

        trend_atr = _pf_rma(tr, 10)
        upper_band = 0.0
        lower_band = 0.0
        trend_dir = 1
        for i in range(n):
            hl2 = (highs[i] + lows[i]) / 2.0
            upper_raw = hl2 + 3.0 * trend_atr[i]
            lower_raw = hl2 - 3.0 * trend_atr[i]
            if i == 0:
                upper_band = upper_raw
                lower_band = lower_raw
                trend_dir = 1
            else:
                prev_c = closes[i - 1]
                prev_u = upper_band
                prev_l = lower_band
                prev_d = trend_dir
                lower_band = max(lower_raw, prev_l) if prev_c > prev_l else lower_raw
                upper_band = min(upper_raw, prev_u) if prev_c < prev_u else upper_raw
                if prev_d == -1:
                    trend_dir = 1 if closes[i] < lower_band else -1
                else:
                    trend_dir = -1 if closes[i] > upper_band else 1

        is_up = trend_dir == -1
        is_dn = trend_dir == 1

        vol_deltas = []
        for i in range(n):
            rng = highs[i] - lows[i]
            buy_v = (vols[i] * (closes[i] - lows[i]) / rng) if rng > 0 else vols[i] * 0.5
            sell_v = (vols[i] * (highs[i] - closes[i]) / rng) if rng > 0 else vols[i] * 0.5
            vol_deltas.append(buy_v - sell_v)
        delta_ema = _pf_ema(vol_deltas, 10)[-1]
        vol_delta = vol_deltas[-1]
        delta_mom = vol_delta > delta_ema
        delta_bull = vol_delta > 0
        delta_bear = vol_delta < 0

        atr_series = _pf_rma(tr, 14)
        atr_now = atr_series[-1]
        ema8 = _pf_ema(closes, 8)[-1]
        ema21 = _pf_ema(closes, 21)[-1]
        ema50 = _pf_ema(closes, 50)[-1]
        rsi_val = _pf_rsi_last(closes, 14)

        ema12_s = _pf_ema(closes, 12)
        ema26_s = _pf_ema(closes, 26)
        macd_s = [ema12_s[i] - ema26_s[i] for i in range(n)]
        sig_s = _pf_ema(macd_s, 9)
        macd_line = macd_s[-1]
        sig_line = sig_s[-1]
        macd_hist = macd_line - sig_line

        stoch_raw = []
        for i in range(n):
            s_idx = max(0, i - 13)
            hi = max(highs[s_idx:i + 1])
            lo = min(lows[s_idx:i + 1])
            span = hi - lo
            stoch_raw.append(((closes[i] - lo) / span) * 100.0 if span > 0 else 50.0)
        stoch_k = stoch_raw[-1]
        stoch_d = _pf_sma(stoch_raw, 3)[-1]

        vol_sma = _pf_sma(vols, 20)[-1]
        vol_ratio = (vols[-1] / vol_sma) if vol_sma > 0 else 1.0

        plus_dm = [0.0] * n
        minus_dm = [0.0] * n
        for i in range(1, n):
            up_m = highs[i] - highs[i - 1]
            dn_m = lows[i - 1] - lows[i]
            plus_dm[i] = up_m if (up_m > dn_m and up_m > 0) else 0.0
            minus_dm[i] = dn_m if (dn_m > up_m and dn_m > 0) else 0.0
        plus_rma = _pf_rma(plus_dm, 14)
        minus_rma = _pf_rma(minus_dm, 14)
        dx_series = []
        for i in range(n):
            t_val = atr_series[i]
            di_p = (100.0 * plus_rma[i] / t_val) if t_val > 0 else 0.0
            di_m = (100.0 * minus_rma[i] / t_val) if t_val > 0 else 0.0
            denom = di_p + di_m
            dx_series.append((100.0 * abs(di_p - di_m) / denom) if denom > 0 else 0.0)
        adx_val = _pf_rma(dx_series, 14)[-1]

        end_idx = n - 2
        start_idx = max(0, end_idx - 99)
        cnt_pct = end_idx - start_idx + 1
        le_cnt = sum(1 for i in range(start_idx, end_idx + 1) if atr_series[i] <= atr_now)
        atr_pct = (le_cnt / cnt_pct) * 100.0 if cnt_pct > 0 else 50.0
        vol_mult = 0.85 if atr_pct > 75 else (1.15 if atr_pct < 25 else 1.0)
        dyn_thresh = 55 if adx_val > 30 else (60 if adx_val > 25 else (65 if adx_val > 20 else 70))

        macd_l = 100 if (macd_line > sig_line and macd_hist > 0) else (70 if macd_line > sig_line else (50 if macd_hist > 0 else 20))
        macd_s_sc = 100 if (macd_line < sig_line and macd_hist < 0) else (70 if macd_line < sig_line else (50 if macd_hist < 0 else 20))

        rsi_l = 100 if rsi_val < 30 else (85 if rsi_val < 40 else (70 if rsi_val < 50 else (50 if rsi_val < 60 else 25)))
        rsi_s_sc = 100 if rsi_val > 70 else (85 if rsi_val > 60 else (70 if rsi_val > 50 else (50 if rsi_val > 40 else 25)))

        stoch_l = 100 if (stoch_k > stoch_d and stoch_k < 20) else (85 if (stoch_k > stoch_d and stoch_k < 50) else (65 if stoch_k > stoch_d else 25))
        stoch_s_sc = 100 if (stoch_k < stoch_d and stoch_k > 80) else (85 if (stoch_k < stoch_d and stoch_k > 50) else (65 if stoch_k < stoch_d else 25))

        vol_sc = 100 if vol_ratio > 2.0 else (80 if vol_ratio > 1.5 else (60 if vol_ratio > 1.0 else (45 if vol_ratio > 0.8 else 25)))
        delta_l = 100 if (vol_delta > 0 and delta_mom) else (75 if vol_delta > 0 else (40 if vol_delta > -abs(delta_ema) else 20))
        delta_s_sc = 100 if (vol_delta < 0 and not delta_mom) else (75 if vol_delta < 0 else (40 if vol_delta < abs(delta_ema) else 20))
        adx_sc = 100 if adx_val > 35 else (85 if adx_val > 30 else (70 if adx_val > 25 else (50 if adx_val > 20 else 30)))

        trend_l = 100 if (is_up and ema8 > ema21 and ema21 > ema50) else (80 if (is_up and ema8 > ema21) else (60 if is_up else 0))
        trend_s_sc = 100 if (is_dn and ema8 < ema21 and ema21 < ema50) else (80 if (is_dn and ema8 < ema21) else (60 if is_dn else 0))

        l_raw = trend_l * 0.23 + macd_l * 0.18 + delta_l * 0.15 + rsi_l * 0.12 + stoch_l * 0.12 + adx_sc * 0.1 + vol_sc * 0.1
        s_raw = trend_s_sc * 0.23 + macd_s_sc * 0.18 + delta_s_sc * 0.15 + rsi_s_sc * 0.12 + stoch_s_sc * 0.12 + adx_sc * 0.1 + vol_sc * 0.1

        l_score = round(min(100.0, max(0.0, l_raw * vol_mult)))
        s_score = round(min(100.0, max(0.0, s_raw * vol_mult)))
        tot = l_score + s_score
        long_pct = round((l_score / tot) * 100.0) if tot > 0 else 50
        short_pct = 100 - long_pct

        conf_l = sum([
            1 if is_up else 0,
            1 if ema8 > ema21 else 0,
            1 if macd_line > sig_line else 0,
            1 if stoch_k > stoch_d else 0,
            1 if vol_ratio >= 0.8 else 0,
            1 if adx_val > 25 else 0,
            1 if rsi_val > 50 else 0,
            1 if delta_bull else 0,
        ])
        conf_s = sum([
            1 if is_dn else 0,
            1 if ema8 < ema21 else 0,
            1 if macd_line < sig_line else 0,
            1 if stoch_k < stoch_d else 0,
            1 if vol_ratio >= 0.8 else 0,
            1 if adx_val > 25 else 0,
            1 if rsi_val < 50 else 0,
            1 if delta_bear else 0,
        ])
        vol_ok = vol_ratio >= 0.8
        l_perf = is_up and long_pct >= dyn_thresh and conf_l >= 5 and vol_ok and rsi_val > 50 and delta_bull
        s_perf = is_dn and short_pct >= dyn_thresh and conf_s >= 5 and vol_ok and rsi_val < 50 and delta_bear
        nc_bias = "HAUSSE" if long_pct > short_pct else ("BAISSE" if short_pct > long_pct else "NEUTRE")
        nc_res = {"longPct": long_pct, "shortPct": short_pct, "bias": nc_bias, "strongSetup": bool(l_perf or s_perf)}

    # 2. Breakout Probability (Expo)
    if n < 3:
        bo_res = {"upPct": 50.0, "dnPct": 50.0, "bias": "NEUTRE", "winRate": None}
    else:
        g_tot = r_tot = ghh = gll = rhh = rll = 0
        a1 = b1 = a2 = b2 = 0.0
        wins = losses = 0
        last_green = False
        for i in range(1, n):
            green = closes[i - 1] > opens[i - 1]
            red = closes[i - 1] < opens[i - 1]
            last_green = green
            if green:
                g_tot += 1
            if red:
                r_tot += 1
            hh = highs[i] >= highs[i - 1]
            ll = lows[i] <= lows[i - 1]
            if green and hh and g_tot > 0:
                ghh += 1
                a1 = round((ghh / g_tot) * 100.0, 2)
            if green and ll and g_tot > 0:
                gll += 1
                b1 = round((gll / g_tot) * 100.0, 2)
            if red and hh and r_tot > 0:
                rhh += 1
                a2 = round((rhh / r_tot) * 100.0, 2)
            if red and ll and r_tot > 0:
                rll += 1
                b2 = round((rll / r_tot) * 100.0, 2)
            if green:
                v = highs[i - 1] if max(a1, b1) == a1 else lows[i - 1]
            else:
                v = highs[i - 1] if max(a2, b2) == a2 else lows[i - 1]
            if v == highs[i - 1]:
                if highs[i] >= v:
                    wins += 1
                else:
                    losses += 1
            else:
                if lows[i] <= v:
                    wins += 1
                else:
                    losses += 1
        has_g = g_tot > 0
        has_r = r_tot > 0
        raw_up = ((ghh / g_tot) * 100.0 if has_g else 50.0) if last_green else (((rhh / r_tot) * 100.0 if has_r else ((ghh / g_tot) * 100.0 if has_g else 50.0)))
        raw_dn = ((gll / g_tot) * 100.0 if has_g else 50.0) if last_green else (((rll / r_tot) * 100.0 if has_r else ((gll / g_tot) * 100.0 if has_g else 50.0)))
        up_pct = round(raw_up, 1)
        dn_pct = round(raw_dn, 1)
        bo_bias = "HAUSSE" if up_pct > dn_pct else ("BAISSE" if dn_pct > up_pct else "NEUTRE")
        tot_tr = wins + losses
        wr = round((wins / tot_tr) * 100.0, 1) if tot_tr > 0 else None
        bo_res = {"upPct": up_pct, "dnPct": dn_pct, "bias": bo_bias, "winRate": wr}

    # 3. Levels Strength Index [BigBeluga]
    if n < 2:
        ls_res = {"bullPct": 50, "bearPct": 50, "bias": "NEUTRE"}
    else:
        prev_end = n - 2
        prev_start = max(0, prev_end - 19)
        prev_upper = max(highs[prev_start:prev_end + 1])
        cur_end = n - 1
        cur_start = max(0, cur_end - 19)
        lower_band_ls = min(lows[cur_start:cur_end + 1])
        upper_band_ls = max(highs[cur_start:cur_end + 1])
        step_ls = (upper_band_ls - lower_band_ls) / 10.0
        src_now = closes[cur_end]
        src_prev = closes[prev_end]
        strength = 0
        for i in range(11):
            lvl = lower_band_ls + step_ls * i
            if src_now > lvl and src_prev <= prev_upper:
                strength += 1
            if src_now < lvl and src_prev >= prev_upper:
                strength -= 1
        clamped = max(0, min(10, strength))
        bull_pct = clamped * 10
        bear_pct = 100 - bull_pct
        ls_bias = "HAUSSE" if clamped > 5 else ("BAISSE" if clamped < 5 else "NEUTRE")
        ls_res = {"bullPct": bull_pct, "bearPct": bear_pct, "bias": ls_bias}

    return {"nextCandle": nc_res, "breakout": bo_res, "levelsStrength": ls_res}


def analyze_pair_timeframe(symbol: str, tf: str) -> Optional[Dict[str, Any]]:
    cfg = ZONES[tf]
    if tf == "30s":
        df = fetch_subminute_candles(symbol, 30, 140)
    else:
        tf_map = {
            "1m": mt5.TIMEFRAME_M1,
            "3m": mt5.TIMEFRAME_M3,
            "5m": mt5.TIMEFRAME_M5,
            "10m": mt5.TIMEFRAME_M10,
            "15m": mt5.TIMEFRAME_M15,
        }
        df = fetch_mt5_rates(symbol, tf_map[tf], 300)

    htf_bar = fetch_pivot_htf_candle(symbol, cfg["pivot_htf"])
    if df is None or len(df) < 35 or htf_bar is None:
        return None

    close = df["close"].astype(float)
    open_p = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["tick_volume"].astype(float)

    c_now = float(close.iloc[-1])
    c_prev = float(close.iloc[-2])
    o_now = float(open_p.iloc[-1])
    is_entry_tf = tf in ("30s", "1m", "3m")

    # 1. EMA
    ema_s = float(close.ewm(span=cfg["ema_short"], adjust=False).mean().iloc[-1])
    ema_l = float(close.ewm(span=cfg["ema_long"], adjust=False).mean().iloc[-1])
    v_ema = 1 if ema_s > ema_l else (-1 if ema_s < ema_l else 0)

    # 2. Bollinger Bands (blocage à 0 hors bande sur 30s, 1m, 3m)
    bb_mid = float(close.rolling(cfg["bb_period"]).mean().iloc[-1])
    bb_std_val = float(close.rolling(cfg["bb_period"]).std(ddof=0).iloc[-1])
    bb_upper = bb_mid + cfg["bb_std"] * bb_std_val
    bb_lower = bb_mid - cfg["bb_std"] * bb_std_val
    bb_tag = ""
    if is_entry_tf and c_now >= bb_upper:
        v_bb = 0
        bb_tag = " · Hors bande +"
    elif is_entry_tf and c_now <= bb_lower:
        v_bb = 0
        bb_tag = " · Hors bande -"
    else:
        v_bb = 1 if c_now > bb_mid else (-1 if c_now < bb_mid else 0)

    # 3. RSI (blocage à 0 en surachat/survente)
    rsi_val = compute_rsi(close, cfg["rsi_period"])
    rsi_tag = ""
    if rsi_val >= cfg["rsi_ob"]:
        v_rsi = 0
        rsi_tag = " [Surachat]"
    elif rsi_val <= cfg["rsi_os"]:
        v_rsi = 0
        rsi_tag = " [Survente]"
    elif rsi_val > 50.0:
        v_rsi = 1
    elif rsi_val < 50.0:
        v_rsi = -1
    else:
        v_rsi = 0

    # 4. MACD
    ema_f = close.ewm(span=cfg["macd_fast"], adjust=False).mean()
    ema_sl = close.ewm(span=cfg["macd_slow"], adjust=False).mean()
    macd_line = ema_f - ema_sl
    sig_line = macd_line.ewm(span=cfg["macd_signal"], adjust=False).mean()
    macd_hist = float((macd_line - sig_line).iloc[-1])
    v_macd = 1 if macd_hist > 0 else (-1 if macd_hist < 0 else 0)

    # 5. Stochastic
    lowest_low = low.rolling(cfg["stoch_k"]).min()
    highest_high = high.rolling(cfg["stoch_k"]).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    raw_k = (100.0 * (close - lowest_low) / denom).fillna(50.0)
    k_line = raw_k.rolling(cfg["stoch_smooth"]).mean()
    d_line = k_line.rolling(cfg["stoch_d"]).mean()
    k_val = float(k_line.iloc[-1])
    d_val = float(d_line.iloc[-1])
    v_stoch = 1 if k_val > d_val else (-1 if k_val < d_val else 0)

    # 6. ATR (vrai filtre de volatilité : 0 si marché calme/plat)
    atr_val, atr_ratio = compute_atr_stats(df, cfg["atr_period"])
    atr_tag = ""
    if atr_ratio < 0.85:
        v_atr = 0
        atr_tag = " (Calme)"
    elif (not is_entry_tf) and abs(c_now - c_prev) < 0.25 * atr_val:
        v_atr = 0
        atr_tag = " (Neutre)"
    elif c_now > c_prev:
        v_atr = 1
    elif c_now < c_prev:
        v_atr = -1
    else:
        v_atr = 0

    # 7. Tick Volume (0 si ratio <= 1.0)
    vol_ma = float(vol.rolling(cfg["vol_ma"]).mean().iloc[-1])
    vol_ratio = (float(vol.iloc[-1]) / vol_ma) if vol_ma > 0 else 1.0
    vol_tag = ""
    if vol_ratio <= 1.0:
        v_vol = 0
        vol_tag = " (Faible)"
    elif c_now > o_now:
        v_vol = 1
    elif c_now < o_now:
        v_vol = -1
    elif c_now > c_prev:
        v_vol = 1
    elif c_now < c_prev:
        v_vol = -1
    else:
        v_vol = 0

    # 8. Pivot Points
    pivot_p = (htf_bar["high"] + htf_bar["low"] + htf_bar["close"]) / 3.0
    v_pivot = 1 if c_now > pivot_p else (-1 if c_now < pivot_p else 0)

    digits = get_digits(symbol)
    zone_tfs = "30s" if tf == "30s" else ("1m, 3m" if tf in ("1m", "3m") else tf)
    zone_label = f"Zone {cfg['zone']} ({zone_tfs})"

    indicators = [
        {
            "name": f"EMA ({cfg['ema_short']}/{cfg['ema_long']})",
            "vote": v_ema,
            "summary": f"{ema_s:.{digits}f} vs {ema_l:.{digits}f}",
        },
        {
            "name": f"Bollinger ({cfg['bb_period']}, {cfg['bb_std']})",
            "vote": v_bb,
            "summary": f"M={bb_mid:.{digits}f} [{bb_lower:.{digits}f}-{bb_upper:.{digits}f}]{bb_tag}",
        },
        {
            "name": f"RSI ({cfg['rsi_period']}) [{cfg['rsi_ob']}/{cfg['rsi_os']}]",
            "vote": v_rsi,
            "summary": f"{rsi_val:.1f}{rsi_tag}",
        },
        {
            "name": f"MACD ({cfg['macd_fast']}/{cfg['macd_slow']}/{cfg['macd_signal']})",
            "vote": v_macd,
            "summary": f"Hist={'+' if macd_hist >= 0 else ''}{macd_hist:.{digits + 1}f}",
        },
        {
            "name": f"Stochastique ({cfg['stoch_k']}/{cfg['stoch_smooth']}/{cfg['stoch_d']})",
            "vote": v_stoch,
            "summary": f"%K={k_val:.1f} / %D={d_val:.1f}",
        },
        {
            "name": f"ATR ({cfg['atr_period']})",
            "vote": v_atr,
            "summary": f"{atr_val:.{digits}f} ({atr_ratio:.2f}x){atr_tag}",
        },
        {
            "name": f"Tick Volume (MA {cfg['vol_ma']})",
            "vote": v_vol,
            "summary": f"Ratio={vol_ratio:.2f}x{vol_tag}",
        },
        {
            "name": f"Pivot Points ({cfg['pivot_htf']})",
            "vote": v_pivot,
            "summary": f"P={pivot_p:.{digits}f}",
        },
    ]

    votes = [v_ema, v_bb, v_rsi, v_macd, v_stoch, v_atr, v_vol, v_pivot]
    buy_count = sum(1 for v in votes if v == 1)
    sell_count = sum(1 for v in votes if v == -1)
    neutral_count = 8 - buy_count - sell_count
    confluence = max(buy_count, sell_count)

    if buy_count >= 5 and buy_count > sell_count:
        direction = "ACHAT"
        buy_pct = round((buy_count / 8) * 100)
        signal_label = f"{buy_pct}% ACHAT"
    elif sell_count >= 5 and sell_count > buy_count:
        direction = "VENTE"
        sell_pct = round((sell_count / 8) * 100)
        signal_label = f"{sell_pct}% VENTE"
    else:
        direction = "NEUTRE"
        signal_label = "NEUTRE"

    price_series: List[Dict[str, Any]] = []
    if tf == "30s":
        tail_df = df.tail(40)
        for _, bar in tail_df.iterrows():
            if "dt" in bar and hasattr(bar["dt"], "strftime"):
                t_str = bar["dt"].strftime("%H:%M:%S")
            elif "time" in bar:
                t_str = datetime.fromtimestamp(int(bar["time"])).strftime("%H:%M:%S")
            else:
                t_str = ""
            price_series.append({"time": t_str, "price": float(bar["close"])})

    core5_votes = [v_ema, v_bb, v_rsi, v_macd, v_stoch]
    if all(v == 1 for v in core5_votes):
        core5_alignment = "ACHAT"
    elif all(v == -1 for v in core5_votes):
        core5_alignment = "VENTE"
    else:
        core5_alignment = None

    return {
        "pair": symbol,
        "timeframe": tf,
        "direction": direction,
        "signal_label": signal_label,
        "confluence": confluence,
        "confluence_label": f"{confluence}/8",
        "core5_alignment": core5_alignment,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "neutral_count": neutral_count,
        "atr_value": atr_val,
        "atr_ratio": atr_ratio,
        "vol_ratio": vol_ratio,
        "price": c_now,
        "zone_label": zone_label,
        "pivot_htf": cfg["pivot_htf"],
        "indicators": indicators,
        "price_series": price_series,
        "pine_forecast": compute_pine_forecast(df),
    }


def collect_swing_candidates(df: Optional[pd.DataFrame], tf_label: str, lookback: int) -> List[Dict[str, Any]]:
    if df is None or len(df) < 7:
        return []
    sub = df.tail(lookback).reset_index(drop=True)
    highs = sub["high"].astype(float).tolist()
    lows = sub["low"].astype(float).tolist()
    n = len(sub)
    w = 2
    out: List[Dict[str, Any]] = []

    for i in range(w, n - 1 - w):
        h = highs[i]
        l = lows[i]
        is_sh = all(highs[k] < h for k in range(i - w, i + w + 1) if k != i)
        is_sl = all(lows[k] > l for k in range(i - w, i + w + 1) if k != i)
        if is_sh:
            out.append({"price": h, "source": f"Sommet {tf_label}"})
        if is_sl:
            out.append({"price": l, "source": f"Creux {tf_label}"})

    if n > 1:
        out.append({"price": max(highs[:-1]), "source": f"Haut {tf_label}"})
        out.append({"price": min(lows[:-1]), "source": f"Bas {tf_label}"})
    return out


def compute_support_resistance(
    symbol: str,
    current_price: float,
    df_1m: Optional[pd.DataFrame],
    df_5m: Optional[pd.DataFrame],
    h1_bar: Optional[Dict[str, float]],
    h4_bar: Optional[Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    if current_price <= 0:
        return None
    pip = get_pip_size(symbol)
    candidates: List[Dict[str, Any]] = []
    candidates.extend(collect_swing_candidates(df_1m, "1m", 80))
    candidates.extend(collect_swing_candidates(df_5m, "5m", 60))

    for label, bar in (("H1", h1_bar), ("H4", h4_bar)):
        if bar is None:
            continue
        p = (bar["high"] + bar["low"] + bar["close"]) / 3.0
        r1 = 2.0 * p - bar["low"]
        s1 = 2.0 * p - bar["high"]
        r2 = p + (bar["high"] - bar["low"])
        s2 = p - (bar["high"] - bar["low"])
        candidates.extend([
            {"price": p, "source": f"Pivot {label}"},
            {"price": r1, "source": f"R1 {label}"},
            {"price": r2, "source": f"R2 {label}"},
            {"price": s1, "source": f"S1 {label}"},
            {"price": s2, "source": f"S2 {label}"},
        ])

    best_support: Optional[Dict[str, Any]] = None
    best_resistance: Optional[Dict[str, Any]] = None
    min_gap = pip * 0.05

    for c in candidates:
        px = float(c["price"])
        if px <= 0:
            continue
        if px < current_price - min_gap:
            if best_support is None or px > best_support["price"]:
                best_support = {"price": px, "source": c["source"]}
        elif px > current_price + min_gap:
            if best_resistance is None or px < best_resistance["price"]:
                best_resistance = {"price": px, "source": c["source"]}

    if df_1m is not None and len(df_1m) >= 12:
        atr_1m, _ = compute_atr_stats(df_1m, 10)
    else:
        atr_1m = 2.0 * pip

    threshold_price = max(2.0 * pip, 0.75 * atr_1m)
    threshold_pips = round(threshold_price / pip, 1)

    support_obj = None
    if best_support is not None:
        support_obj = {
            "price": best_support["price"],
            "distancePips": round((current_price - best_support["price"]) / pip, 1),
            "source": best_support["source"],
        }

    resistance_obj = None
    if best_resistance is not None:
        resistance_obj = {
            "price": best_resistance["price"],
            "distancePips": round((best_resistance["price"] - current_price) / pip, 1),
            "source": best_resistance["source"],
        }

    near_support = best_support is not None and (current_price - best_support["price"]) <= threshold_price
    near_resistance = best_resistance is not None and (best_resistance["price"] - current_price) <= threshold_price

    if near_support and near_resistance:
        proximity_alert = "NEAR_BOTH"
    elif near_resistance:
        proximity_alert = "NEAR_RESISTANCE"
    elif near_support:
        proximity_alert = "NEAR_SUPPORT"
    else:
        proximity_alert = "CLEAR"

    return {
        "support": support_obj,
        "resistance": resistance_obj,
        "proximityAlert": proximity_alert,
        "thresholdPips": threshold_pips,
    }


# ==============================================================================
# PLANIFICATION HORLOGE RÉELLE PAR TIMEFRAME
# ==============================================================================
def get_next_target_epoch_sec(tf: str, after_epoch_sec: int) -> int:
    base = datetime.fromtimestamp(after_epoch_sec).replace(second=0, microsecond=0)
    if tf == "30s":
        t25 = int((base + timedelta(seconds=25)).timestamp())
        if t25 > after_epoch_sec:
            return t25
        t55 = int((base + timedelta(seconds=55)).timestamp())
        if t55 > after_epoch_sec:
            return t55
        return int((base + timedelta(minutes=1, seconds=25)).timestamp())

    if tf in ("1m", "3m", "5m"):
        t55 = int((base + timedelta(seconds=55)).timestamp())
        if t55 > after_epoch_sec:
            return t55
        return int((base + timedelta(minutes=1, seconds=55)).timestamp())

    if tf == "10m":
        for offset in range(0, 3):
            cand = base + timedelta(minutes=offset, seconds=55)
            cand_sec = int(cand.timestamp())
            if cand.minute % 2 == 1 and cand_sec > after_epoch_sec:
                return cand_sec

    # 15m : :55 des minutes 02, 05, 08, 11, 14, 17, 20... (minute % 3 == 2)
    for offset in range(0, 4):
        cand = base + timedelta(minutes=offset, seconds=55)
        cand_sec = int(cand.timestamp())
        if cand.minute % 3 == 2 and cand_sec > after_epoch_sec:
            return cand_sec

    return after_epoch_sec + 180


# ==============================================================================
# GÉNÉRATION HTML AUTONOME (dashboard/forex_dashboard.html)
# ==============================================================================
def render_dashboard_html(
    results: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
    mt5_ok: bool,
    updated_at: str,
    sr_by_pair: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
    spread_by_pair: Optional[Dict[str, Optional[float]]] = None,
    active_pairs: Optional[List[str]] = None,
) -> str:
    pairs_to_render = list(active_pairs) if active_pairs else list(ACTIVE_PAIRS)
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for pair in pairs_to_render:
        rows = []
        for tf in TIMEFRAMES:
            cfg = ZONES[tf]
            zone_tfs = "30s" if tf == "30s" else ("1m, 3m" if tf in ("1m", "3m") else tf)
            default_zone_label = f"Zone {cfg['zone']} ({zone_tfs})"
            row = results.get(pair, {}).get(tf)
            if not mt5_ok or row is None:
                rows.append({
                    "pair": pair,
                    "timeframe": tf,
                    "direction": "WAIT",
                    "signal_label": "WAIT",
                    "confluence_label": "WAIT",
                    "core5_alignment": None,
                    "buy_count": 0,
                    "sell_count": 0,
                    "neutral_count": 0,
                    "atr_value": 0.0,
                    "atr_ratio": 1.0,
                    "vol_ratio": 1.0,
                    "price": None,
                    "zone_label": default_zone_label,
                    "pivot_htf": cfg["pivot_htf"],
                    "indicators": [],
                    "pine_forecast": None,
                })
            else:
                rows.append({
                    "pair": pair,
                    "timeframe": tf,
                    "direction": row["direction"],
                    "signal_label": row["signal_label"],
                    "confluence_label": row["confluence_label"],
                    "core5_alignment": row.get("core5_alignment"),
                    "buy_count": row["buy_count"],
                    "sell_count": row["sell_count"],
                    "neutral_count": row.get("neutral_count", max(0, 8 - row["buy_count"] - row["sell_count"])),
                    "atr_value": row.get("atr_value", 0.0),
                    "atr_ratio": row.get("atr_ratio", 1.0),
                    "vol_ratio": row.get("vol_ratio", 1.0),
                    "price": row.get("price"),
                    "zone_label": row.get("zone_label", default_zone_label),
                    "pivot_htf": row.get("pivot_htf", cfg["pivot_htf"]),
                    "indicators": row.get("indicators", []),
                    "pine_forecast": row.get("pine_forecast"),
                })
        payload[pair] = rows

    price_payload: Dict[str, List[Dict[str, Any]]] = {}
    for pair in pairs_to_render:
        row_30s = results.get(pair, {}).get("30s")
        if mt5_ok and row_30s and isinstance(row_30s.get("price_series"), list):
            price_payload[pair] = row_30s["price_series"]
        else:
            price_payload[pair] = []

    sr_payload: Dict[str, Optional[Dict[str, Any]]] = {}
    spread_payload: Dict[str, Optional[float]] = {}
    for pair in pairs_to_render:
        sr_payload[pair] = (sr_by_pair or {}).get(pair) if mt5_ok else None
        raw_sp = (spread_by_pair or {}).get(pair) if mt5_ok else None
        spread_payload[pair] = round(float(raw_sp), 1) if raw_sp is not None else None

    data_json = json.dumps(payload, ensure_ascii=False)
    price_json = json.dumps(price_payload, ensure_ascii=False)
    sr_json = json.dumps(sr_payload, ensure_ascii=False)
    spread_json = json.dumps(spread_payload, ensure_ascii=False)
    updated_json = json.dumps(updated_at, ensure_ascii=False)
    pairs_json = json.dumps(pairs_to_render, ensure_ascii=False)
    suggested_json = json.dumps(SUGGESTED_PAIRS, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Forex Agent Dashboard</title>
  <style>
    :root {{
      --font-sans: "Plus Jakarta Sans", system-ui, -apple-system, sans-serif;
      --font-mono: "JetBrains Mono", Consolas, ui-monospace, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: #07090d;
      color: #f1f5f9;
      font-family: var(--font-sans);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }}
    .font-mono {{ font-family: var(--font-mono); }}
    .tabular-nums {{ font-variant-numeric: tabular-nums; }}

    /* A. En-tête */
    .header {{
      border-bottom: 1px solid #1e2633;
      background-color: #0a0d13;
    }}
    .header-inner {{
      max-width: 1152px;
      margin: 0 auto;
      padding: 16px 20px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .header-brand {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 10px;
      min-width: 0;
    }}
    .header-title {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #ffffff;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .header-winrate {{
      display: inline-flex;
      align-items: baseline;
      gap: 6px;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .header-winrate-label {{
      font-size: 13px;
      font-weight: 500;
      color: #94a3b8;
    }}
    .header-winrate-val {{
      font-family: var(--font-mono);
      font-size: 13px;
      color: #94a3b8;
      font-variant-numeric: tabular-nums;
    }}
    .header-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }}
    .sound-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background-color: #0f131a;
      color: #e2e8f0;
      border: 1px solid #1e2633;
      padding: 8px 14px;
      border-radius: 8px;
      font-family: var(--font-sans);
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      white-space: nowrap;
      flex-shrink: 0;
      transition: border-color 0.15s ease, color 0.15s ease;
    }}
    .sound-btn:hover {{
      border-color: #475569;
      color: #ffffff;
    }}
    .refresh-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background-color: #059669;
      color: #ffffff;
      border: none;
      padding: 8px 16px;
      border-radius: 8px;
      font-family: var(--font-sans);
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      white-space: nowrap;
      flex-shrink: 0;
      transition: background-color 0.15s ease;
    }}
    .refresh-btn:hover {{ background-color: #10b981; }}

    /* Conteneur principal */
    .main {{
      max-width: 1152px;
      margin: 0 auto;
      padding: 28px 20px;
    }}

    /* B. Barre de sélection des 4 paires */
    .pairs-row {{
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .pairs-bar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }}
    .pairs-right {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }}
    .usd-strength {{
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .live-clock {{
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 700;
      color: #e2e8f0;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .pair-item {{
      display: inline-flex;
      align-items: center;
      border-radius: 12px;
      border: 1px solid #1e2633;
      background-color: #0f131a;
      transition: background-color 0.15s ease, border-color 0.15s ease;
    }}
    .pair-item:hover {{
      border-color: #475569;
    }}
    .pair-item.active {{
      border-color: #cbd5e1;
      background-color: #141b26;
    }}
    .pair-label {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 14px 12px 16px;
      color: #cbd5e1;
      font-family: var(--font-mono);
      font-weight: 700;
      font-size: 15px;
      cursor: pointer;
      user-select: none;
    }}
    .pair-name-buy {{ color: #34d399; }}
    .pair-name-sell {{ color: #f87171; }}
    .pair-name-neutral {{ color: #ffffff; }}
    .pair-label input {{
      width: 16px;
      height: 16px;
      accent-color: #e2e8f0;
      cursor: pointer;
    }}
    .pair-setup-buy {{
      font-family: var(--font-sans);
      font-size: 12px;
      font-weight: 600;
      color: #34d399;
      white-space: nowrap;
    }}
    .pair-setup-sell {{
      font-family: var(--font-sans);
      font-size: 12px;
      font-weight: 600;
      color: #f87171;
      white-space: nowrap;
    }}
    .pair-remove-btn {{
      margin-right: 8px;
      width: 24px;
      height: 24px;
      border-radius: 6px;
      border: none;
      background: transparent;
      color: #94a3b8;
      font-size: 16px;
      line-height: 1;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: background-color 0.15s ease, color 0.15s ease;
    }}
    .pair-remove-btn:hover {{
      background-color: #1e2633;
      color: #f87171;
    }}
    .pair-add-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 12px 16px;
      border-radius: 12px;
      border: 1px dashed #2b3648;
      background-color: #0f131a;
      color: #cbd5e1;
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      flex-shrink: 0;
      transition: border-color 0.15s ease, color 0.15s ease;
    }}
    .pair-add-btn:hover {{
      border-color: #94a3b8;
      color: #ffffff;
    }}
    .pair-add-panel {{
      margin-bottom: 20px;
      border-radius: 12px;
      border: 1px solid #1e2633;
      background-color: #0f131a;
      padding: 14px 16px;
    }}
    .pair-add-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .pair-suggest-group {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }}
    .pair-suggest-title {{
      font-size: 12px;
      font-weight: 500;
      color: #94a3b8;
      margin-right: 4px;
    }}
    .pair-suggest-btn {{
      border-radius: 8px;
      border: 1px solid #1e2633;
      background-color: #090c11;
      color: #e2e8f0;
      padding: 6px 10px;
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: border-color 0.15s ease, color 0.15s ease;
    }}
    .pair-suggest-btn:hover {{
      border-color: #10b981;
      color: #6ee7b7;
    }}
    .pair-form {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pair-input {{
      width: 185px;
      border-radius: 8px;
      border: 1px solid #1e2633;
      background-color: #07090d;
      padding: 6px 10px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #f1f5f9;
      outline: none;
    }}
    .pair-input:focus {{
      border-color: #10b981;
    }}
    .pair-submit-btn {{
      border-radius: 8px;
      border: none;
      background-color: #059669;
      color: #ffffff;
      padding: 6px 12px;
      font-family: var(--font-sans);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }}
    .pair-submit-btn:hover {{ background-color: #10b981; }}
    .pair-close-btn {{
      border-radius: 8px;
      border: 1px solid #1e2633;
      background-color: #090c11;
      color: #cbd5e1;
      padding: 6px 10px;
      font-family: var(--font-sans);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
    }}
    .pair-error-msg {{
      margin-top: 8px;
      font-size: 12px;
      font-weight: 500;
      color: #fcd34d;
    }}

    /* Bandeau compact Setup 1m/3m, État du marché & Support/Résistance */
    .status-banner {{
      margin-bottom: 20px;
      background-color: #0f131a;
      border: 1px solid #1e2633;
      border-radius: 12px;
      padding: 14px 20px;
      font-size: 14px;
    }}
    .banner-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .banner-sr-row {{
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid #1a2230;
    }}
    .banner-group {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }}
    .banner-label {{
      color: #94a3b8;
      font-weight: 500;
    }}
    .banner-sep {{
      color: #475569;
    }}
    .tone-buy {{
      color: #34d399;
      font-weight: 700;
    }}
    .tone-sell {{
      color: #f87171;
      font-weight: 700;
    }}
    .tone-warn {{
      color: #fcd34d;
      font-weight: 600;
    }}
    .tone-muted {{
      color: #cbd5e1;
      font-weight: 500;
    }}
    .tone-subtle {{
      color: #94a3b8;
      font-weight: 500;
    }}
    .banner-ratios {{
      font-family: var(--font-mono);
      font-size: 12px;
      color: #94a3b8;
      font-variant-numeric: tabular-nums;
    }}
    .sr-val {{
      font-family: var(--font-mono);
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }}
    .sr-buy {{ color: #34d399; }}
    .sr-sell {{ color: #f87171; }}
    .chart-header-right {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 12px;
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }}

    /* C. Tableau 4 colonnes et 6 lignes */
    .table-wrap {{
      background-color: #0f131a;
      border: 1px solid #1e2633;
      border-radius: 16px;
      overflow: hidden;
    }}
    .table-scroll {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }}
    thead tr {{
      background-color: #0a0d13;
      border-bottom: 1px solid #1e2633;
    }}
    th {{
      padding: 16px 24px;
      font-size: 13px;
      font-weight: 600;
      color: #94a3b8;
    }}
    tbody tr {{
      border-bottom: 1px solid #171e2b;
      cursor: pointer;
      transition: background-color 0.15s ease;
    }}
    tbody tr:last-child {{ border-bottom: none; }}
    tbody tr:hover {{ background-color: #121822; }}
    tbody tr.selected {{ background-color: #141b26; }}
    td {{
      padding: 14px 24px;
      vertical-align: middle;
      font-variant-numeric: tabular-nums;
    }}
    .tf-cell {{
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 700;
      color: #f1f5f9;
    }}
    .sig-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 200px;
      padding: 10px 20px;
      border-radius: 12px;
      font-family: var(--font-mono);
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -0.02em;
      text-align: center;
    }}
    .sig-ACHAT {{ background-color: #059669; color: #ffffff; }}
    .sig-VENTE {{ background-color: #dc2626; color: #ffffff; }}
    .sig-NEUTRE {{ background-color: #334155; color: #f1f5f9; }}
    .sig-WAIT {{ background-color: #1e293b; color: #fbbf24; }}
    .conf-cell {{
      font-family: var(--font-mono);
      font-size: 24px;
      font-weight: 700;
      color: #ffffff;
    }}
    .conf-wrap {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
    }}
    .core5-dot {{
      display: inline-block;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
    }}
    .core5-dot-buy {{
      background-color: #10b981;
      box-shadow: 0 0 8px rgba(16, 185, 129, 0.75);
    }}
    .core5-dot-sell {{
      background-color: #ef4444;
      box-shadow: 0 0 8px rgba(239, 68, 68, 0.75);
    }}
    .maj-cell {{
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 700;
      color: #cbd5e1;
    }}

    /* D. Panneau Détail des 8 indicateurs */
    .details-panel {{
      margin-top: 24px;
      border-radius: 12px;
      border: 1px solid #1e2633;
      background-color: #0f131a;
      padding: 20px;
    }}
    .details-header {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      border-bottom: 1px solid #1e2633;
      padding-bottom: 12px;
      margin-bottom: 16px;
    }}
    .details-title-wrap {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 12px;
    }}
    .details-title {{
      font-size: 16px;
      font-weight: 700;
      color: #f1f5f9;
    }}
    .details-zone {{
      font-size: 12px;
      font-weight: 500;
      color: #94a3b8;
    }}
    .details-counts {{
      font-family: var(--font-mono);
      font-size: 12px;
      color: #cbd5e1;
      font-variant-numeric: tabular-nums;
    }}
    .details-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    @media (min-width: 1024px) {{
      .details-grid {{
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }}
    }}
    .ind-card {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-radius: 8px;
      border: 1px solid #1a2230;
      background-color: #090c11;
      padding: 10px 14px;
    }}
    .ind-info {{ min-width: 0; }}
    .ind-name {{
      font-size: 12px;
      font-weight: 600;
      color: #e2e8f0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .ind-summary {{
      font-family: var(--font-mono);
      font-size: 12px;
      color: #94a3b8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-variant-numeric: tabular-nums;
    }}
    .ind-badge {{
      flex-shrink: 0;
      border-radius: 4px;
      padding: 4px 8px;
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .ind-badge-buy {{
      background-color: #04785715;
      color: #34d399;
    }}
    .ind-badge-sell {{
      background-color: #dc262615;
      color: #f87171;
    }}
    .ind-badge-neutral {{
      background-color: #1e293b;
      color: #cbd5e1;
    }}

    /* D-bis. Panneau Graphique Prix en temps réel */
    .chart-panel {{
      margin-top: 24px;
      border-radius: 12px;
      border: 1px solid #1e2633;
      background-color: #0f131a;
      padding: 20px;
    }}
    .chart-price-badge {{
      font-family: var(--font-mono);
      font-size: 14px;
      font-weight: 700;
      color: #f1f5f9;
      font-variant-numeric: tabular-nums;
    }}
    .chart-container {{
      position: relative;
      width: 100%;
      height: 224px;
      background: transparent;
    }}
    .chart-svg {{
      width: 100%;
      height: 100%;
      display: block;
      overflow: visible;
    }}
    .chart-tooltip {{
      position: absolute;
      pointer-events: none;
      display: none;
      background-color: #090c11;
      border: 1px solid #1e2633;
      border-radius: 8px;
      padding: 8px 10px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #f1f5f9;
      white-space: nowrap;
      z-index: 10;
    }}
    .chart-tooltip-time {{
      color: #94a3b8;
      margin-bottom: 2px;
      font-size: 11px;
    }}

    /* D-ter. Mini historique des 10 derniers setups */
    .history-panel {{
      margin-top: 24px;
      border-radius: 12px;
      border: 1px solid #1e2633;
      background-color: #0f131a;
      padding: 20px;
    }}
    .history-clear-btn {{
      border-radius: 8px;
      border: 1px solid #1e2633;
      background-color: #090c11;
      color: #cbd5e1;
      padding: 6px 12px;
      font-family: var(--font-sans);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: border-color 0.15s ease, color 0.15s ease;
    }}
    .history-clear-btn:hover {{
      border-color: #475569;
      color: #ffffff;
    }}
    .history-empty {{
      font-size: 13px;
      color: #94a3b8;
    }}
    .history-table th {{
      padding: 8px 16px 8px 0;
      font-size: 12px;
      color: #94a3b8;
    }}
    .history-table td {{
      padding: 10px 16px 10px 0;
      font-size: 13px;
      white-space: nowrap;
    }}
    .history-dir-buy {{
      font-family: var(--font-mono);
      font-weight: 700;
      color: #34d399;
    }}
    .history-dir-sell {{
      font-family: var(--font-mono);
      font-weight: 700;
      color: #f87171;
    }}

    /* E. Pied de page */
    .footer {{
      margin-top: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: #94a3b8;
      font-size: 13px;
    }}
    .footer-time {{
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }}
  </style>
</head>
<body>
  <header class="header">
    <div class="header-inner">
      <div class="header-brand">
        <h1 class="header-title">Forex Agent Dashboard</h1>
        <span class="banner-sep" aria-hidden="true">·</span>
        <div class="header-winrate" title="Pourcentage de succès des 10 derniers setups résolus (après 3 bougies)">
          <span class="header-winrate-label">Winrate Session</span>
          <span class="header-winrate-val" id="headerWinrateVal">—</span>
        </div>
      </div>
      <div class="header-actions">
        <button type="button" class="sound-btn" id="soundBtn" aria-pressed="true"></button>
        <button type="button" class="refresh-btn" id="refreshBtn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
            <path d="M16 16h5v5" />
          </svg>
          Actualiser
        </button>
      </div>
    </div>
  </header>

  <main class="main">
    <div class="pairs-row">
      <div class="pairs-bar" id="pairSelector" role="radiogroup" aria-label="Sélection de la paire Forex"></div>
      <div class="pairs-right">
        <span class="usd-strength" id="usdStrength"></span>
        <span class="banner-sep" id="usdStrengthSep" style="display:none">·</span>
        <div class="live-clock" id="liveClock" aria-label="Heure actuelle"></div>
      </div>
    </div>

    <div class="pair-add-panel" id="pairAddPanel" style="display:none"></div>

    <div class="status-banner" id="statusBanner"></div>

    <div class="table-wrap">
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Timeframe</th>
              <th>Signal</th>
              <th>Confluence</th>
              <th>Prochaine MAJ</th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
    </div>

    <section class="details-panel" id="detailsPanel"></section>

    <section class="chart-panel" id="chartPanel"></section>

    <section class="history-panel" id="historyPanel"></section>

    <footer class="footer">
      <span class="footer-time" id="footerTime"></span>
      <span id="footerPair"></span>
    </footer>
  </main>

  <script>
    const DATA = {data_json};
    const PRICE_DATA = {price_json};
    const SR_DATA = {sr_json};
    const SPREAD_DATA = {spread_json};
    const UPDATED_AT = {updated_json};
    const PAIRS = {pairs_json};
    const SUGGESTED_PAIRS = {suggested_json};
    const MAX_ACTIVE_PAIRS = {MAX_ACTIVE_PAIRS};
    const TIMEFRAMES = ["30s", "1m", "3m", "5m", "10m", "15m"];
    const STORAGE_PAIR = "forex_agent_selected_pair";
    const STORAGE_TF = "forex_agent_selected_tf";
    const STORAGE_SOUND = "forex_agent_sound_enabled";
    const STORAGE_HISTORY = "forex_agent_setup_history";
    const STORAGE_SIGS = "forex_agent_last_setup_sigs";
    const STORAGE_SCROLL_Y = "forex_agent_scroll_y";

    let selectedPair = localStorage.getItem(STORAGE_PAIR);
    if (!PAIRS.includes(selectedPair)) selectedPair = PAIRS[0] || "EURUSDm";
    let selectedTfDetail = localStorage.getItem(STORAGE_TF);
    if (!TIMEFRAMES.includes(selectedTfDetail)) selectedTfDetail = "1m";
    let soundEnabled = localStorage.getItem(STORAGE_SOUND) !== "0";
    let isAddPanelOpen = false;
    let pairActionError = "";
    let pairActionBusy = false;

    function getPipSize(pair) {{
      const u = String(pair || "").toUpperCase();
      if (u.indexOf("XAU") !== -1 || u.indexOf("GOLD") !== -1) return 0.1;
      if (u.indexOf("JPY") !== -1) return 0.01;
      return 0.0001;
    }}

    function getPairDigits(pair) {{
      const u = String(pair || "").toUpperCase();
      if (u.indexOf("XAU") !== -1 || u.indexOf("GOLD") !== -1) return 2;
      if (u.indexOf("JPY") !== -1) return 3;
      return 5;
    }}

    function normalizeSymbolInput(raw) {{
      const cleaned = String(raw || "").trim().replace(/\\s+/g, "");
      if (!cleaned) return "";
      if (/^[A-Za-z]{{6}}$/.test(cleaned)) return cleaned.toUpperCase() + "m";
      if (/^[A-Za-z]{{6}}[mM]$/.test(cleaned)) return cleaned.slice(0, 6).toUpperCase() + "m";
      return cleaned.slice(0, 16);
    }}

    let audioCtx = null;
    function getAudioCtx() {{
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return null;
      if (!audioCtx) audioCtx = new Ctor();
      if (audioCtx.state === "suspended") {{
        audioCtx.resume().catch(() => {{}});
      }}
      return audioCtx;
    }}

    function playSetupChime(direction) {{
      try {{
        const ctx = getAudioCtx();
        if (!ctx) return;
        const now = ctx.currentTime;
        const freqs = direction === "ACHAT" ? [660, 880] : [520, 390];
        freqs.forEach((freq, idx) => {{
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          const start = now + idx * 0.11;
          const stop = start + 0.13;
          osc.type = "sine";
          osc.frequency.setValueAtTime(freq, start);
          gain.gain.setValueAtTime(0.0001, start);
          gain.gain.exponentialRampToValueAtTime(0.08, start + 0.015);
          gain.gain.exponentialRampToValueAtTime(0.0001, stop);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(start);
          osc.stop(stop);
        }});
      }} catch (_e) {{}}
    }}

    function renderSoundButton() {{
      const btn = document.getElementById("soundBtn");
      btn.setAttribute("aria-pressed", soundEnabled ? "true" : "false");
      btn.title = soundEnabled ? "Couper l'alerte sonore" : "Activer l'alerte sonore";
      btn.innerHTML = soundEnabled
        ? "<svg width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='#34d399' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><polygon points='11 5 6 9 2 9 2 15 6 15 11 19 11 5'/><path d='M15.54 8.46a5 5 0 0 1 0 7.07'/><path d='M19.07 4.93a10 10 0 0 1 0 14.14'/></svg><span>Son activé</span>"
        : "<svg width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='#94a3b8' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><polygon points='11 5 6 9 2 9 2 15 6 15 11 19 11 5'/><line x1='22' y1='9' x2='16' y2='15'/><line x1='16' y1='9' x2='22' y2='15'/></svg><span>Son coupé</span>";
    }}

    document.getElementById("soundBtn").addEventListener("click", () => {{
      getAudioCtx();
      soundEnabled = !soundEnabled;
      localStorage.setItem(STORAGE_SOUND, soundEnabled ? "1" : "0");
      renderSoundButton();
    }});

    function reloadPreservingScroll() {{
      try {{
        sessionStorage.setItem(STORAGE_SCROLL_Y, String(window.scrollY || 0));
      }} catch (_e) {{}}
      window.location.reload();
    }}

    document.getElementById("refreshBtn").addEventListener("click", () => {{
      reloadPreservingScroll();
    }});

    function getNextTargetSec(tf, afterSec) {{
      const d = new Date(afterSec * 1000);
      const y = d.getFullYear(), mo = d.getMonth(), da = d.getDate(), h = d.getHours(), m = d.getMinutes();
      if (tf === "30s") {{
        const t25 = Math.floor(new Date(y, mo, da, h, m, 25, 0).getTime() / 1000);
        if (t25 > afterSec) return t25;
        const t55 = Math.floor(new Date(y, mo, da, h, m, 55, 0).getTime() / 1000);
        if (t55 > afterSec) return t55;
        return Math.floor(new Date(y, mo, da, h, m + 1, 25, 0).getTime() / 1000);
      }}
      if (tf === "1m" || tf === "3m" || tf === "5m") {{
        const t55 = Math.floor(new Date(y, mo, da, h, m, 55, 0).getTime() / 1000);
        if (t55 > afterSec) return t55;
        return Math.floor(new Date(y, mo, da, h, m + 1, 55, 0).getTime() / 1000);
      }}
      if (tf === "10m") {{
        for (let off = 0; off <= 2; off++) {{
          const c = new Date(y, mo, da, h, m + off, 55, 0);
          const cs = Math.floor(c.getTime() / 1000);
          if (c.getMinutes() % 2 === 1 && cs > afterSec) return cs;
        }}
      }}
      for (let off = 0; off <= 3; off++) {{
        const c = new Date(y, mo, da, h, m + off, 55, 0);
        const cs = Math.floor(c.getTime() / 1000);
        if (c.getMinutes() % 3 === 2 && cs > afterSec) return cs;
      }}
      return afterSec + 180;
    }}

    function fmtMmSs(sec) {{
      const s = Math.max(0, Math.floor(sec));
      return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }}

    function fmtClockHHMMSS(dateObj) {{
      return (
        String(dateObj.getHours()).padStart(2, "0") +
        ":" +
        String(dateObj.getMinutes()).padStart(2, "0") +
        ":" +
        String(dateObj.getSeconds()).padStart(2, "0")
      );
    }}

    function setSelectedTfDetail(tf) {{
      selectedTfDetail = tf;
      try {{
        localStorage.setItem(STORAGE_TF, tf);
      }} catch (_e) {{}}
      renderBanner();
      renderTable();
      renderDetails();
    }}

    function getForexSessionInfo(dateObj) {{
      const d = dateObj || new Date();
      const day = d.getUTCDay();
      const mins = d.getUTCHours() * 60 + d.getUTCMinutes();
      if (day === 6 || (day === 5 && mins >= 22 * 60) || (day === 0 && mins < 22 * 60)) {{
        return {{ label: "Marché fermé · Week-end", tone: "WARN" }};
      }}
      if (mins >= 21 * 60 + 55 && mins <= 23 * 60 + 5) {{
        return {{ label: "Rollover · Spread élevé", tone: "WARN" }};
      }}
      if (mins >= 12 * 60 && mins < 16 * 60) {{
        return {{ label: "Londres + New York · Liquidité optimale", tone: "GOOD" }};
      }}
      if (mins >= 7 * 60 && mins < 12 * 60) {{
        return {{ label: "Londres", tone: "NORMAL" }};
      }}
      if (mins >= 16 * 60 && mins < 21 * 60 + 55) {{
        return {{ label: "New York", tone: "NORMAL" }};
      }}
      return {{ label: "Asie", tone: "NORMAL" }};
    }}

    function getPineConsensus(pf) {{
      if (!pf || !pf.nextCandle || !pf.breakout || !pf.levelsStrength) {{
        return {{ label: "—", bias: "NEUTRE", bullCount: 0, bearCount: 0 }};
      }}
      const biases = [pf.nextCandle.bias, pf.breakout.bias, pf.levelsStrength.bias];
      const bullCount = biases.filter(b => b === "HAUSSE").length;
      const bearCount = biases.filter(b => b === "BAISSE").length;
      if (bullCount === 3) return {{ label: "3/3 Hausse", bias: "HAUSSE", bullCount, bearCount }};
      if (bearCount === 3) return {{ label: "3/3 Baisse", bias: "BAISSE", bullCount, bearCount }};
      if (bullCount === 2 && bearCount <= 1) return {{ label: "2/3 Hausse", bias: "HAUSSE", bullCount, bearCount }};
      if (bearCount === 2 && bullCount <= 1) return {{ label: "2/3 Baisse", bias: "BAISSE", bullCount, bearCount }};
      return {{ label: "Partagé", bias: "NEUTRE", bullCount, bearCount }};
    }}

    function computeUsdStrength(dataMap) {{
      if (!dataMap) return null;
      let score = 0;
      let validPairs = 0;
      PAIRS.forEach(p => {{
        const upper = String(p || "").toUpperCase();
        if (upper.indexOf("XAU") !== -1 || upper.indexOf("GOLD") !== -1) return;
        const usdAtStart = upper.indexOf("USD") === 0;
        const usdAsQuote = upper.slice(3, 6) === "USD";
        if (!usdAtStart && !usdAsQuote) return;

        const rows = (dataMap[p] || []).filter(r => r && r.direction !== "WAIT");
        if (rows.length === 0) return;
        const r1m = rows.find(r => r.timeframe === "1m");
        const r5m = rows.find(r => r.timeframe === "5m");
        const sample = [r1m, r5m].filter(Boolean);
        const refs = sample.length > 0 ? sample : [rows[0]];
        const avgNet = refs.reduce((acc, r) => acc + ((r.buy_count || 0) - (r.sell_count || 0)), 0) / refs.length;
        const pairBias = avgNet >= 1.5 ? 1 : (avgNet <= -1.5 ? -1 : 0);
        const usdDelta = usdAtStart ? pairBias : -pairBias;
        score += usdDelta;
        validPairs += 1;
      }});
      if (validPairs === 0) return null;
      const threshold = validPairs >= 4 ? 2 : 1;
      if (score >= threshold) return {{ score, maxScore: validPairs, label: "USD Fort", bias: "HAUSSE" }};
      if (score <= -threshold) return {{ score, maxScore: validPairs, label: "USD Faible", bias: "BAISSE" }};
      return {{ score, maxScore: validPairs, label: "USD Neutre", bias: "NEUTRE" }};
    }}

    function computeRiskEstimate(pair, atrVal, sr, dirHint) {{
      if (typeof atrVal !== "number" || !Number.isFinite(atrVal) || atrVal <= 0) return null;
      const pip = getPipSize(pair);
      const slPips = Number(((1.5 * atrVal) / pip).toFixed(1));
      if (slPips <= 0) return null;
      let obstaclePips = null;
      if (dirHint === "ACHAT" && sr && sr.resistance) {{
        obstaclePips = sr.resistance.distancePips;
      }} else if (dirHint === "VENTE" && sr && sr.support) {{
        obstaclePips = sr.support.distancePips;
      }} else if (sr && sr.support && sr.resistance) {{
        obstaclePips = Math.min(sr.support.distancePips, sr.resistance.distancePips);
      }} else if (sr && sr.resistance) {{
        obstaclePips = sr.resistance.distancePips;
      }} else if (sr && sr.support) {{
        obstaclePips = sr.support.distancePips;
      }}
      const rrRatio = (obstaclePips !== null && Number.isFinite(obstaclePips) && obstaclePips > 0)
        ? Number((obstaclePips / slPips).toFixed(1))
        : null;
      return {{ slPips, rrRatio }};
    }}

    function renderUsdStrength() {{
      const el = document.getElementById("usdStrength");
      const sep = document.getElementById("usdStrengthSep");
      if (!el || !sep) return;
      const usd = computeUsdStrength(DATA);
      if (!usd) {{
        el.textContent = "";
        sep.style.display = "none";
        return;
      }}
      const signed = usd.score > 0 ? "+" + usd.score : String(usd.score);
      el.textContent = usd.label + " (" + signed + "/" + usd.maxScore + ")";
      el.style.color = usd.bias === "HAUSSE" ? "#34d399" : (usd.bias === "BAISSE" ? "#f87171" : "#94a3b8");
      el.title = "Force relative du Dollar US calculée sur les paires USD actives (1m/5m)";
      sep.style.display = "inline";
    }}

    function evaluatePairSetup(rows) {{
      if (!rows || rows.length === 0 || rows.every(r => r.direction === "WAIT")) {{
        return {{
          status: "WAITING",
          direction: null,
          triggerTf: null,
          triggerPrice: null,
          setupText: "En attente des données MT5",
          atrRatio: 1.0,
          volRatio: 1.0,
          isMarketActive: true,
        }};
      }}

      const byTf = {{}};
      rows.forEach(r => {{ byTf[r.timeframe] = r; }});
      const r1m = byTf["1m"];
      const r3m = byTf["3m"];
      const htfRows = [byTf["5m"], byTf["10m"], byTf["15m"]].filter(Boolean);
      const htfBuys = htfRows.filter(r => r.direction === "ACHAT").length;
      const htfSells = htfRows.filter(r => r.direction === "VENTE").length;
      const htfTrend = (htfBuys >= 2 && htfSells === 0) ? "ACHAT" : ((htfSells >= 2 && htfBuys === 0) ? "VENTE" : null);

      const marketRef = r1m || r3m || rows[0];
      const atrRatio = typeof marketRef.atr_ratio === "number" ? marketRef.atr_ratio : 1.0;
      const volRatio = typeof marketRef.vol_ratio === "number" ? marketRef.vol_ratio : 1.0;
      const isMarketActive = atrRatio >= 0.85;

      const entryRows = [r1m, r3m].filter(Boolean);
      const readyBuyRow = htfTrend === "ACHAT"
        ? entryRows.find(r => r.direction === "ACHAT" && r.core5_alignment === "ACHAT")
        : null;
      const readySellRow = htfTrend === "VENTE"
        ? entryRows.find(r => r.direction === "VENTE" && r.core5_alignment === "VENTE")
        : null;
      const isCounterTrend =
        (htfTrend === "ACHAT" && entryRows.some(r => r.direction === "VENTE")) ||
        (htfTrend === "VENTE" && entryRows.some(r => r.direction === "ACHAT"));

      if (readyBuyRow && isMarketActive) {{
        return {{
          status: "READY_BUY",
          direction: "ACHAT",
          triggerTf: readyBuyRow.timeframe,
          triggerPrice: typeof readyBuyRow.price === "number" ? readyBuyRow.price : null,
          setupText: "Prêt ACHAT (aligné 5m–15m)",
          atrRatio,
          volRatio,
          isMarketActive,
        }};
      }}
      if (readySellRow && isMarketActive) {{
        return {{
          status: "READY_SELL",
          direction: "VENTE",
          triggerTf: readySellRow.timeframe,
          triggerPrice: typeof readySellRow.price === "number" ? readySellRow.price : null,
          setupText: "Prêt VENTE (aligné 5m–15m)",
          atrRatio,
          volRatio,
          isMarketActive,
        }};
      }}
      if (readyBuyRow || readySellRow) {{
        return {{
          status: "CALM_BLOCKED",
          direction: null,
          triggerTf: null,
          triggerPrice: null,
          setupText: "Aligné " + htfTrend + ", mais marché trop calme",
          atrRatio,
          volRatio,
          isMarketActive,
        }};
      }}
      if (isCounterTrend) {{
        return {{
          status: "COUNTER_TREND",
          direction: null,
          triggerTf: null,
          triggerPrice: null,
          setupText: "Contre-tendance 5m–15m · Prudence",
          atrRatio,
          volRatio,
          isMarketActive,
        }};
      }}
      return {{
        status: "WAITING",
        direction: null,
        triggerTf: null,
        triggerPrice: null,
        setupText: "En attente d'alignement 1m/3m + 5m–15m",
        atrRatio,
        volRatio,
        isMarketActive,
      }};
    }}

    function selectPairAndRender(pair) {{
      selectedPair = pair;
      localStorage.setItem(STORAGE_PAIR, pair);
      renderPairs();
      renderBanner();
      renderTable();
      renderDetails();
      renderChart();
    }}

    function renderAddPairPanel() {{
      const panel = document.getElementById("pairAddPanel");
      if (!panel) return;
      if (!isAddPanelOpen) {{
        panel.style.display = "none";
        panel.innerHTML = "";
        return;
      }}
      panel.style.display = "block";
      panel.innerHTML = "";

      const row = document.createElement("div");
      row.className = "pair-add-row";

      const suggestGroup = document.createElement("div");
      suggestGroup.className = "pair-suggest-group";
      const title = document.createElement("span");
      title.className = "pair-suggest-title";
      title.textContent = "Paires suggérées (" + PAIRS.length + "/" + MAX_ACTIVE_PAIRS + ") :";
      suggestGroup.appendChild(title);

      SUGGESTED_PAIRS.filter(s => !PAIRS.includes(s)).forEach(sym => {{
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pair-suggest-btn";
        btn.textContent = "+ " + sym;
        btn.disabled = pairActionBusy;
        btn.addEventListener("click", () => managePair("add", sym));
        suggestGroup.appendChild(btn);
      }});

      const form = document.createElement("form");
      form.className = "pair-form";
      const inp = document.createElement("input");
      inp.type = "text";
      inp.className = "pair-input";
      inp.placeholder = "Ex: EURJPYm ou XAUUSDm";
      inp.setAttribute("aria-label", "Nom du symbole personnalisé");
      const subBtn = document.createElement("button");
      subBtn.type = "submit";
      subBtn.className = "pair-submit-btn";
      subBtn.disabled = pairActionBusy;
      subBtn.textContent = pairActionBusy ? "..." : "Valider";
      const clsBtn = document.createElement("button");
      clsBtn.type = "button";
      clsBtn.className = "pair-close-btn";
      clsBtn.textContent = "Fermer";
      clsBtn.addEventListener("click", () => {{
        isAddPanelOpen = false;
        pairActionError = "";
        renderAddPairPanel();
      }});
      form.addEventListener("submit", (e) => {{
        e.preventDefault();
        managePair("add", inp.value);
      }});
      form.append(inp, subBtn, clsBtn);
      row.append(suggestGroup, form);
      panel.appendChild(row);

      if (pairActionError) {{
        const errEl = document.createElement("p");
        errEl.className = "pair-error-msg";
        errEl.textContent = pairActionError;
        panel.appendChild(errEl);
      }}
    }}

    async function managePair(action, rawSymbol) {{
      if (pairActionBusy) return;
      const symbol = normalizeSymbolInput(rawSymbol);
      if (action === "add" && !symbol) {{
        pairActionError = "Veuillez saisir un symbole valide (ex: EURJPYm ou XAUUSDm).";
        renderAddPairPanel();
        return;
      }}
      if (window.location.protocol === "file:") {{
        pairActionError = "Lancez lancer_forex_agent.bat pour ajouter/supprimer des paires depuis le navigateur.";
        isAddPanelOpen = true;
        renderAddPairPanel();
        return;
      }}
      pairActionBusy = true;
      pairActionError = "";
      renderAddPairPanel();
      try {{
        const res = await fetch("/api/pairs", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ action, symbol }}),
        }});
        const data = await res.json();
        if (!res.ok || !data.ok) {{
          pairActionError = data.error || "Impossible de modifier la liste des paires.";
          isAddPanelOpen = true;
          pairActionBusy = false;
          renderAddPairPanel();
          return;
        }}
        if (action === "add") {{
          localStorage.setItem(STORAGE_PAIR, data.symbol || symbol);
        }} else if (action === "remove" && selectedPair === symbol && Array.isArray(data.pairs) && data.pairs.length > 0) {{
          localStorage.setItem(STORAGE_PAIR, data.pairs[0]);
        }}
        reloadPreservingScroll();
      }} catch (_err) {{
        pairActionError = "Serveur local python injoignable. Relancez lancer_forex_agent.bat.";
        isAddPanelOpen = true;
        pairActionBusy = false;
        renderAddPairPanel();
      }}
    }}

    function renderPairs() {{
      const wrap = document.getElementById("pairSelector");
      wrap.innerHTML = "";
      const usd = computeUsdStrength(DATA);
      const nameCls = usd && usd.bias === "HAUSSE"
        ? "pair-name-buy"
        : (usd && usd.bias === "BAISSE" ? "pair-name-sell" : "pair-name-neutral");
      PAIRS.forEach(p => {{
        const setup = evaluatePairSetup(DATA[p] || []);
        const item = document.createElement("div");
        item.className = "pair-item" + (p === selectedPair ? " active" : "");

        const lbl = document.createElement("label");
        lbl.className = "pair-label";
        const inp = document.createElement("input");
        inp.type = "radio";
        inp.name = "pair";
        inp.value = p;
        inp.checked = (p === selectedPair);
        inp.addEventListener("change", () => selectPairAndRender(p));
        const nameEl = document.createElement("span");
        nameEl.className = nameCls;
        nameEl.textContent = p;
        lbl.appendChild(inp);
        lbl.appendChild(nameEl);
        if (setup.status === "READY_BUY" || setup.status === "READY_SELL") {{
          const sep = document.createElement("span");
          sep.className = "banner-sep";
          sep.textContent = "·";
          const st = document.createElement("span");
          st.className = setup.status === "READY_BUY" ? "pair-setup-buy" : "pair-setup-sell";
          st.textContent = setup.status === "READY_BUY" ? "Prêt ACHAT" : "Prêt VENTE";
          lbl.appendChild(sep);
          lbl.appendChild(st);
        }}
        item.appendChild(lbl);

        if (PAIRS.length > 1) {{
          const remBtn = document.createElement("button");
          remBtn.type = "button";
          remBtn.className = "pair-remove-btn";
          remBtn.title = "Supprimer " + p;
          remBtn.setAttribute("aria-label", "Supprimer " + p);
          remBtn.textContent = "×";
          remBtn.addEventListener("click", () => managePair("remove", p));
          item.appendChild(remBtn);
        }}

        wrap.appendChild(item);
      }});

      if (PAIRS.length < MAX_ACTIVE_PAIRS) {{
        const addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "pair-add-btn";
        addBtn.textContent = "+ Ajouter";
        addBtn.setAttribute("aria-expanded", isAddPanelOpen ? "true" : "false");
        addBtn.addEventListener("click", () => {{
          isAddPanelOpen = !isAddPanelOpen;
          pairActionError = "";
          renderPairs();
          renderAddPairPanel();
        }});
        wrap.appendChild(addBtn);
      }}
      renderAddPairPanel();
    }}

    function renderBanner() {{
      const banner = document.getElementById("statusBanner");
      const rows = DATA[selectedPair] || [];
      const sr = SR_DATA[selectedPair] || null;
      const spreadVal = typeof SPREAD_DATA[selectedPair] === "number" ? SPREAD_DATA[selectedPair] : null;
      const digits = getPairDigits(selectedPair);
      banner.innerHTML = "";

      const isWait = rows.length === 0 || rows.every(r => r.direction === "WAIT");
      const topRow = document.createElement("div");
      topRow.className = "banner-row";
      const leftGroup = document.createElement("div");
      leftGroup.className = "banner-group";
      const rightGroup = document.createElement("div");
      rightGroup.className = "banner-group";

      const setupLbl = document.createElement("span");
      setupLbl.className = "banner-label";
      setupLbl.textContent = "Setup 1m/3m";
      const sep1 = document.createElement("span");
      sep1.className = "banner-sep";
      sep1.textContent = "·";
      const setupVal = document.createElement("span");

      const marketLbl = document.createElement("span");
      marketLbl.className = "banner-label";
      marketLbl.textContent = "État du marché";
      const sep2 = document.createElement("span");
      sep2.className = "banner-sep";
      sep2.textContent = "·";
      const marketVal = document.createElement("span");

      const sessionInfo = getForexSessionInfo(new Date());
      const sessionSep = document.createElement("span");
      sessionSep.className = "banner-sep";
      sessionSep.textContent = "·";
      const sessionEl = document.createElement("span");
      sessionEl.className = sessionInfo.tone === "WARN" ? "tone-warn" : (sessionInfo.tone === "GOOD" ? "tone-buy" : "banner-ratios");
      sessionEl.style.fontSize = "12px";
      sessionEl.textContent = "Session : " + sessionInfo.label;

      if (isWait) {{
        setupVal.className = "tone-warn";
        setupVal.textContent = "En attente des données MT5";
        marketVal.className = "tone-warn";
        marketVal.textContent = "WAIT";
        leftGroup.append(setupLbl, sep1, setupVal);
        rightGroup.append(marketLbl, sep2, marketVal, sessionSep, sessionEl);
        topRow.append(leftGroup, rightGroup);
        banner.appendChild(topRow);
        return;
      }}

      const setup = evaluatePairSetup(rows);
      setupVal.textContent = setup.setupText;
      if (setup.status === "READY_BUY") setupVal.className = "tone-buy";
      else if (setup.status === "READY_SELL") setupVal.className = "tone-sell";
      else if (setup.status === "CALM_BLOCKED" || setup.status === "COUNTER_TREND") setupVal.className = "tone-warn";
      else setupVal.className = "tone-muted";

      marketVal.className = setup.isMarketActive ? "tone-buy" : "tone-warn";
      marketVal.textContent = setup.isMarketActive ? "Marché actif" : "Marché calme / plat";

      const sep3 = document.createElement("span");
      sep3.className = "banner-sep";
      sep3.textContent = "·";
      const ratiosEl = document.createElement("span");
      ratiosEl.className = "banner-ratios";
      ratiosEl.textContent = "ATR " + setup.atrRatio.toFixed(2) + "x · Vol " + setup.volRatio.toFixed(2) + "x";

      leftGroup.append(setupLbl, sep1, setupVal);
      rightGroup.append(marketLbl, sep2, marketVal, sep3, ratiosEl);

      if (spreadVal !== null) {{
        const sep4 = document.createElement("span");
        sep4.className = "banner-sep";
        sep4.textContent = "·";
        const spreadEl = document.createElement("span");
        const isWide = spreadVal >= 2.0;
        spreadEl.className = isWide ? "banner-ratios tone-warn" : "banner-ratios";
        spreadEl.textContent = "Spread " + spreadVal.toFixed(1) + " pips" + (isWide ? " · Spread large" : "");
        rightGroup.append(sep4, spreadEl);
      }}
      rightGroup.append(sessionSep, sessionEl);

      topRow.append(leftGroup, rightGroup);
      banner.appendChild(topRow);

      // Deuxième ligne : Support / Résistance, Alerte de prudence & Référence risque (SL ATR + R:R)
      const activeRow = rows.find(r => r.timeframe === selectedTfDetail) || rows[0];
      const srRow = document.createElement("div");
      srRow.className = "banner-row banner-sr-row";
      const srLeft = document.createElement("div");
      srLeft.className = "banner-group";

      const srLbl = document.createElement("span");
      srLbl.className = "banner-label";
      srLbl.textContent = "Support / Résistance";
      const srSep1 = document.createElement("span");
      srSep1.className = "banner-sep";
      srSep1.textContent = "·";

      const sEl = document.createElement("span");
      if (sr && sr.support) {{
        sEl.className = "sr-val sr-buy";
        sEl.textContent = "S " + sr.support.price.toFixed(digits) + " (-" + sr.support.distancePips.toFixed(1) + " pips · " + sr.support.source + ")";
      }} else {{
        sEl.className = "sr-val tone-subtle";
        sEl.textContent = "S —";
      }}

      const srSep2 = document.createElement("span");
      srSep2.className = "banner-sep";
      srSep2.textContent = "·";

      const rEl = document.createElement("span");
      if (sr && sr.resistance) {{
        rEl.className = "sr-val sr-sell";
        rEl.textContent = "R " + sr.resistance.price.toFixed(digits) + " (+" + sr.resistance.distancePips.toFixed(1) + " pips · " + sr.resistance.source + ")";
      }} else {{
        rEl.className = "sr-val tone-subtle";
        rEl.textContent = "R —";
      }}

      srLeft.append(srLbl, srSep1, sEl, srSep2, rEl);

      const srRight = document.createElement("div");
      srRight.className = "banner-group";
      const srAlertSpan = document.createElement("span");
      if (!sr) {{
        srAlertSpan.className = "tone-subtle";
        srAlertSpan.textContent = "En attente des niveaux S/R";
      }} else if (sr.proximityAlert === "NEAR_BOTH") {{
        srAlertSpan.className = "tone-warn";
        srAlertSpan.textContent = "Compression entre Support et Résistance · Prudence";
      }} else if (sr.proximityAlert === "NEAR_RESISTANCE" && sr.resistance) {{
        srAlertSpan.className = "tone-warn";
        srAlertSpan.textContent = "Prudence ACHAT · Proche Résistance (" + sr.resistance.distancePips.toFixed(1) + " pips)";
      }} else if (sr.proximityAlert === "NEAR_SUPPORT" && sr.support) {{
        srAlertSpan.className = "tone-warn";
        srAlertSpan.textContent = "Prudence VENTE · Proche Support (" + sr.support.distancePips.toFixed(1) + " pips)";
      }} else {{
        srAlertSpan.className = "tone-subtle";
        srAlertSpan.textContent = "Zone libre entre Support et Résistance";
      }}
      srRight.appendChild(srAlertSpan);

      const atrForRisk = activeRow && typeof activeRow.atr_value === "number" && activeRow.atr_value > 0
        ? activeRow.atr_value
        : (rows[0] ? rows[0].atr_value : 0);
      const dirHint = setup.direction || (activeRow ? activeRow.direction : "NEUTRE");
      const riskEst = computeRiskEstimate(selectedPair, atrForRisk, sr, dirHint);
      if (riskEst) {{
        const riskSep1 = document.createElement("span");
        riskSep1.className = "banner-sep";
        riskSep1.textContent = "·";
        const slEl = document.createElement("span");
        slEl.className = "banner-ratios";
        slEl.style.color = "#cbd5e1";
        slEl.textContent = "SL ~" + riskEst.slPips.toFixed(1) + " pips";
        srRight.append(riskSep1, slEl);

        if (riskEst.rrRatio !== null) {{
          const riskSep2 = document.createElement("span");
          riskSep2.className = "banner-sep";
          riskSep2.textContent = "·";
          const rrEl = document.createElement("span");
          rrEl.className = "banner-ratios";
          rrEl.style.fontWeight = "600";
          rrEl.style.color = riskEst.rrRatio >= 1.5 ? "#34d399" : (riskEst.rrRatio < 1.0 ? "#fcd34d" : "#cbd5e1");
          rrEl.textContent = "R:R ~" + riskEst.rrRatio.toFixed(1) + "x";
          srRight.append(riskSep2, rrEl);
        }}
      }}

      srRow.append(srLeft, srRight);
      banner.appendChild(srRow);

      // Troisième ligne : 3 indicateurs Pine Script de prévision + Accord Pine (informatif)
      const pf = activeRow && activeRow.pine_forecast ? activeRow.pine_forecast : null;
      const pfRow = document.createElement("div");
      pfRow.className = "banner-row banner-sr-row";
      const pfLeft = document.createElement("div");
      pfLeft.className = "banner-group";

      const pfLbl = document.createElement("span");
      pfLbl.className = "banner-label";
      pfLbl.textContent = "Prévision Pine (" + (activeRow ? activeRow.timeframe : selectedTfDetail) + ")";
      const pfSep0 = document.createElement("span");
      pfSep0.className = "banner-sep";
      pfSep0.textContent = "·";
      pfLeft.append(pfLbl, pfSep0);

      if (!pf) {{
        const waitPf = document.createElement("span");
        waitPf.className = "tone-subtle";
        waitPf.textContent = "En attente des données MT5";
        pfLeft.appendChild(waitPf);
      }} else {{
        const nc = pf.nextCandle;
        const bo = pf.breakout;
        const ls = pf.levelsStrength;

        const ncLbl = document.createElement("span");
        ncLbl.className = "tone-subtle";
        ncLbl.textContent = "Next Candle :";
        const ncVal = document.createElement("span");
        ncVal.className = "sr-val " + (nc.bias === "HAUSSE" ? "tone-buy" : (nc.bias === "BAISSE" ? "tone-sell" : "tone-muted"));
        const ncDomPct = nc.bias === "BAISSE" ? nc.shortPct : nc.longPct;
        const ncDomWord = nc.bias === "HAUSSE" ? "Hausse" : (nc.bias === "BAISSE" ? "Baisse" : "Neutre");
        ncVal.textContent = ncDomPct + "% " + ncDomWord;
        const ncSub = document.createElement("span");
        ncSub.className = "banner-ratios";
        ncSub.textContent = "(" + (nc.bias === "BAISSE" ? nc.longPct + "% ▲" : nc.shortPct + "% ▼") + (nc.strongSetup ? " · Fort" : "") + ")";

        const pfSep1 = document.createElement("span");
        pfSep1.className = "banner-sep";
        pfSep1.textContent = "·";

        const boLbl = document.createElement("span");
        boLbl.className = "tone-subtle";
        boLbl.textContent = "Breakout :";
        const boVal = document.createElement("span");
        boVal.className = "sr-val " + (bo.bias === "HAUSSE" ? "tone-buy" : (bo.bias === "BAISSE" ? "tone-sell" : "tone-muted"));
        boVal.textContent = bo.upPct.toFixed(1) + "% ▲ / " + bo.dnPct.toFixed(1) + "% ▼";

        pfLeft.append(ncLbl, ncVal, ncSub, pfSep1, boLbl, boVal);
        if (typeof bo.winRate === "number") {{
          const boWr = document.createElement("span");
          boWr.className = "banner-ratios";
          boWr.textContent = "(WR " + bo.winRate.toFixed(0) + "%)";
          pfLeft.appendChild(boWr);
        }}

        const pfSep2 = document.createElement("span");
        pfSep2.className = "banner-sep";
        pfSep2.textContent = "·";

        const lsLbl = document.createElement("span");
        lsLbl.className = "tone-subtle";
        lsLbl.textContent = "Levels :";
        const lsVal = document.createElement("span");
        lsVal.className = "sr-val " + (ls.bias === "HAUSSE" ? "tone-buy" : (ls.bias === "BAISSE" ? "tone-sell" : "tone-muted"));
        const lsDomPct = ls.bias === "BAISSE" ? ls.bearPct : ls.bullPct;
        const lsDomWord = ls.bias === "HAUSSE" ? "Hausse" : (ls.bias === "BAISSE" ? "Baisse" : "Neutre");
        lsVal.textContent = lsDomPct + "% " + lsDomWord;
        const lsSub = document.createElement("span");
        lsSub.className = "banner-ratios";
        lsSub.textContent = "(" + (ls.bias === "BAISSE" ? ls.bullPct + "% ▲" : ls.bearPct + "% ▼") + ")";

        pfLeft.append(pfSep2, lsLbl, lsVal, lsSub);
      }}

      const pfRight = document.createElement("div");
      pfRight.className = "banner-group";
      if (pf) {{
        const cons = getPineConsensus(pf);
        const cLbl = document.createElement("span");
        cLbl.className = "banner-ratios";
        cLbl.textContent = "Accord Pine :";
        const cVal = document.createElement("span");
        cVal.className = "banner-ratios";
        cVal.style.fontWeight = "600";
        cVal.style.color = cons.bias === "HAUSSE" ? "#34d399" : (cons.bias === "BAISSE" ? "#f87171" : "#cbd5e1");
        cVal.textContent = cons.label;
        const cSep = document.createElement("span");
        cSep.className = "banner-sep";
        cSep.textContent = "·";
        pfRight.append(cLbl, cVal, cSep);
      }}
      const infoEl = document.createElement("span");
      infoEl.className = "banner-ratios";
      infoEl.textContent = "Informatif";
      pfRight.appendChild(infoEl);
      pfRow.append(pfLeft, pfRight);
      banner.appendChild(pfRow);
    }}

    function renderTable() {{
      const tbody = document.getElementById("tableBody");
      tbody.innerHTML = "";
      const nowSec = Math.floor(Date.now() / 1000);
      const rows = DATA[selectedPair] || [];
      rows.forEach(r => {{
        const tr = document.createElement("tr");
        if (r.timeframe === selectedTfDetail) tr.className = "selected";
        tr.addEventListener("click", () => setSelectedTfDetail(r.timeframe));

        const tdTf = document.createElement("td");
        tdTf.className = "tf-cell";
        tdTf.textContent = r.timeframe;

        const tdSig = document.createElement("td");
        const sigSpan = document.createElement("span");
        sigSpan.className = "sig-btn sig-" + r.direction;
        sigSpan.textContent = r.signal_label;
        tdSig.appendChild(sigSpan);

        const tdConf = document.createElement("td");
        tdConf.className = "conf-cell";
        const confWrap = document.createElement("span");
        confWrap.className = "conf-wrap";
        const confTextSpan = document.createElement("span");
        confTextSpan.textContent = r.confluence_label;
        confWrap.appendChild(confTextSpan);

        let align = r.core5_alignment;
        if (!align && Array.isArray(r.indicators) && r.indicators.length >= 5) {{
          const first5 = r.indicators.slice(0, 5);
          if (first5.every(ind => ind.vote === 1)) align = "ACHAT";
          else if (first5.every(ind => ind.vote === -1)) align = "VENTE";
        }}
        if (r.direction !== "WAIT" && (align === "ACHAT" || align === "VENTE")) {{
          const dot = document.createElement("span");
          dot.className = "core5-dot " + (align === "ACHAT" ? "core5-dot-buy" : "core5-dot-sell");
          dot.title = align === "ACHAT"
            ? "5/5 alignés ACHAT (EMA, Bollinger, RSI, MACD, Stochastique)"
            : "5/5 alignés VENTE (EMA, Bollinger, RSI, MACD, Stochastique)";
          dot.setAttribute("aria-label", dot.title);
          confWrap.appendChild(dot);
        }}
        tdConf.appendChild(confWrap);

        const tdMaj = document.createElement("td");
        tdMaj.className = "maj-cell";
        tdMaj.dataset.tf = r.timeframe;
        const target = getNextTargetSec(r.timeframe, nowSec);
        tdMaj.textContent = fmtMmSs(target - nowSec);

        tr.appendChild(tdTf);
        tr.appendChild(tdSig);
        tr.appendChild(tdConf);
        tr.appendChild(tdMaj);
        tbody.appendChild(tr);
      }});
      document.getElementById("footerTime").textContent = "Dernière mise à jour : " + UPDATED_AT;
      document.getElementById("footerPair").textContent = "Exness-MT5Trial16 · " + selectedPair;
    }}

    function renderDetails() {{
      const panel = document.getElementById("detailsPanel");
      const rows = DATA[selectedPair] || [];
      const row = rows.find(r => r.timeframe === selectedTfDetail) || rows[0];
      if (!row || !Array.isArray(row.indicators) || row.indicators.length === 0) {{
        panel.style.display = "none";
        panel.innerHTML = "";
        return;
      }}

      panel.style.display = "block";
      panel.innerHTML = "";

      const header = document.createElement("div");
      header.className = "details-header";

      const titleWrap = document.createElement("div");
      titleWrap.className = "details-title-wrap";

      const title = document.createElement("h3");
      title.className = "details-title";
      title.textContent = "Détail des 8 indicateurs — " + row.pair + " (" + row.timeframe + ")";

      const zone = document.createElement("span");
      zone.className = "details-zone";
      zone.textContent = row.zone_label + " · Pivot " + row.pivot_htf;

      titleWrap.appendChild(title);
      titleWrap.appendChild(zone);

      const neutralCount = typeof row.neutral_count === "number"
        ? row.neutral_count
        : Math.max(0, 8 - row.buy_count - row.sell_count);
      const counts = document.createElement("div");
      counts.className = "details-counts";
      counts.textContent = "Achat : " + row.buy_count + "/8 · Vente : " + row.sell_count + "/8 · Neutre : " + neutralCount + "/8";

      header.appendChild(titleWrap);
      header.appendChild(counts);
      panel.appendChild(header);

      const grid = document.createElement("div");
      grid.className = "details-grid";

      row.indicators.forEach(ind => {{
        const card = document.createElement("div");
        card.className = "ind-card";

        const info = document.createElement("div");
        info.className = "ind-info";

        const nameEl = document.createElement("div");
        nameEl.className = "ind-name";
        nameEl.textContent = ind.name;

        const sumEl = document.createElement("div");
        sumEl.className = "ind-summary";
        sumEl.textContent = ind.summary;

        info.appendChild(nameEl);
        info.appendChild(sumEl);

        const badge = document.createElement("span");
        if (ind.vote === 1) {{
          badge.className = "ind-badge ind-badge-buy";
          badge.textContent = "+1 ACHAT";
        }} else if (ind.vote === -1) {{
          badge.className = "ind-badge ind-badge-sell";
          badge.textContent = "-1 VENTE";
        }} else {{
          badge.className = "ind-badge ind-badge-neutral";
          badge.textContent = "0 NEUTRE";
        }}

        card.appendChild(info);
        card.appendChild(badge);
        grid.appendChild(card);
      }});

      panel.appendChild(grid);
    }}

    function renderChart() {{
      const panel = document.getElementById("chartPanel");
      const series = PRICE_DATA[selectedPair] || [];
      if (!Array.isArray(series) || series.length === 0) {{
        panel.style.display = "none";
        panel.innerHTML = "";
        return;
      }}

      const digits = getPairDigits(selectedPair);
      const latest = series[series.length - 1].price;
      const first = series[0].price;
      const strokeColor = latest >= first ? "#10b981" : "#ef4444";

      panel.style.display = "block";
      panel.innerHTML = "";

      const header = document.createElement("div");
      header.className = "details-header";

      const titleWrap = document.createElement("div");
      titleWrap.className = "details-title-wrap";

      const title = document.createElement("h3");
      title.className = "details-title";
      title.textContent = "Prix en temps réel — " + selectedPair;

      const sub = document.createElement("span");
      sub.className = "details-zone";
      sub.textContent = "Bougies 30s (" + series.length + " points)";

      titleWrap.appendChild(title);
      titleWrap.appendChild(sub);

      const headerRight = document.createElement("div");
      headerRight.className = "chart-header-right";
      const sr = SR_DATA[selectedPair] || null;
      const support = sr && sr.support ? sr.support : null;
      const resistance = sr && sr.resistance ? sr.resistance : null;
      if (support) {{
        const sTag = document.createElement("span");
        sTag.className = "sr-buy";
        sTag.textContent = "S " + support.price.toFixed(digits);
        headerRight.appendChild(sTag);
      }}
      if (resistance) {{
        const rTag = document.createElement("span");
        rTag.className = "sr-sell";
        rTag.textContent = "R " + resistance.price.toFixed(digits);
        headerRight.appendChild(rTag);
      }}

      const priceBadge = document.createElement("div");
      priceBadge.className = "chart-price-badge";
      priceBadge.textContent = latest.toFixed(digits);
      headerRight.appendChild(priceBadge);

      header.appendChild(titleWrap);
      header.appendChild(headerRight);
      panel.appendChild(header);

      const container = document.createElement("div");
      container.className = "chart-container";

      const W = 1000;
      const H = 224;
      const padL = digits <= 3 ? 68 : 74;
      const padR = 14;
      const padT = 12;
      const padB = 26;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;

      let minP = Infinity;
      let maxP = -Infinity;
      series.forEach(pt => {{
        if (pt.price < minP) minP = pt.price;
        if (pt.price > maxP) maxP = pt.price;
      }});
      const pip = getPipSize(selectedPair);
      const span = maxP - minP || pip;
      const showSupport = support && support.price >= minP - span * 0.65 && support.price <= maxP + span * 0.65;
      const showResistance = resistance && resistance.price >= minP - span * 0.65 && resistance.price <= maxP + span * 0.65;

      let visMin = minP;
      let visMax = maxP;
      if (showSupport) {{
        visMin = Math.min(visMin, support.price);
        visMax = Math.max(visMax, support.price);
      }}
      if (showResistance) {{
        visMin = Math.min(visMin, resistance.price);
        visMax = Math.max(visMax, resistance.price);
      }}
      const visSpan = visMax - visMin || pip;
      const minY = visMin - visSpan * 0.08;
      const maxY = visMax + visSpan * 0.08;
      const spanY = maxY - minY;

      const coords = series.map((pt, idx) => {{
        const x = padL + (series.length === 1 ? plotW / 2 : (idx / (series.length - 1)) * plotW);
        const y = padT + (1 - (pt.price - minY) / spanY) * plotH;
        return {{ x, y, time: pt.time, price: pt.price }};
      }});

      const svgNS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(svgNS, "svg");
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      svg.setAttribute("preserveAspectRatio", "none");
      svg.className.baseVal = "chart-svg";

      const ySteps = 4;
      for (let i = 0; i <= ySteps; i++) {{
        const ratio = i / ySteps;
        const gy = padT + ratio * plotH;
        const val = maxY - ratio * spanY;

        const line = document.createElementNS(svgNS, "line");
        line.setAttribute("x1", String(padL));
        line.setAttribute("x2", String(W - padR));
        line.setAttribute("y1", gy.toFixed(1));
        line.setAttribute("y2", gy.toFixed(1));
        line.setAttribute("stroke", "#1e2633");
        line.setAttribute("stroke-dasharray", "3 3");
        svg.appendChild(line);

        const lbl = document.createElementNS(svgNS, "text");
        lbl.setAttribute("x", String(padL - 8));
        lbl.setAttribute("y", (gy + 4).toFixed(1));
        lbl.setAttribute("text-anchor", "end");
        lbl.setAttribute("fill", "#94a3b8");
        lbl.setAttribute("font-size", "11");
        lbl.setAttribute("font-family", "JetBrains Mono, Consolas, monospace");
        lbl.textContent = val.toFixed(digits);
        svg.appendChild(lbl);
      }}

      function drawSrLine(priceVal, labelText, colorHex) {{
        const sy = padT + (1 - (priceVal - minY) / spanY) * plotH;
        const srLine = document.createElementNS(svgNS, "line");
        srLine.setAttribute("x1", String(padL));
        srLine.setAttribute("x2", String(W - padR));
        srLine.setAttribute("y1", sy.toFixed(1));
        srLine.setAttribute("y2", sy.toFixed(1));
        srLine.setAttribute("stroke", colorHex);
        srLine.setAttribute("stroke-dasharray", "4 4");
        srLine.setAttribute("stroke-opacity", "0.85");
        svg.appendChild(srLine);

        const srTxt = document.createElementNS(svgNS, "text");
        srTxt.setAttribute("x", String(W - padR - 4));
        srTxt.setAttribute("y", (sy - 4 < padT + 10 ? sy + 12 : sy - 4).toFixed(1));
        srTxt.setAttribute("text-anchor", "end");
        srTxt.setAttribute("fill", colorHex);
        srTxt.setAttribute("font-size", "11");
        srTxt.setAttribute("font-family", "JetBrains Mono, Consolas, monospace");
        srTxt.textContent = labelText;
        svg.appendChild(srTxt);
      }}

      if (showSupport) {{
        drawSrLine(support.price, "S " + support.price.toFixed(digits), "#34d399");
      }}
      if (showResistance) {{
        drawSrLine(resistance.price, "R " + resistance.price.toFixed(digits), "#f87171");
      }}

      const xAxis = document.createElementNS(svgNS, "line");
      xAxis.setAttribute("x1", String(padL));
      xAxis.setAttribute("x2", String(W - padR));
      xAxis.setAttribute("y1", String(H - padB));
      xAxis.setAttribute("y2", String(H - padB));
      xAxis.setAttribute("stroke", "#1e2633");
      svg.appendChild(xAxis);

      const tickCount = Math.min(5, coords.length);
      for (let t = 0; t < tickCount; t++) {{
        const idx = tickCount === 1 ? 0 : Math.round((t / (tickCount - 1)) * (coords.length - 1));
        const pt = coords[idx];
        const tLbl = document.createElementNS(svgNS, "text");
        tLbl.setAttribute("x", pt.x.toFixed(1));
        tLbl.setAttribute("y", String(H - 6));
        tLbl.setAttribute("text-anchor", t === 0 ? "start" : (t === tickCount - 1 ? "end" : "middle"));
        tLbl.setAttribute("fill", "#94a3b8");
        tLbl.setAttribute("font-size", "11");
        tLbl.setAttribute("font-family", "JetBrains Mono, Consolas, monospace");
        tLbl.textContent = pt.time || "";
        svg.appendChild(tLbl);
      }}

      const poly = document.createElementNS(svgNS, "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", strokeColor);
      poly.setAttribute("stroke-width", "2");
      poly.setAttribute("stroke-linejoin", "round");
      poly.setAttribute("stroke-linecap", "round");
      poly.setAttribute("points", coords.map(c => c.x.toFixed(1) + "," + c.y.toFixed(1)).join(" "));
      svg.appendChild(poly);

      const guideLine = document.createElementNS(svgNS, "line");
      guideLine.setAttribute("y1", String(padT));
      guideLine.setAttribute("y2", String(H - padB));
      guideLine.setAttribute("stroke", "#475569");
      guideLine.setAttribute("stroke-dasharray", "3 3");
      guideLine.style.display = "none";
      svg.appendChild(guideLine);

      const activeDot = document.createElementNS(svgNS, "circle");
      activeDot.setAttribute("r", "4");
      activeDot.setAttribute("fill", strokeColor);
      activeDot.setAttribute("stroke", "#0f131a");
      activeDot.setAttribute("stroke-width", "2");
      activeDot.style.display = "none";
      svg.appendChild(activeDot);

      const tooltip = document.createElement("div");
      tooltip.className = "chart-tooltip";

      svg.addEventListener("mousemove", (evt) => {{
        const rect = svg.getBoundingClientRect();
        if (!rect.width) return;
        const mouseX = ((evt.clientX - rect.left) / rect.width) * W;
        let nearest = coords[0];
        let bestDist = Infinity;
        coords.forEach(c => {{
          const d = Math.abs(c.x - mouseX);
          if (d < bestDist) {{
            bestDist = d;
            nearest = c;
          }}
        }});

        guideLine.setAttribute("x1", nearest.x.toFixed(1));
        guideLine.setAttribute("x2", nearest.x.toFixed(1));
        guideLine.style.display = "block";
        activeDot.setAttribute("cx", nearest.x.toFixed(1));
        activeDot.setAttribute("cy", nearest.y.toFixed(1));
        activeDot.style.display = "block";

        tooltip.innerHTML = "<div class='chart-tooltip-time'>" + (nearest.time || "") + "</div><div>" + selectedPair + " : " + nearest.price.toFixed(digits) + "</div>";
        tooltip.style.display = "block";
        const leftPct = (nearest.x / W) * 100;
        tooltip.style.left = Math.min(82, Math.max(4, leftPct)) + "%";
        tooltip.style.top = "8px";
      }});

      svg.addEventListener("mouseleave", () => {{
        guideLine.style.display = "none";
        activeDot.style.display = "none";
        tooltip.style.display = "none";
      }});

      container.appendChild(svg);
      container.appendChild(tooltip);
      panel.appendChild(container);
    }}

    function formatSrNote(sr) {{
      if (!sr) return "S/R —";
      if (sr.proximityAlert === "NEAR_BOTH") return "Compression S/R";
      if (sr.proximityAlert === "NEAR_RESISTANCE" && sr.resistance) {{
        return "Proche Résistance (" + sr.resistance.distancePips.toFixed(1) + " pips)";
      }}
      if (sr.proximityAlert === "NEAR_SUPPORT" && sr.support) {{
        return "Proche Support (" + sr.support.distancePips.toFixed(1) + " pips)";
      }}
      return "Zone libre";
    }}

    function loadHistory() {{
      try {{
        const raw = localStorage.getItem(STORAGE_HISTORY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.slice(0, 10) : [];
      }} catch (_e) {{
        return [];
      }}
    }}

    function renderHistory(entries) {{
      const panel = document.getElementById("historyPanel");
      panel.innerHTML = "";

      const header = document.createElement("div");
      header.className = "details-header";

      const titleWrap = document.createElement("div");
      titleWrap.className = "details-title-wrap";
      const title = document.createElement("h3");
      title.className = "details-title";
      title.textContent = "Derniers Setups Prêts (max 10)";
      const cnt = document.createElement("span");
      cnt.className = "details-zone font-mono tabular-nums";
      cnt.textContent = entries.length + " / 10";
      titleWrap.append(title, cnt);

      const resolved = entries.filter(e => e.outcomeStatus === "WIN" || e.outcomeStatus === "LOSS");
      if (resolved.length > 0) {{
        const wins = resolved.filter(e => e.outcomeStatus === "WIN").length;
        const winRatePct = Math.round((wins / resolved.length) * 100);
        const sep = document.createElement("span");
        sep.className = "banner-sep";
        sep.textContent = "·";
        const wr = document.createElement("span");
        wr.className = "details-zone font-mono tabular-nums";
        wr.style.fontWeight = "600";
        wr.style.color = winRatePct >= 50 ? "#34d399" : "#fcd34d";
        wr.textContent = "Taux : " + wins + "/" + resolved.length + " (" + winRatePct + "%)";
        titleWrap.append(sep, wr);
      }}
      header.appendChild(titleWrap);

      if (entries.length > 0) {{
        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "history-clear-btn";
        clearBtn.textContent = "Effacer";
        clearBtn.addEventListener("click", () => {{
          localStorage.removeItem(STORAGE_HISTORY);
          renderHistory([]);
          renderHeaderWinrate();
        }});
        header.appendChild(clearBtn);
      }}
      panel.appendChild(header);

      if (entries.length === 0) {{
        const empty = document.createElement("p");
        empty.className = "history-empty";
        empty.textContent = "Aucun Setup Prêt 1m/3m détecté pour le moment durant cette session.";
        panel.appendChild(empty);
        return;
      }}

      const scroll = document.createElement("div");
      scroll.className = "table-scroll";
      const table = document.createElement("table");
      table.className = "history-table";
      const thead = document.createElement("thead");
      thead.innerHTML = "<tr><th>Heure</th><th>Paire</th><th>TF</th><th>Sens</th><th>Prix</th><th>Spread</th><th>Accord Pine</th><th>Contexte S/R</th><th>Résultat (3 bougies)</th></tr>";
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      entries.forEach(item => {{
        const tr = document.createElement("tr");
        tr.addEventListener("click", () => {{
          if (PAIRS.includes(item.pair)) selectPairAndRender(item.pair);
        }});
        const d = getPairDigits(item.pair);

        const tdTime = document.createElement("td");
        tdTime.className = "font-mono tabular-nums";
        tdTime.style.color = "#cbd5e1";
        tdTime.textContent = item.time;

        const tdPair = document.createElement("td");
        tdPair.className = "font-mono";
        tdPair.style.fontWeight = "700";
        tdPair.style.color = "#f1f5f9";
        tdPair.textContent = item.pair;

        const tdTf = document.createElement("td");
        tdTf.className = "font-mono tabular-nums";
        tdTf.style.color = "#cbd5e1";
        tdTf.textContent = item.timeframe;

        const tdDir = document.createElement("td");
        tdDir.className = item.direction === "ACHAT" ? "history-dir-buy" : "history-dir-sell";
        tdDir.textContent = item.direction;

        const tdPrice = document.createElement("td");
        tdPrice.className = "font-mono tabular-nums";
        tdPrice.style.color = "#e2e8f0";
        tdPrice.textContent = typeof item.price === "number" ? item.price.toFixed(d) : "—";

        const tdSpread = document.createElement("td");
        tdSpread.className = "font-mono tabular-nums";
        tdSpread.style.color = "#cbd5e1";
        tdSpread.textContent = typeof item.spreadPips === "number" ? item.spreadPips.toFixed(1) + " pips" : "—";

        const tdPine = document.createElement("td");
        tdPine.className = "font-mono";
        const pineTxt = item.pineNote || "—";
        tdPine.textContent = pineTxt;
        if (pineTxt.indexOf("Hausse") !== -1) {{
          tdPine.style.color = "#34d399";
          tdPine.style.fontWeight = "600";
        }} else if (pineTxt.indexOf("Baisse") !== -1) {{
          tdPine.style.color = "#f87171";
          tdPine.style.fontWeight = "600";
        }} else {{
          tdPine.style.color = "#94a3b8";
        }}

        const tdSr = document.createElement("td");
        tdSr.style.color = "#94a3b8";
        tdSr.textContent = item.srNote || "—";

        const tdOutcome = document.createElement("td");
        tdOutcome.className = "font-mono tabular-nums";
        if (item.outcomeStatus === "PENDING") {{
          tdOutcome.style.color = "#94a3b8";
          tdOutcome.textContent = "En cours";
        }} else if (item.outcomeStatus === "WIN" && typeof item.outcomePips === "number") {{
          tdOutcome.style.color = "#34d399";
          tdOutcome.style.fontWeight = "600";
          tdOutcome.textContent = "+" + Math.abs(item.outcomePips).toFixed(1) + " pips · Gagnant";
        }} else if (item.outcomeStatus === "LOSS" && typeof item.outcomePips === "number") {{
          tdOutcome.style.color = "#f87171";
          tdOutcome.style.fontWeight = "600";
          const formatted = item.outcomePips <= 0 ? item.outcomePips.toFixed(1) : "-" + item.outcomePips.toFixed(1);
          tdOutcome.textContent = formatted + " pips · Perdant";
        }} else {{
          tdOutcome.style.color = "#64748b";
          tdOutcome.textContent = "—";
        }}

        tr.append(tdTime, tdPair, tdTf, tdDir, tdPrice, tdSpread, tdPine, tdSr, tdOutcome);
        tbody.appendChild(tr);
      }});
      table.appendChild(tbody);
      scroll.appendChild(table);
      panel.appendChild(scroll);
    }}

    function processSetupsAndRenderHistory() {{
      let prevSigs = {{}};
      try {{
        prevSigs = JSON.parse(localStorage.getItem(STORAGE_SIGS) || "{{}}") || {{}};
      }} catch (_e) {{
        prevSigs = {{}};
      }}
      const newEntries = [];
      let changed = false;
      const nowDate = new Date();
      const nowTime = fmtClockHHMMSS(nowDate);
      const nowSec = Math.floor(nowDate.getTime() / 1000);

      PAIRS.forEach(p => {{
        const rows = DATA[p] || [];
        if (rows.length === 0 || rows.every(r => r.direction === "WAIT")) return;
        const setup = evaluatePairSetup(rows);
        const sig = (setup.status === "READY_BUY" || setup.status === "READY_SELL") && setup.direction && setup.triggerTf
          ? setup.direction + ":" + setup.triggerTf
          : "NONE";
        if (sig !== "NONE" && prevSigs[p] !== sig && setup.triggerPrice !== null) {{
          const triggerRow = rows.find(r => r.timeframe === setup.triggerTf);
          const pineNote = getPineConsensus(triggerRow ? triggerRow.pine_forecast : null).label;
          newEntries.push({{
            id: String(Date.now()) + "-" + p,
            time: nowTime,
            pair: p,
            timeframe: setup.triggerTf,
            direction: setup.direction,
            price: setup.triggerPrice,
            spreadPips: typeof SPREAD_DATA[p] === "number" ? SPREAD_DATA[p] : null,
            srNote: formatSrNote(SR_DATA[p] || null),
            triggeredAtSec: nowSec,
            pineNote,
            outcomeStatus: "PENDING",
            outcomePips: null,
          }});
        }}
        if (prevSigs[p] !== sig) {{
          prevSigs[p] = sig;
          changed = true;
        }}
      }});

      if (changed) {{
        localStorage.setItem(STORAGE_SIGS, JSON.stringify(prevSigs));
      }}

      let history = loadHistory();
      let anyResolved = false;
      history = history.map(item => {{
        if ((item.outcomeStatus === "PENDING" || !item.outcomeStatus) && typeof item.triggeredAtSec === "number") {{
          const horizonSec = item.timeframe === "1m" ? 180 : 540;
          if (nowSec - item.triggeredAtSec >= horizonSec) {{
            const pairRows = DATA[item.pair] || [];
            const priceRow = pairRows.find(r => typeof r.price === "number" && r.price > 0);
            if (priceRow) {{
              const pip = getPipSize(item.pair);
              const rawPips = item.direction === "ACHAT"
                ? (priceRow.price - item.price) / pip
                : (item.price - priceRow.price) / pip;
              const roundedPips = Number(rawPips.toFixed(1));
              anyResolved = true;
              return Object.assign({{}}, item, {{
                outcomeStatus: roundedPips > 0 ? "WIN" : "LOSS",
                outcomePips: roundedPips,
              }});
            }}
          }}
        }}
        return item;
      }});

      if (newEntries.length > 0 || anyResolved) {{
        history = newEntries.concat(history).slice(0, 10);
        localStorage.setItem(STORAGE_HISTORY, JSON.stringify(history));
        if (newEntries.length > 0 && soundEnabled) {{
          playSetupChime(newEntries[0].direction);
        }}
      }}
      renderHistory(history);
    }}

    function computeSessionWinrate() {{
      const entries = loadHistory().slice(0, 10);
      const resolved = entries.filter(e => e.outcomeStatus === "WIN" || e.outcomeStatus === "LOSS");
      const wins = resolved.filter(e => e.outcomeStatus === "WIN").length;
      const pct = resolved.length > 0 ? Math.round((wins / resolved.length) * 100) : null;
      return {{ wins, total: resolved.length, pct }};
    }}

    function renderHeaderWinrate() {{
      const el = document.getElementById("headerWinrateVal");
      if (!el) return;
      const wrInfo = computeSessionWinrate();
      if (wrInfo.pct === null) {{
        el.textContent = "—";
        el.style.color = "#94a3b8";
        el.style.fontWeight = "400";
      }} else {{
        el.textContent = wrInfo.pct + "% (" + wrInfo.wins + "/" + wrInfo.total + ")";
        el.style.color = wrInfo.pct >= 50 ? "#34d399" : "#fcd34d";
        el.style.fontWeight = "600";
      }}
    }}

    renderSoundButton();
    renderPairs();
    renderUsdStrength();
    processSetupsAndRenderHistory();
    renderHeaderWinrate();
    renderBanner();
    renderTable();
    renderDetails();
    renderChart();
    document.getElementById("liveClock").textContent = fmtClockHHMMSS(new Date());

    try {{
      const savedScrollY = sessionStorage.getItem(STORAGE_SCROLL_Y);
      if (savedScrollY !== null) {{
        const y = parseInt(savedScrollY, 10);
        if (!Number.isNaN(y) && y > 0) window.scrollTo(0, y);
        sessionStorage.removeItem(STORAGE_SCROLL_Y);
      }}
    }} catch (_e) {{}}

    setInterval(() => {{
      const nowSec = Math.floor(Date.now() / 1000);
      document.getElementById("liveClock").textContent = fmtClockHHMMSS(new Date(nowSec * 1000));
      document.querySelectorAll("[data-tf]").forEach(el => {{
        const tf = el.dataset.tf;
        const target = getNextTargetSec(tf, nowSec);
        el.textContent = fmtMmSs(target - nowSec);
      }});
      if (nowSec % 30 === 26 || nowSec % 60 === 56) {{
        reloadPreservingScroll();
      }}
    }}, 500);
  </script>
</body>
</html>
"""


def write_dashboard_atomically(html_content: str) -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = DASHBOARD_DIR / "forex_dashboard.tmp.html"
    tmp_path.write_text(html_content, encoding="utf-8")
    os.replace(tmp_path, DASHBOARD_HTML_PATH)


def compute_sr_map(pairs_list: Optional[List[str]] = None) -> Dict[str, Optional[Dict[str, Any]]]:
    target_pairs = list(pairs_list) if pairs_list is not None else list(ACTIVE_PAIRS)
    sr_map: Dict[str, Optional[Dict[str, Any]]] = {p: None for p in target_pairs}
    for pair in target_pairs:
        try:
            df_1m = fetch_mt5_rates(pair, mt5.TIMEFRAME_M1, 120)
            df_5m = fetch_mt5_rates(pair, mt5.TIMEFRAME_M5, 80)
            h1_bar = fetch_pivot_htf_candle(pair, "H1")
            h4_bar = fetch_pivot_htf_candle(pair, "H4")
            tick = mt5.symbol_info_tick(pair)
            cur_px = 0.0
            if tick is not None and getattr(tick, "bid", 0) > 0:
                cur_px = float(tick.bid)
            elif df_1m is not None and len(df_1m) > 0:
                cur_px = float(df_1m["close"].iloc[-1])
            sr_map[pair] = compute_support_resistance(pair, cur_px, df_1m, df_5m, h1_bar, h4_bar)
        except Exception as exc:
            print(f"[ERREUR] S/R {pair} : {exc}")
            sr_map[pair] = None
    return sr_map


def compute_spread_map(pairs_list: Optional[List[str]] = None) -> Dict[str, Optional[float]]:
    target_pairs = list(pairs_list) if pairs_list is not None else list(ACTIVE_PAIRS)
    spread_map: Dict[str, Optional[float]] = {p: None for p in target_pairs}
    if mt5 is None:
        return spread_map
    for pair in target_pairs:
        try:
            tick = mt5.symbol_info_tick(pair)
            if tick is not None and getattr(tick, "ask", 0) > 0 and getattr(tick, "bid", 0) > 0:
                pip = get_pip_size(pair)
                spread_map[pair] = round(max(0.0, (float(tick.ask) - float(tick.bid)) / pip), 1)
        except Exception as exc:
            print(f"[ERREUR] Spread {pair} : {exc}")
            spread_map[pair] = None
    return spread_map


def rebuild_and_persist_dashboard_locked() -> str:
    html = render_dashboard_html(
        LATEST_RESULTS,
        LATEST_MT5_OK,
        LATEST_UPDATED_AT,
        LATEST_SR,
        LATEST_SPREAD,
        ACTIVE_PAIRS,
    )
    LATEST_HTML_REF = html
    write_dashboard_atomically(html)
    return LATEST_HTML_REF


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        global LATEST_HTML
        path_only = self.path.split("?", 1)[0]
        if path_only in ("/", "/index.html", "/forex_dashboard.html"):
            with STATE_LOCK:
                html_str = LATEST_HTML
            if not html_str:
                html_str = "<!doctype html><html><body>Chargement...</body></html>"
            body = html_str.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path_only == "/api/pairs":
            with STATE_LOCK:
                pairs_copy = list(ACTIVE_PAIRS)
            self._send_json(200, {"ok": True, "pairs": pairs_copy, "maxPairs": MAX_ACTIVE_PAIRS})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        global ACTIVE_PAIRS, LATEST_HTML, LATEST_MT5_OK, LATEST_UPDATED_AT
        path_only = self.path.split("?", 1)[0]
        if path_only != "/api/pairs":
            self._send_json(404, {"ok": False, "error": "Route inconnue"})
            return

        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_len = 0
        raw_body = self.rfile.read(max(0, min(content_len, 65536))) if content_len > 0 else b"{}"
        try:
            req = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "JSON invalide"})
            return

        action = str(req.get("action", "")).strip().lower()
        symbol = normalize_symbol(str(req.get("symbol", "")))

        if action == "remove":
            with STATE_LOCK:
                if len(ACTIVE_PAIRS) <= 1:
                    self._send_json(400, {"ok": False, "error": "Impossible de supprimer la dernière paire active."})
                    return
                if symbol not in ACTIVE_PAIRS:
                    self._send_json(404, {"ok": False, "error": f"Paire introuvable : {symbol}"})
                    return
                ACTIVE_PAIRS = [p for p in ACTIVE_PAIRS if p != symbol]
                LATEST_RESULTS.pop(symbol, None)
                LATEST_SR.pop(symbol, None)
                LATEST_SPREAD.pop(symbol, None)
                save_pairs_config(ACTIVE_PAIRS)
                LATEST_UPDATED_AT = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                LATEST_HTML = rebuild_and_persist_dashboard_locked()
                pairs_copy = list(ACTIVE_PAIRS)
            print(f"[PAIRES] Paire supprimée : {symbol} -> {pairs_copy}")
            self._send_json(200, {"ok": True, "action": "remove", "symbol": symbol, "pairs": pairs_copy})
            return

        if action == "add":
            if not symbol or not is_valid_trading_symbol(symbol):
                self._send_json(400, {"ok": False, "error": "Symbole invalide (ex: EURJPYm ou XAUUSDm)."})
                return
            with STATE_LOCK:
                if len(ACTIVE_PAIRS) >= MAX_ACTIVE_PAIRS:
                    self._send_json(400, {"ok": False, "error": f"Limite atteinte ({MAX_ACTIVE_PAIRS} paires max)."})
                    return
                if symbol in ACTIVE_PAIRS:
                    self._send_json(400, {"ok": False, "error": f"{symbol} est déjà affiché."})
                    return

            # Vérifier dans MetaTrader 5 si connecté
            mt5_ready = ensure_mt5_connected([symbol])
            if mt5_ready and mt5 is not None:
                selected_ok = mt5.symbol_select(symbol, True)
                sym_info = mt5.symbol_info(symbol)
                if not selected_ok or sym_info is None:
                    self._send_json(
                        400,
                        {"ok": False, "error": f"Symbole introuvable dans MetaTrader 5 : {symbol}"},
                    )
                    return

            # Calcul immédiat des 6 timeframes + S/R + Spread avant de recharger le navigateur
            new_tf_results: Dict[str, Optional[Dict[str, Any]]] = {}
            new_sr: Optional[Dict[str, Any]] = None
            new_spread: Optional[float] = None
            if mt5_ready:
                for tf in TIMEFRAMES:
                    try:
                        new_tf_results[tf] = analyze_pair_timeframe(symbol, tf)
                    except Exception as exc:
                        print(f"[ERREUR] Calcul {symbol} {tf} : {exc}")
                        new_tf_results[tf] = None
                new_sr = compute_sr_map([symbol]).get(symbol)
                new_spread = compute_spread_map([symbol]).get(symbol)

            with STATE_LOCK:
                if symbol not in ACTIVE_PAIRS:
                    ACTIVE_PAIRS.append(symbol)
                LATEST_RESULTS[symbol] = new_tf_results
                LATEST_SR[symbol] = new_sr
                LATEST_SPREAD[symbol] = new_spread
                LATEST_MT5_OK = mt5_ready
                save_pairs_config(ACTIVE_PAIRS)
                LATEST_UPDATED_AT = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                LATEST_HTML = rebuild_and_persist_dashboard_locked()
                pairs_copy = list(ACTIVE_PAIRS)
            print(f"[PAIRES] Paire ajoutée : {symbol} -> {pairs_copy}")
            self._send_json(200, {"ok": True, "action": "add", "symbol": symbol, "pairs": pairs_copy})
            return

        self._send_json(400, {"ok": False, "error": "Action invalide (attendu : add ou remove)."})


def start_local_http_server() -> Tuple[Optional[ThreadingHTTPServer], Optional[int]]:
    for port in range(HTTP_PORT_START, HTTP_PORT_END + 1):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), DashboardRequestHandler)
            srv.daemon_threads = True
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            return srv, port
        except OSError:
            continue
    return None, None


def main() -> None:
    global HTTP_SERVER, LATEST_MT5_OK, LATEST_UPDATED_AT, LATEST_HTML
    print("=== Forex Agent Dashboard (Exness MT5) ===")
    print(f"Serveur MT5 cible : {MT5_SERVER}")
    print(f"Fichier dashboard : {DASHBOARD_HTML_PATH}")
    print(f"Paires actives    : {', '.join(ACTIVE_PAIRS)}")

    now_sec = int(time.time())
    targets = {tf: get_next_target_epoch_sec(tf, now_sec) for tf in TIMEFRAMES}

    # Calcul initial complet des 6 timeframes
    with STATE_LOCK:
        initial_pairs = list(ACTIVE_PAIRS)
    mt5_ok = ensure_mt5_connected(initial_pairs)
    init_results: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {p: {} for p in initial_pairs}
    init_sr: Dict[str, Optional[Dict[str, Any]]] = {p: None for p in initial_pairs}
    init_spread: Dict[str, Optional[float]] = {p: None for p in initial_pairs}

    if mt5_ok:
        for pair in initial_pairs:
            for tf in TIMEFRAMES:
                try:
                    init_results[pair][tf] = analyze_pair_timeframe(pair, tf)
                except Exception as exc:
                    print(f"[ERREUR] Calcul {pair} {tf} : {exc}")
                    init_results[pair][tf] = None
        init_sr = compute_sr_map(initial_pairs)
        init_spread = compute_spread_map(initial_pairs)
    else:
        print("[AVERTISSEMENT] MetaTrader 5 injoignable -> affichage WAIT partout.")

    with STATE_LOCK:
        for pair in initial_pairs:
            if pair in ACTIVE_PAIRS:
                LATEST_RESULTS[pair] = init_results.get(pair, {})
                LATEST_SR[pair] = init_sr.get(pair)
                LATEST_SPREAD[pair] = init_spread.get(pair)
        LATEST_MT5_OK = mt5_ok
        LATEST_UPDATED_AT = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        LATEST_HTML = rebuild_and_persist_dashboard_locked()

    srv, http_port = start_local_http_server()
    HTTP_SERVER = srv
    if srv is not None and http_port is not None:
        url = f"http://127.0.0.1:{http_port}/"
        print(f"[SERVEUR LOCAL] Dashboard interactif actif sur : {url}")
    else:
        url = DASHBOARD_HTML_PATH.resolve().as_uri()
        print(f"[AVERTISSEMENT] Ports {HTTP_PORT_START}-{HTTP_PORT_END} occupés, repli sur fichier : {url}")

    print(f"[NAVIGATEUR] Ouverture automatique : {url}")
    webbrowser.open(url)

    try:
        while RUNNING:
            time.sleep(0.25)
            cur_sec = int(time.time())
            due_tfs = [tf for tf in TIMEFRAMES if cur_sec >= targets[tf]]
            if not due_tfs:
                continue

            for tf in due_tfs:
                targets[tf] = get_next_target_epoch_sec(tf, cur_sec)

            with STATE_LOCK:
                cycle_pairs = list(ACTIVE_PAIRS)

            mt5_ok = ensure_mt5_connected(cycle_pairs)
            cycle_updates: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {p: {} for p in cycle_pairs}
            cycle_sr: Dict[str, Optional[Dict[str, Any]]] = {p: None for p in cycle_pairs}
            cycle_spread: Dict[str, Optional[float]] = {p: None for p in cycle_pairs}

            if mt5_ok:
                for pair in cycle_pairs:
                    for tf in due_tfs:
                        try:
                            cycle_updates[pair][tf] = analyze_pair_timeframe(pair, tf)
                        except Exception as exc:
                            print(f"[ERREUR] Calcul {pair} {tf} : {exc}")
                            cycle_updates[pair][tf] = None
                cycle_sr = compute_sr_map(cycle_pairs)
                cycle_spread = compute_spread_map(cycle_pairs)

            updated_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            with STATE_LOCK:
                if mt5_ok:
                    for pair in cycle_pairs:
                        if pair in ACTIVE_PAIRS:
                            LATEST_RESULTS.setdefault(pair, {}).update(cycle_updates.get(pair, {}))
                            LATEST_SR[pair] = cycle_sr.get(pair)
                            LATEST_SPREAD[pair] = cycle_spread.get(pair)
                LATEST_MT5_OK = mt5_ok
                LATEST_UPDATED_AT = updated_str
                LATEST_HTML = rebuild_and_persist_dashboard_locked()
            print(f"[CYCLE] MAJ {', '.join(due_tfs)} effectuée à {updated_str} (MT5={'OK' if mt5_ok else 'WAIT'})")
    finally:
        if HTTP_SERVER is not None:
            try:
                HTTP_SERVER.shutdown()
                HTTP_SERVER.server_close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
