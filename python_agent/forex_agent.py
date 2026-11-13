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
from typing import Any, Dict, List, Optional

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
        "ema_short": 5, "ema_long": 13,
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
        "ema_short": 13, "ema_long": 34,
        "bb_period": 20, "bb_std": 2.0,
        "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "stoch_k": 14, "stoch_smooth": 3, "stoch_d": 3,
        "atr_period": 14,
        "vol_ma": 20,
        "pivot_htf": "H4",
    },
    "10m": {
        "zone": 3,
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
        "zone": 4,
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
# CALCUL DES 8 INDICATEURS TECHNIQUES (VOTE STRICT +1 / -1)
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


def compute_atr(df: pd.DataFrame, period: int) -> float:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr_series.iloc[-1])


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

    # 1. EMA
    ema_s = float(close.ewm(span=cfg["ema_short"], adjust=False).mean().iloc[-1])
    ema_l = float(close.ewm(span=cfg["ema_long"], adjust=False).mean().iloc[-1])
    v_ema = 1 if ema_s > ema_l else -1

    # 2. Bollinger Bands
    bb_mid = float(close.rolling(cfg["bb_period"]).mean().iloc[-1])
    bb_std_val = float(close.rolling(cfg["bb_period"]).std(ddof=0).iloc[-1])
    bb_upper = bb_mid + cfg["bb_std"] * bb_std_val
    bb_lower = bb_mid - cfg["bb_std"] * bb_std_val
    v_bb = 1 if c_now > bb_mid else -1

    # 3. RSI
    rsi_val = compute_rsi(close, cfg["rsi_period"])
    v_rsi = 1 if rsi_val >= 50.0 else -1

    # 4. MACD
    ema_f = close.ewm(span=cfg["macd_fast"], adjust=False).mean()
    ema_sl = close.ewm(span=cfg["macd_slow"], adjust=False).mean()
    macd_line = ema_f - ema_sl
    sig_line = macd_line.ewm(span=cfg["macd_signal"], adjust=False).mean()
    macd_hist = float((macd_line - sig_line).iloc[-1])
    v_macd = 1 if macd_hist > 0 else -1

    # 5. Stochastic
    lowest_low = low.rolling(cfg["stoch_k"]).min()
    highest_high = high.rolling(cfg["stoch_k"]).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    raw_k = (100.0 * (close - lowest_low) / denom).fillna(50.0)
    k_line = raw_k.rolling(cfg["stoch_smooth"]).mean()
    d_line = k_line.rolling(cfg["stoch_d"]).mean()
    k_val = float(k_line.iloc[-1])
    d_val = float(d_line.iloc[-1])
    v_stoch = 1 if k_val > d_val else -1

    # 6. ATR
    atr_val = compute_atr(df, cfg["atr_period"])
    if c_now > c_prev + atr_val:
        v_atr = 1
    elif c_now < c_prev - atr_val:
        v_atr = -1
    else:
        v_atr = 1 if c_now >= c_prev else -1

    # 7. Tick Volume
    vol_ma = float(vol.rolling(cfg["vol_ma"]).mean().iloc[-1])
    vol_ratio = (float(vol.iloc[-1]) / vol_ma) if vol_ma > 0 else 1.0
    if vol_ratio > 1.0 and c_now > o_now:
        v_vol = 1
    elif vol_ratio > 1.0 and c_now < o_now:
        v_vol = -1
    elif c_now != o_now:
        v_vol = 1 if c_now > o_now else -1
    else:
        v_vol = 1 if c_now >= c_prev else -1

    # 8. Pivot Points
    pivot_p = (htf_bar["high"] + htf_bar["low"] + htf_bar["close"]) / 3.0
    v_pivot = 1 if c_now > pivot_p else -1

    digits = 3 if symbol == "USDJPYm" else 5
    zone_tfs = "30s" if tf == "30s" else ("1m, 3m" if tf in ("1m", "3m") else ("5m, 10m" if tf in ("5m", "10m") else "15m"))
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
            "summary": f"M={bb_mid:.{digits}f} [{bb_lower:.{digits}f}-{bb_upper:.{digits}f}]",
        },
        {
            "name": f"RSI ({cfg['rsi_period']}) [{cfg['rsi_ob']}/{cfg['rsi_os']}]",
            "vote": v_rsi,
            "summary": f"{rsi_val:.1f}",
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
            "summary": f"{atr_val:.{digits}f}",
        },
        {
            "name": f"Tick Volume (MA {cfg['vol_ma']})",
            "vote": v_vol,
            "summary": f"Ratio={vol_ratio:.2f}x",
        },
        {
            "name": f"Pivot Points ({cfg['pivot_htf']})",
            "vote": v_pivot,
            "summary": f"P={pivot_p:.{digits}f}",
        },
    ]

    votes = [v_ema, v_bb, v_rsi, v_macd, v_stoch, v_atr, v_vol, v_pivot]
    buy_count = sum(1 for v in votes if v == 1)
    sell_count = 8 - buy_count
    buy_pct = round((buy_count / 8) * 100)
    sell_pct = round((sell_count / 8) * 100)
    confluence = max(buy_count, sell_count)

    if buy_pct > 50:
        direction = "ACHAT"
        signal_label = f"{buy_pct}% ACHAT"
    elif sell_pct > 50:
        direction = "VENTE"
        signal_label = f"{sell_pct}% VENTE"
    else:
        direction = "NEUTRE"
        signal_label = "50% NEUTRE"

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
        "price": c_now,
        "zone_label": zone_label,
        "pivot_htf": cfg["pivot_htf"],
        "indicators": indicators,
        "price_series": price_series,
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
) -> str:
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for pair in PAIRS:
        rows = []
        for tf in TIMEFRAMES:
            cfg = ZONES[tf]
            zone_tfs = "30s" if tf == "30s" else ("1m, 3m" if tf in ("1m", "3m") else ("5m, 10m" if tf in ("5m", "10m") else "15m"))
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

    data_json = json.dumps(payload, ensure_ascii=False)
    price_json = json.dumps(price_payload, ensure_ascii=False)
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
  </header>

  <main class="main">
    <div class="pairs-row">
      <div class="pairs-bar" id="pairSelector" role="radiogroup" aria-label="Sélection de la paire Forex"></div>
      <div class="live-clock" id="liveClock" aria-label="Heure actuelle"></div>
    </div>

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

    <footer class="footer">
      <span class="footer-time" id="footerTime"></span>
      <span id="footerPair"></span>
    </footer>
  </main>

  <script>
    const DATA = {data_json};
    const PRICE_DATA = {price_json};
    const UPDATED_AT = {updated_json};
    const PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"];
    const STORAGE_PAIR = "forex_agent_selected_pair";

    let selectedPair = localStorage.getItem(STORAGE_PAIR);
    if (!PAIRS.includes(selectedPair)) selectedPair = "EURUSDm";
    let selectedTfDetail = "1m";

    document.getElementById("refreshBtn").addEventListener("click", () => {{
      window.location.reload();
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
      renderTable();
      renderDetails();
    }}

    function renderPairs() {{
      const wrap = document.getElementById("pairSelector");
      wrap.innerHTML = "";
      PAIRS.forEach(p => {{
        const lbl = document.createElement("label");
        lbl.className = "pair-label" + (p === selectedPair ? " active" : "");
        const inp = document.createElement("input");
        inp.type = "radio";
        inp.name = "pair";
        inp.value = p;
        inp.checked = (p === selectedPair);
        inp.addEventListener("change", () => {{
          selectedPair = p;
          localStorage.setItem(STORAGE_PAIR, p);
          renderPairs();
          renderTable();
          renderDetails();
          renderChart();
        }});
        lbl.appendChild(inp);
        lbl.appendChild(document.createTextNode(p));
        wrap.appendChild(lbl);
      }});
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

      const counts = document.createElement("div");
      counts.className = "details-counts";
      counts.textContent = "Achat : " + row.buy_count + "/8 · Vente : " + row.sell_count + "/8";

      header.appendChild(titleWrap);
      header.appendChild(counts);
      panel.appendChild(header);

      const grid = document.createElement("div");
      grid.className = "details-grid";

      row.indicators.forEach(ind => {{
        const isBuy = ind.vote === 1;
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
        badge.className = "ind-badge " + (isBuy ? "ind-badge-buy" : "ind-badge-sell");
        badge.textContent = isBuy ? "+1 ACHAT" : "-1 VENTE";

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

      const priceBadge = document.createElement("div");
      priceBadge.className = "chart-price-badge";
      priceBadge.textContent = latest.toFixed(digits);

      header.appendChild(titleWrap);
      header.appendChild(priceBadge);
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
      const span = maxP - minP || (selectedPair === "USDJPYm" ? 0.01 : 0.0001);
      const minY = minP - span * 0.08;
      const maxY = maxP + span * 0.08;
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

    renderPairs();
    renderTable();
    renderDetails();
    renderChart();
    document.getElementById("liveClock").textContent = fmtClockHHMMSS(new Date());

    setInterval(() => {{
      const nowSec = Math.floor(Date.now() / 1000);
      document.getElementById("liveClock").textContent = fmtClockHHMMSS(new Date(nowSec * 1000));
      document.querySelectorAll("[data-tf]").forEach(el => {{
        const tf = el.dataset.tf;
        const target = getNextTargetSec(tf, nowSec);
        el.textContent = fmtMmSs(target - nowSec);
      }});
      if (nowSec % 30 === 26 || nowSec % 60 === 56) {{
        window.location.reload();
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


def main() -> None:
    print("=== Forex Agent Dashboard (Exness MT5) ===")
    print(f"Serveur MT5 cible : {MT5_SERVER}")
    print(f"Fichier dashboard : {DASHBOARD_HTML_PATH}")

    now_sec = int(time.time())
    targets = {tf: get_next_target_epoch_sec(tf, now_sec) for tf in TIMEFRAMES}
    results: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {p: {} for p in PAIRS}

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
    else:
        print("[AVERTISSEMENT] MetaTrader 5 injoignable -> affichage WAIT partout.")

    updated_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    write_dashboard_atomically(render_dashboard_html(results, mt5_ok, updated_str))
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

        updated_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        write_dashboard_atomically(render_dashboard_html(results, mt5_ok, updated_str))
        print(f"[CYCLE] MAJ {', '.join(due_tfs)} effectuée à {updated_str} (MT5={'OK' if mt5_ok else 'WAIT'})")


if __name__ == "__main__":
    main()
