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
            row = results.get(pair, {}).get(tf)
            if not mt5_ok or row is None:
                rows.append({
                    "pair": pair,
                    "timeframe": tf,
                    "direction": "WAIT",
                    "signal_label": "WAIT",
                    "confluence_label": "WAIT",
                })
            else:
                rows.append({
                    "pair": pair,
                    "timeframe": tf,
                    "direction": row["direction"],
                    "signal_label": row["signal_label"],
                    "confluence_label": row["confluence_label"],
                })
        payload[pair] = rows

    data_json = json.dumps(payload, ensure_ascii=False)
    updated_json = json.dumps(updated_at, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
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
      transition: background-color 0.15s ease, border-color 0.15s ease;
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
    .maj-cell {{ font-family: Consolas, monospace; font-size: 20px; font-weight: 700; color: #cbd5e1; }}
    .footer {{ margin-top: 16px; color: #94a3b8; font-size: 14px; font-family: Consolas, monospace; }}
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
            <th>Prochaine MAJ</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <div class="footer" id="footerTime"></div>
  </div>

  <script>
    const DATA = {data_json};
    const UPDATED_AT = {updated_json};
    const PAIRS = ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"];
    const STORAGE_PAIR = "forex_agent_selected_pair";

    let selectedPair = localStorage.getItem(STORAGE_PAIR);
    if (!PAIRS.includes(selectedPair)) selectedPair = "EURUSDm";

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
    }}

    renderPairs();
    renderTable();

    setInterval(() => {{
      const nowSec = Math.floor(Date.now() / 1000);
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
