#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forex Agent Dashboard - Agent autonome Windows 10 + MetaTrader 5 (Exness-MT5Trial16)
Surveillance temps réel de 4 paires (EURUSDm, GBPUSDm, USDJPYm, AUDUSDm)
sur 7 timeframes (15s, 30s, 1m, 3m, 5m, 10m, 15m) avec 8 indicateurs techniques
et validation LLM restrictive via routeur local http://127.0.0.1:31415/v1/messages.
"""

import json
import os
import re
import signal
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

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
TIMEFRAMES = ["15s", "30s", "1m", "3m", "5m", "10m", "15m"]

REFRESH_SECONDS = 15

LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:31415/v1/messages")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "freellmapi-XXXXX")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-3-5-sonnet-20241022")
LLM_CACHE_TTL_SEC = 60
LLM_429_COOLDOWN_SEC = 60

# Paramètres stricts par zone (CRUCIAL)
ZONES: Dict[str, Dict[str, Any]] = {
    "15s": {
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
    """Construit des bougies 15s ou 30s à partir des ticks MT5."""
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
    df = pd.DataFrame(rates)
    return df


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
    if tf == "15s":
        df = fetch_subminute_candles(symbol, 15, 140)
    elif tf == "30s":
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
    v_stoch = 1 if float(k_line.iloc[-1]) > float(d_line.iloc[-1]) else -1

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

    return {
        "pair": symbol,
        "timeframe": tf,
        "direction": direction,
        "signal_label": signal_label,
        "confluence": confluence,
        "confluence_label": f"{confluence}/8",
        "buy_count": buy_count,
        "sell_count": sell_count,
        "price": c_now,
    }


# ==============================================================================
# GESTIONNAIRE LLM RESTRICTIF
# ==============================================================================
class RestrictiveLlmManager:
    def __init__(self):
        # Clé (pair, tf) -> dict
        self.cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.last_signal_called: Dict[Tuple[str, str], str] = {}
        self.cooldown_until: float = 0.0

    def evaluate_cycle(self, results: Dict[str, Dict[str, Optional[Dict[str, Any]]]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """
        Règles strictes :
        - UNIQUEMENT EURUSDm
        - UNIQUEMENT 1m et 3m
        - UNIQUEMENT confluence >= 6/8
        - UNIQUEMENT si le signal a changé depuis le dernier appel réussi
        - MAXIMUM 1 appel LLM par cycle de 15s
        - Cache verdict 60s minimum
        - Si 429 : afficher ERREUR LLM pendant 60s sans réessayer
        """
        now = time.time()
        verdicts: Dict[Tuple[str, str], Dict[str, Any]] = {}
        call_made_this_cycle = False

        for pair in PAIRS:
            for tf in TIMEFRAMES:
                row = results.get(pair, {}).get(tf)
                if row is None:
                    verdicts[(pair, tf)] = {"state": "WAIT", "label": "WAIT"}
                    continue

                if pair != "EURUSDm" or tf not in ("1m", "3m") or row["confluence"] < 6:
                    verdicts[(pair, tf)] = {"state": "NON_REQUIS", "label": "NON_REQUIS"}
                    continue

                key = (pair, tf)
                cached = self.cache.get(key)
                sig = row["signal_label"]

                # Vérifier cache valide (60s minimum) et signal inchangé
                if cached and now < cached["expires_at"]:
                    verdicts[key] = cached["verdict"]
                    continue

                if self.last_signal_called.get(key) == sig and cached:
                    verdicts[key] = cached["verdict"]
                    continue

                # Rate limit 429 actif ?
                if now < self.cooldown_until:
                    verdicts[key] = {"state": "ERREUR", "label": "ERREUR LLM"}
                    continue

                # Max 1 appel par cycle de 15s
                if call_made_this_cycle:
                    if cached:
                        verdicts[key] = cached["verdict"]
                    else:
                        verdicts[key] = {"state": "EN_COURS", "label": "EN COURS..."}
                    continue

                call_made_this_cycle = True
                verdict, is_429, ok = self._call_llm(row)
                if is_429:
                    self.cooldown_until = now + LLM_429_COOLDOWN_SEC
                    verdicts[key] = {"state": "ERREUR", "label": "ERREUR LLM"}
                elif not ok:
                    verdicts[key] = {"state": "ERREUR", "label": "ERREUR LLM"}
                else:
                    self.last_signal_called[key] = sig
                    self.cache[key] = {
                        "expires_at": now + LLM_CACHE_TTL_SEC,
                        "verdict": verdict,
                    }
                    verdicts[key] = verdict

        return verdicts

    def _call_llm(self, row: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, bool]:
        prompt = (
            f"Analyse ce signal Forex pour validation stricte.\n"
            f"Paire: {row['pair']}\n"
            f"Timeframe: {row['timeframe']}\n"
            f"Signal agent: {row['signal_label']}\n"
            f"Confluence: {row['confluence_label']}\n"
            f"Réponds UNIQUEMENT en JSON strict sur une ligne : "
            f'{{"decision":"CONFIRME"|"REFUSE"|"NEUTRE","raison":"court","confiance":0-100}}'
        )
        headers = {
            "Content-Type": "application/json",
            "x-api-key": LLM_API_KEY,
            "Authorization": f"Bearer {LLM_API_KEY}",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": LLM_MODEL,
            "max_tokens": 120,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            resp = requests.post(LLM_ENDPOINT, headers=headers, json=payload, timeout=8)
            if resp.status_code == 429:
                print("[LLM] Erreur 429 (rate limit) -> pause de 60s.")
                return {}, True, False
            if resp.status_code >= 400:
                print(f"[LLM] Erreur HTTP {resp.status_code}")
                return {}, False, False

            data = resp.json()
            # Extraction compatible Anthropic / OpenAI-like
            text = ""
            if isinstance(data.get("content"), list) and data["content"]:
                text = data["content"][0].get("text", "")
            elif isinstance(data.get("choices"), list) and data["choices"]:
                text = data["choices"][0].get("message", {}).get("content", "")
            else:
                text = json.dumps(data)

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}, False, False
            parsed = json.loads(match.group(0))
            decision = str(parsed.get("decision", "NEUTRE")).upper()
            if decision not in ("CONFIRME", "REFUSE", "NEUTRE"):
                decision = "NEUTRE"
            confiance = max(0, min(100, int(parsed.get("confiance", 50))))

            if decision == "CONFIRME":
                label = f"CONFIRMÉ {confiance}%"
            elif decision == "REFUSE":
                label = f"REFUSÉ {confiance}%"
            else:
                label = f"NEUTRE {confiance}%"

            return {
                "state": decision,
                "decision": decision,
                "confiance": confiance,
                "label": label,
            }, False, True
        except Exception as exc:
            print(f"[LLM] Routeur inaccessible : {exc}")
            return {}, False, False


# ==============================================================================
# GÉNÉRATION HTML AUTONOME (dashboard/forex_dashboard.html)
# ==============================================================================
def render_dashboard_html(
    results: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
    verdicts: Dict[Tuple[str, str], Dict[str, Any]],
    mt5_ok: bool,
    updated_at: str,
) -> str:
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for pair in PAIRS:
        rows = []
        for tf in TIMEFRAMES:
            row = results.get(pair, {}).get(tf)
            v = verdicts.get((pair, tf), {"state": "NON_REQUIS", "label": "NON_REQUIS"})
            if not mt5_ok or row is None:
                rows.append({
                    "pair": pair,
                    "timeframe": tf,
                    "direction": "WAIT",
                    "signal_label": "WAIT",
                    "confluence_label": "WAIT",
                    "llm_state": "WAIT",
                    "llm_label": "WAIT",
                })
            else:
                rows.append({
                    "pair": pair,
                    "timeframe": tf,
                    "direction": row["direction"],
                    "signal_label": row["signal_label"],
                    "confluence_label": row["confluence_label"],
                    "llm_state": v["state"],
                    "llm_label": v["label"],
                })
        payload[pair] = rows

    data_json = json.dumps(payload, ensure_ascii=False)
    updated_json = json.dumps(updated_at, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="refresh" content="15" />
  <title>Forex Agent Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: #07090d;
      color: #f1f5f9;
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 28px 20px;
    }}
    .container {{ width: 100%; max-width: 1080px; }}
    h1 {{ font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 20px; }}
    .pairs {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
    .pair-label {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 12px 22px; border-radius: 10px;
      background: #0f131a; border: 1px solid #1e2633;
      cursor: pointer; font-weight: 700; font-size: 15px;
      transition: all 0.15s ease;
    }}
    .pair-label input {{ accent-color: #10b981; width: 16px; height: 16px; }}
    .pair-label.active {{ background: #13231d; border-color: #10b981; color: #34d399; }}
    .table-wrap {{
      background: #0f131a; border: 1px solid #1e2633;
      border-radius: 14px; overflow: hidden;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{
      text-align: left; padding: 14px 18px;
      font-size: 13px; color: #94a3b8; font-weight: 600;
      border-bottom: 1px solid #1e2633; background: #0b0e14;
    }}
    td {{
      padding: 14px 18px; border-bottom: 1px solid #161d29;
      vertical-align: middle; font-variant-numeric: tabular-nums;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .tf-cell {{ font-family: Consolas, monospace; font-size: 18px; font-weight: 700; color: #e2e8f0; }}
    .sig-btn {{
      display: inline-block; min-width: 190px; text-align: center;
      padding: 10px 18px; border-radius: 10px;
      font-family: Consolas, monospace; font-size: 24px; font-weight: 800;
    }}
    .sig-ACHAT {{ background: #059669; color: #ffffff; }}
    .sig-VENTE {{ background: #dc2626; color: #ffffff; }}
    .sig-NEUTRE {{ background: #334155; color: #e2e8f0; }}
    .sig-WAIT {{ background: #1e293b; color: #fbbf24; }}
    .conf-cell {{ font-family: Consolas, monospace; font-size: 22px; font-weight: 700; color: #f8fafc; }}
    .llm-badge {{
      display: inline-block; padding: 8px 14px; border-radius: 8px;
      font-family: Consolas, monospace; font-size: 14px; font-weight: 700;
    }}
    .llm-CONFIRME {{ background: #059669; color: #ffffff; }}
    .llm-REFUSE {{ background: #dc2626; color: #ffffff; }}
    .llm-NEUTRE {{ background: #ca8a04; color: #ffffff; }}
    .llm-NON_REQUIS {{ background: #334155; color: #cbd5e1; }}
    .llm-EN_COURS {{ background: #475569; color: #f8fafc; animation: pulse 1s infinite; }}
    .llm-ERREUR {{ background: #1f2937; color: #f87171; border: 1px solid #374151; }}
    .llm-WAIT {{ background: #1e293b; color: #fbbf24; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.45; }} }}
    .footer {{ margin-top: 16px; color: #94a3b8; font-size: 14px; font-family: Consolas, monospace; }}

    /* POPUP GÉANT (5x plus grand) */
    .popup-overlay {{
      position: fixed; inset: 0; background: rgba(0, 0, 0, 0.86);
      display: none; align-items: center; justify-content: center;
      z-index: 9999; padding: 24px;
    }}
    .popup-overlay.visible {{ display: flex; }}
    .popup-card {{
      position: relative; width: 100%; max-width: 960px;
      background: #0b0f17; border-radius: 28px;
      padding: 56px 48px; text-align: center;
      border: 8px solid #10b981;
      box-shadow: 0 25px 80px rgba(0, 0, 0, 0.85);
    }}
    .popup-card.vente {{ border-color: #ef4444; }}
    .popup-close {{
      position: absolute; top: 22px; right: 26px;
      width: 56px; height: 56px; border-radius: 14px;
      background: #1e293b; color: #ffffff; border: 1px solid #334155;
      font-size: 28px; font-weight: 800; cursor: pointer;
    }}
    .popup-title {{ font-size: 42px; font-weight: 800; margin-bottom: 28px; }}
    .popup-pair {{ font-size: 64px; font-weight: 800; font-family: Consolas, monospace; margin-bottom: 14px; }}
    .popup-tf {{ font-size: 36px; font-weight: 700; color: #cbd5e1; margin-bottom: 24px; }}
    .popup-signal {{ font-size: 56px; font-weight: 800; font-family: Consolas, monospace; margin-bottom: 18px; }}
    .popup-signal.achat {{ color: #34d399; }}
    .popup-signal.vente {{ color: #f87171; }}
    .popup-conf {{ font-size: 38px; font-weight: 700; margin-bottom: 24px; font-family: Consolas, monospace; }}
    .popup-llm {{
      display: inline-block; padding: 16px 36px; border-radius: 16px;
      font-size: 36px; font-weight: 800; font-family: Consolas, monospace;
      background: #059669; color: #ffffff;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Forex Agent Dashboard</h1>
    <div class="pairs" id="pairSelector"></div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Timeframe</th>
            <th>Signal</th>
            <th>Confluence</th>
            <th>Verdict LLM</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <div class="footer" id="footerTime"></div>
  </div>

  <div class="popup-overlay" id="giantPopup">
    <div class="popup-card" id="popupCard">
      <button class="popup-close" id="popupCloseBtn" aria-label="Fermer">✕</button>
      <div class="popup-title">🔔 SIGNAL CONFIRMÉ</div>
      <div class="popup-pair" id="popupPair"></div>
      <div class="popup-tf" id="popupTf"></div>
      <div class="popup-signal" id="popupSignal"></div>
      <div class="popup-conf" id="popupConf"></div>
      <div class="popup-llm" id="popupLlm"></div>
    </div>
  </div>

  <script>
    const DATA = {data_json};
    const UPDATED_AT = {updated_json};
    const PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"];
    const STORAGE_PAIR = "forex_agent_selected_pair";
    const STORAGE_DISMISSED = "forex_agent_dismissed_signatures";

    let selectedPair = localStorage.getItem(STORAGE_PAIR);
    if (!PAIRS.includes(selectedPair)) selectedPair = "EURUSDm";

    function getDismissed() {{
      try {{ return JSON.parse(localStorage.getItem(STORAGE_DISMISSED) || "[]"); }}
      catch {{ return []; }}
    }}

    function dismissSignature(sig) {{
      const list = getDismissed();
      if (!list.includes(sig)) {{
        list.push(sig);
        localStorage.setItem(STORAGE_DISMISSED, JSON.stringify(list.slice(-50)));
      }}
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
          renderPopup();
        }});
        lbl.appendChild(inp);
        lbl.appendChild(document.createTextNode(p));
        wrap.appendChild(lbl);
      }});
    }}

    function renderTable() {{
      const tbody = document.getElementById("tableBody");
      tbody.innerHTML = "";
      const rows = DATA[selectedPair] || [];
      rows.forEach(r => {{
        const tr = document.createElement("tr");
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
        tdConf.textContent = r.confluence_label;

        const tdLlm = document.createElement("td");
        const llmSpan = document.createElement("span");
        llmSpan.className = "llm-badge llm-" + r.llm_state;
        llmSpan.textContent = r.llm_label;
        tdLlm.appendChild(llmSpan);

        tr.appendChild(tdTf);
        tr.appendChild(tdSig);
        tr.appendChild(tdConf);
        tr.appendChild(tdLlm);
        tbody.appendChild(tr);
      }});
      document.getElementById("footerTime").textContent = "Dernière mise à jour : " + UPDATED_AT;
    }}

    let activePopupSig = null;
    function renderPopup() {{
      const overlay = document.getElementById("giantPopup");
      const rows = DATA[selectedPair] || [];
      const dismissed = getDismissed();
      const match = rows.find(r =>
        r.pair === selectedPair &&
        (r.timeframe === "1m" || r.timeframe === "3m") &&
        r.llm_state === "CONFIRME" &&
        !dismissed.includes(r.pair + "|" + r.timeframe + "|" + r.signal_label + "|CONFIRME")
      );

      if (!match) {{
        activePopupSig = null;
        overlay.classList.remove("visible");
        return;
      }}

      activePopupSig = match.pair + "|" + match.timeframe + "|" + match.signal_label + "|CONFIRME";
      const card = document.getElementById("popupCard");
      card.className = "popup-card " + (match.direction === "VENTE" ? "vente" : "achat");
      document.getElementById("popupPair").textContent = match.pair;
      document.getElementById("popupTf").textContent = "Timeframe : " + match.timeframe;
      const sigEl = document.getElementById("popupSignal");
      sigEl.textContent = match.signal_label;
      sigEl.className = "popup-signal " + (match.direction === "VENTE" ? "vente" : "achat");
      document.getElementById("popupConf").textContent = "Confluence : " + match.confluence_label;
      document.getElementById("popupLlm").textContent = match.llm_label;
      overlay.classList.add("visible");
    }}

    document.getElementById("popupCloseBtn").addEventListener("click", () => {{
      if (activePopupSig) {{
        dismissSignature(activePopupSig);
      }}
      document.getElementById("giantPopup").classList.remove("visible");
    }});

    renderPairs();
    renderTable();
    renderPopup();
  </script>
</body>
</html>
"""


