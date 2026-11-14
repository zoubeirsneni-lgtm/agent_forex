#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forex Agent Dashboard - Agent autonome Windows 10 + MetaTrader 5 (Exness-MT5Trial16)
Surveillance temps réel de 4 paires (EURUSDm, GBPUSDm, USDJPYm, AUDUSDm)
sur 6 timeframes (30s, 1m, 3m, 5m, 10m, 15m) avec 8 indicateurs techniques.
"""

import json
import os
import signal
import sys
import time
import webbrowser
from datetime import datetime, timedelta
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

MT5_SERVER = "Exness-MT5Trial16"
PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"]
TIMEFRAMES = ["30s", "1m", "3m", "5m", "10m", "15m"]

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


def handle_sigint(signum, frame):
    global RUNNING
    RUNNING = False
    print("\n[ARRET] Interruption Ctrl+C détectée. Fermeture propre de MetaTrader 5...")
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
def ensure_mt5_connected() -> bool:
    if mt5 is None:
        return False
    info = mt5.terminal_info()
    if info is not None and mt5.account_info() is not None:
        return True
    if not mt5.initialize():
        return False
    acct = mt5.account_info()
    if acct is None:
        return False
    if acct.server != MT5_SERVER:
        print(f"[INFO] Serveur MT5 actif : {acct.server} (attendu : {MT5_SERVER})")
    for sym in PAIRS:
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
        df = fetch_mt5_rates(symbol, tf_map[tf], 140)

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

    digits = 3 if symbol == "USDJPYm" else 5
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
        "atr_ratio": atr_ratio,
        "vol_ratio": vol_ratio,
        "price": c_now,
        "zone_label": zone_label,
        "pivot_htf": cfg["pivot_htf"],
        "indicators": indicators,
        "price_series": price_series,
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
    pip = 0.01 if symbol == "USDJPYm" else 0.0001
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
) -> str:
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for pair in PAIRS:
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
                    "atr_ratio": 1.0,
                    "vol_ratio": 1.0,
                    "price": None,
                    "zone_label": default_zone_label,
                    "pivot_htf": cfg["pivot_htf"],
                    "indicators": [],
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
                    "atr_ratio": row.get("atr_ratio", 1.0),
                    "vol_ratio": row.get("vol_ratio", 1.0),
                    "price": row.get("price"),
                    "zone_label": row.get("zone_label", default_zone_label),
                    "pivot_htf": row.get("pivot_htf", cfg["pivot_htf"]),
                    "indicators": row.get("indicators", []),
                })
        payload[pair] = rows

    price_payload: Dict[str, List[Dict[str, Any]]] = {}
    for pair in PAIRS:
        row_30s = results.get(pair, {}).get("30s")
        if mt5_ok and row_30s and isinstance(row_30s.get("price_series"), list):
            price_payload[pair] = row_30s["price_series"]
        else:
            price_payload[pair] = []

    sr_payload: Dict[str, Optional[Dict[str, Any]]] = {}
    spread_payload: Dict[str, Optional[float]] = {}
    for pair in PAIRS:
        sr_payload[pair] = (sr_by_pair or {}).get(pair) if mt5_ok else None
        raw_sp = (spread_by_pair or {}).get(pair) if mt5_ok else None
        spread_payload[pair] = round(float(raw_sp), 1) if raw_sp is not None else None

    data_json = json.dumps(payload, ensure_ascii=False)
    price_json = json.dumps(price_payload, ensure_ascii=False)
    sr_json = json.dumps(sr_payload, ensure_ascii=False)
    spread_json = json.dumps(spread_payload, ensure_ascii=False)
    updated_json = json.dumps(updated_at, ensure_ascii=False)

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
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }}
    .header-title {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #ffffff;
      white-space: nowrap;
      flex-shrink: 0;
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
    .live-clock {{
      font-family: var(--font-mono);
      font-size: 20px;
      font-weight: 700;
      color: #e2e8f0;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .pair-label {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 20px;
      border-radius: 12px;
      border: 1px solid #1e2633;
      background-color: #0f131a;
      color: #cbd5e1;
      font-family: var(--font-mono);
      font-weight: 700;
      font-size: 15px;
      cursor: pointer;
      user-select: none;
      transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }}
    .pair-label:hover {{
      border-color: #475569;
      color: #ffffff;
    }}
    .pair-label.active {{
      border-color: #10b981;
      background-color: #052e1f50;
      color: #6ee7b7;
    }}
    .pair-label input {{
      width: 16px;
      height: 16px;
      accent-color: #10b981;
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
      <h1 class="header-title">Forex Agent Dashboard</h1>
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
      <div class="live-clock" id="liveClock" aria-label="Heure actuelle"></div>
    </div>

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
    const PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"];
    const TIMEFRAMES = ["30s", "1m", "3m", "5m", "10m", "15m"];
    const STORAGE_PAIR = "forex_agent_selected_pair";
    const STORAGE_TF = "forex_agent_selected_tf";
    const STORAGE_SOUND = "forex_agent_sound_enabled";
    const STORAGE_HISTORY = "forex_agent_setup_history";
    const STORAGE_SIGS = "forex_agent_last_setup_sigs";
    const STORAGE_SCROLL_Y = "forex_agent_scroll_y";

    let selectedPair = localStorage.getItem(STORAGE_PAIR);
    if (!PAIRS.includes(selectedPair)) selectedPair = "EURUSDm";
    let selectedTfDetail = localStorage.getItem(STORAGE_TF);
    if (!TIMEFRAMES.includes(selectedTfDetail)) selectedTfDetail = "1m";
    let soundEnabled = localStorage.getItem(STORAGE_SOUND) !== "0";

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
      renderTable();
      renderDetails();
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

    function renderPairs() {{
      const wrap = document.getElementById("pairSelector");
      wrap.innerHTML = "";
      PAIRS.forEach(p => {{
        const setup = evaluatePairSetup(DATA[p] || []);
        const lbl = document.createElement("label");
        lbl.className = "pair-label" + (p === selectedPair ? " active" : "");
        const inp = document.createElement("input");
        inp.type = "radio";
        inp.name = "pair";
        inp.value = p;
        inp.checked = (p === selectedPair);
        inp.addEventListener("change", () => selectPairAndRender(p));
        lbl.appendChild(inp);
        lbl.appendChild(document.createTextNode(p));
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
        wrap.appendChild(lbl);
      }});
    }}

    function renderBanner() {{
      const banner = document.getElementById("statusBanner");
      const rows = DATA[selectedPair] || [];
      const sr = SR_DATA[selectedPair] || null;
      const spreadVal = typeof SPREAD_DATA[selectedPair] === "number" ? SPREAD_DATA[selectedPair] : null;
      const digits = selectedPair === "USDJPYm" ? 3 : 5;
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

      if (isWait) {{
        setupVal.className = "tone-warn";
        setupVal.textContent = "En attente des données MT5";
        marketVal.className = "tone-warn";
        marketVal.textContent = "WAIT";
        leftGroup.append(setupLbl, sep1, setupVal);
        rightGroup.append(marketLbl, sep2, marketVal);
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

      topRow.append(leftGroup, rightGroup);
      banner.appendChild(topRow);

      // Deuxième ligne : Support / Résistance & Alerte de prudence
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
      if (!sr) {{
        srRight.className = "tone-subtle";
        srRight.textContent = "En attente des niveaux S/R";
      }} else if (sr.proximityAlert === "NEAR_BOTH") {{
        srRight.className = "tone-warn";
        srRight.textContent = "Compression entre Support et Résistance · Prudence";
      }} else if (sr.proximityAlert === "NEAR_RESISTANCE" && sr.resistance) {{
        srRight.className = "tone-warn";
        srRight.textContent = "Prudence ACHAT · Proche Résistance (" + sr.resistance.distancePips.toFixed(1) + " pips)";
      }} else if (sr.proximityAlert === "NEAR_SUPPORT" && sr.support) {{
        srRight.className = "tone-warn";
        srRight.textContent = "Prudence VENTE · Proche Support (" + sr.support.distancePips.toFixed(1) + " pips)";
      }} else {{
        srRight.className = "tone-subtle";
        srRight.textContent = "Zone libre entre Support et Résistance";
      }}

      srRow.append(srLeft, srRight);
      banner.appendChild(srRow);
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

      const digits = selectedPair === "USDJPYm" ? 3 : 5;
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
      const padL = digits === 3 ? 64 : 74;
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
      const pip = selectedPair === "USDJPYm" ? 0.01 : 0.0001;
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
      header.appendChild(titleWrap);

      if (entries.length > 0) {{
        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "history-clear-btn";
        clearBtn.textContent = "Effacer";
        clearBtn.addEventListener("click", () => {{
          localStorage.removeItem(STORAGE_HISTORY);
          renderHistory([]);
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
      thead.innerHTML = "<tr><th>Heure</th><th>Paire</th><th>TF</th><th>Sens</th><th>Prix</th><th>Spread</th><th>Contexte S/R</th></tr>";
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      entries.forEach(item => {{
        const tr = document.createElement("tr");
        tr.addEventListener("click", () => selectPairAndRender(item.pair));
        const d = item.pair === "USDJPYm" ? 3 : 5;

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

        const tdSr = document.createElement("td");
        tdSr.style.color = "#94a3b8";
        tdSr.textContent = item.srNote || "—";

        tr.append(tdTime, tdPair, tdTf, tdDir, tdPrice, tdSpread, tdSr);
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
      const nowTime = fmtClockHHMMSS(new Date());

      PAIRS.forEach(p => {{
        const rows = DATA[p] || [];
        if (rows.length === 0 || rows.every(r => r.direction === "WAIT")) return;
        const setup = evaluatePairSetup(rows);
        const sig = (setup.status === "READY_BUY" || setup.status === "READY_SELL") && setup.direction && setup.triggerTf
          ? setup.direction + ":" + setup.triggerTf
          : "NONE";
        if (sig !== "NONE" && prevSigs[p] !== sig && setup.triggerPrice !== null) {{
          newEntries.push({{
            id: String(Date.now()) + "-" + p,
            time: nowTime,
            pair: p,
            timeframe: setup.triggerTf,
            direction: setup.direction,
            price: setup.triggerPrice,
            spreadPips: typeof SPREAD_DATA[p] === "number" ? SPREAD_DATA[p] : null,
            srNote: formatSrNote(SR_DATA[p] || null),
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
      if (newEntries.length > 0) {{
        history = newEntries.concat(history).slice(0, 10);
        localStorage.setItem(STORAGE_HISTORY, JSON.stringify(history));
        if (soundEnabled) {{
          playSetupChime(newEntries[0].direction);
        }}
      }}
      renderHistory(history);
    }}

    renderSoundButton();
    renderPairs();
    renderBanner();
    renderTable();
    renderDetails();
    renderChart();
    processSetupsAndRenderHistory();
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


def compute_sr_map() -> Dict[str, Optional[Dict[str, Any]]]:
    sr_map: Dict[str, Optional[Dict[str, Any]]] = {p: None for p in PAIRS}
    for pair in PAIRS:
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


def compute_spread_map() -> Dict[str, Optional[float]]:
    spread_map: Dict[str, Optional[float]] = {p: None for p in PAIRS}
    if mt5 is None:
        return spread_map
    for pair in PAIRS:
        try:
            tick = mt5.symbol_info_tick(pair)
            if tick is not None and getattr(tick, "ask", 0) > 0 and getattr(tick, "bid", 0) > 0:
                pip = 0.01 if pair == "USDJPYm" else 0.0001
                spread_map[pair] = round(max(0.0, (float(tick.ask) - float(tick.bid)) / pip), 1)
        except Exception as exc:
            print(f"[ERREUR] Spread {pair} : {exc}")
            spread_map[pair] = None
    return spread_map


def main() -> None:
    print("=== Forex Agent Dashboard (Exness MT5) ===")
    print(f"Serveur MT5 cible : {MT5_SERVER}")
    print(f"Fichier dashboard : {DASHBOARD_HTML_PATH}")

    now_sec = int(time.time())
    targets = {tf: get_next_target_epoch_sec(tf, now_sec) for tf in TIMEFRAMES}
    results: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {p: {} for p in PAIRS}
    sr_by_pair: Dict[str, Optional[Dict[str, Any]]] = {p: None for p in PAIRS}
    spread_by_pair: Dict[str, Optional[float]] = {p: None for p in PAIRS}

    # Calcul initial complet des 6 timeframes
    mt5_ok = ensure_mt5_connected()
    if mt5_ok:
        for pair in PAIRS:
            for tf in TIMEFRAMES:
                try:
                    results[pair][tf] = analyze_pair_timeframe(pair, tf)
                except Exception as exc:
                    print(f"[ERREUR] Calcul {pair} {tf} : {exc}")
                    results[pair][tf] = None
        sr_by_pair = compute_sr_map()
        spread_by_pair = compute_spread_map()
    else:
        print("[AVERTISSEMENT] MetaTrader 5 injoignable -> affichage WAIT partout.")

    updated_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    write_dashboard_atomically(
        render_dashboard_html(results, mt5_ok, updated_str, sr_by_pair, spread_by_pair)
    )
    url = DASHBOARD_HTML_PATH.resolve().as_uri()
    print(f"[NAVIGATEUR] Ouverture automatique : {url}")
    webbrowser.open(url)

    while RUNNING:
        time.sleep(0.25)
        cur_sec = int(time.time())
        due_tfs = [tf for tf in TIMEFRAMES if cur_sec >= targets[tf]]
        if not due_tfs:
            continue

        for tf in due_tfs:
            targets[tf] = get_next_target_epoch_sec(tf, cur_sec)

        mt5_ok = ensure_mt5_connected()
        if mt5_ok:
            for pair in PAIRS:
                for tf in due_tfs:
                    try:
                        results[pair][tf] = analyze_pair_timeframe(pair, tf)
                    except Exception as exc:
                        print(f"[ERREUR] Calcul {pair} {tf} : {exc}")
                        results[pair][tf] = None
            sr_by_pair = compute_sr_map()
            spread_by_pair = compute_spread_map()

        updated_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        write_dashboard_atomically(
            render_dashboard_html(results, mt5_ok, updated_str, sr_by_pair, spread_by_pair)
        )
        print(f"[CYCLE] MAJ {', '.join(due_tfs)} effectuée à {updated_str} (MT5={'OK' if mt5_ok else 'WAIT'})")


if __name__ == "__main__":
    main()