def write_dashboard_atomically(html_content: str) -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = DASHBOARD_DIR / "forex_dashboard.tmp.html"
    tmp_path.write_text(html_content, encoding="utf-8")
    os.replace(tmp_path, DASHBOARD_HTML_PATH)


def sync_to_second_59() -> None:
    now = datetime.now()
    sec = now.second
    if sec == 59:
        return
    wait_sec = 59 - sec
    target = (now + timedelta(seconds=wait_sec)).strftime("%H:%M:%S")
    print(f"[SYNC] Synchronisation au démarrage : attente jusqu'à la 59e seconde ({target}, dans {wait_sec}s)...")
    while RUNNING:
        current = datetime.now()
        if current.second == 59:
            break
        time.sleep(0.25)


def main() -> None:
    print("=== Forex Agent Dashboard (Exness MT5) ===")
    print(f"Serveur MT5 cible : {MT5_SERVER}")
    print(f"Fichier dashboard : {DASHBOARD_HTML_PATH}")

    sync_to_second_59()

    llm_manager = RestrictiveLlmManager()
    browser_opened = False

    while RUNNING:
        cycle_start = time.time()
        mt5_ok = ensure_mt5_connected()
        results: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}

        if mt5_ok:
            for pair in PAIRS:
                results[pair] = {}
                for tf in TIMEFRAMES:
                    try:
                        results[pair][tf] = analyze_pair_timeframe(pair, tf)
                    except Exception as exc:
                        print(f"[ERREUR] Calcul {pair} {tf} : {exc}")
                        results[pair][tf] = None
        else:
            print("[AVERTISSEMENT] MetaTrader 5 injoignable -> affichage WAIT partout.")

        verdicts = llm_manager.evaluate_cycle(results)
        updated_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        html = render_dashboard_html(results, verdicts, mt5_ok, updated_str)
        write_dashboard_atomically(html)

        if not browser_opened:
            browser_opened = True
            url = DASHBOARD_HTML_PATH.resolve().as_uri()
            print(f"[NAVIGATEUR] Ouverture automatique : {url}")
            webbrowser.open(url)

        print(f"[CYCLE] Mise à jour effectuée à {updated_str} (MT5={'OK' if mt5_ok else 'WAIT'})")

        elapsed = time.time() - cycle_start
        sleep_time = max(1.0, REFRESH_SECONDS - elapsed)
        end_wait = time.time() + sleep_time
        while RUNNING and time.time() < end_wait:
            time.sleep(0.25)


if __name__ == "__main__":
    main()
