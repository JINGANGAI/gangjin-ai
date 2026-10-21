# ==============================================================================
# GANGJIN AI TRADER PRO — App (14)
# v13 + 신호 자동 검증(signal_outcomes) 통합
# - 봇 신호 발생 시 5/10/20일 후 자동으로 실제 주가와 비교해 승률 산출
# - 사용자 매매일지(trade_journal) + 봇 신호 검증(signal_outcomes) 이중 추적
# ==============================================================================
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import html
import os
import sqlite3
import logging
import urllib.request
import urllib.parse
import time
import xml.etree.ElementTree as ET
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False


# ==============================================================================
# 1) CONFIG
# ==============================================================================
CFG = {
    "cache": {
        "history": 60, "indices": 60, "top_bar": 60, "market_cap": 3600,
        "fear_greed": 1800, "macro": 300, "gamma": 1800, "scanner": 180,
        "noise_filter": 60, "short_interest": 1800, "gex": 1800,
    },
    "ind": {
        "rsi_period": 14, "rsi_panic": 25.0, "rsi_oversold": 35.0, "rsi_overbought": 70.0,
        "rsi_take_profit": 74.0, "atr_period": 14, "box_period": 20,
        "vol_breakout": 1.5, "vol_exit": 1.4,
    },
    "trail": {
        "leverage_etfs": frozenset({
            "SOXL", "TQQQ", "SQQQ", "SOXS", "TSLL", "NVDL", "MSTU", "MSTX",
            "CONL", "BITX", "UPRO", "TMF", "LABU", "FNGU", "BULZ",
        }),
        "tiers": {
            "mega":  {"min": 200e9, "tight": (4.0, 6.5), "core": (6.0, 9.0)},
            "large": {"min": 10e9,  "tight": (5.0, 7.5), "core": (7.0, 10.5)},
            "mid":   {"min": 2e9,   "tight": (6.5, 9.5), "core": (9.0, 13.5)},
            "small": {"min": 0,     "tight": (8.0, 12.0), "core": (11.5, 17.5)},
        },
        "leverage_tier": {"tight": (7.0, 11.0), "core": (10.0, 16.0)},
        "fallback": {
            "high": {"atr_min": 5.5, "tight": (8.0, 12.0), "core": (11.5, 17.0)},
            "mid":  {"atr_min": 3.5, "tight": (6.0, 9.0),  "core": (8.5, 13.0)},
            "low":  {"atr_min": 0,   "tight": (4.5, 7.0),  "core": (6.5, 9.5)},
        },
    },
    "macro": {
        "nq_strong": 1.0, "es_strong": 0.8, "wti_spike_chg": 2.5, "wti_spike_price": 85.0,
        "wti_stable": 75.0, "tnx_spike_price": 4.5, "tnx_spike_chg": 1.5, "tnx_stable": 4.1,
        "vix_crisis": 23.0, "vix_calm": 18.0,
    },
    "news": {
        "contract": ("contract", "deal", "partnership", "agreement", "award", "hyperscaler",
                     "alliance", "expansion", "capacity", "customer"),
        "earnings_bull": ("beat", "record revenue", "surge", "strong guidance", "profit",
                          "eps beat", "outperform", "upgrade", "buyback"),
        "bad_strict": ("offering", "dilution", "convertible", "lawsuit", "probe", "subpoena",
                       "miss", "downgrade", "slash", "halted", "short seller", "fraud"),
        "cut_bullish": ("rate cut", "cuts rate", "cut rates", "interest rate cut",
                        "price target raised", "dividend"),
        "cut_bearish": ("guidance cut", "cuts guidance", "dividend cut",
                        "job cut", "layoff", "production cut"),
        "geo": ("war", "tariff", "sanction", "inflation", "fed", "rate", "missile",
                "iran", "china", "ban", "export control"),
    },
    "noise": {
        "minor_atr_mult": 1.35, "band_atr_mult": 1.8, "chandelier_atr": 2.8,
        "tight_atr": 2.0, "warn_ratio": 75.0, "confirm_bear": 6.0,
        "confirm_watch": 3.0, "confirm_bull": 5.0,
    },
    "squeeze": {
        "short_pct_high": 20.0, "short_pct_mid": 10.0,
        "dtc_high": 7.0, "dtc_mid": 4.0,
        "squeeze_bonus_max": 10,
    },
    "paths": {"db": "data/portfolio.db", "logs": "data/logs"},
    "usd_krw_fallback": 1380.0,
}

Path(CFG["paths"]["logs"]).mkdir(parents=True, exist_ok=True)
Path(CFG["paths"]["db"]).parent.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# 2) LOGGER
# ==============================================================================
def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("gangjin")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    try:
        fh = RotatingFileHandler(f"{CFG['paths']['logs']}/app.log", maxBytes=5 * 1024 * 1024,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    return logger


LOG = _setup_logger()


# ==============================================================================
# 3) UTILS & CONSTANTS
# ==============================================================================
def render_html(s: str):
    st.markdown("\n".join(l.strip() for l in s.splitlines() if l.strip()), unsafe_allow_html=True)


def safe_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url or "")
        if p.scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return "#"


def safe_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


def compute_wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    g = d.where(d > 0, 0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    l = (-d.where(d < 0, 0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = g / l.replace(0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


SIGNAL_HOLD_LONG   = "🟢 장기 홀딩"
SIGNAL_HOLD_SHORT  = "🟡 단기 대응"
SIGNAL_WATCH       = "🟠 경계 (준비)"
SIGNAL_EXIT        = "🔴 즉시 청산"
SIGNAL_TAKE_PROFIT = "🔵 목표 익절"
SIGNAL_STOP_HIT    = "⚫ 손절선 이탈"

SIGNAL_SEVERITY = {
    SIGNAL_STOP_HIT: 5, SIGNAL_EXIT: 4, SIGNAL_TAKE_PROFIT: 3,
    SIGNAL_WATCH: 2, SIGNAL_HOLD_SHORT: 1, SIGNAL_HOLD_LONG: 0,
}
SIGNAL_BADGE = {
    SIGNAL_STOP_HIT: "badge-red", SIGNAL_EXIT: "badge-red",
    SIGNAL_TAKE_PROFIT: "badge-blue", SIGNAL_WATCH: "badge-yellow",
    SIGNAL_HOLD_SHORT: "badge-indigo", SIGNAL_HOLD_LONG: "badge-green",
}


# ==============================================================================
# 4) PAGE CONFIG & CSS
# ==============================================================================
st.set_page_config(
    page_title="GANGJIN AI TRADER PRO",
    layout="centered",
    page_icon="⚡",
    initial_sidebar_state="collapsed",
)

render_html("""
<meta name="google" content="notranslate">
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Pretendard:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Pretendard', -apple-system, sans-serif; }
.mono { font-family: 'JetBrains Mono', monospace; }
#MainMenu, footer, header {visibility: hidden;}
.block-container { padding-top: 0.8rem; padding-bottom: 2rem; max-width: 800px; }
.stApp { background-color: #080c14; color: #e6edf3; }
div[data-baseweb="input"], div[data-baseweb="textarea"] { background-color: #0f1523 !important; border: 1px solid #1e293b !important; border-radius: 10px !important; color: #ffffff !important; }
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { color: #ffffff !important; font-size: 14px !important; font-weight: 700 !important; }
div[data-baseweb="select"] > div { background-color: #0f1523 !important; border-color: #1e293b !important; color: #ffffff !important; border-radius: 10px !important; }
.glass-card { background: linear-gradient(135deg, rgba(17,24,39,.85), rgba(15,23,42,.65)); border: 1px solid rgba(51,65,85,.5); backdrop-filter: blur(12px); padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(0,0,0,.4); }
.main-hero-card { background: linear-gradient(135deg,#0d1e16,#0a131a 50%,#0c1524); border: 1px solid #1e3a2f; padding: 18px 22px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 8px 32px rgba(16,185,129,.08); }
.verdict-card { background: linear-gradient(135deg,#13221c,#0d1526 55%,#1f1429); border: 2px solid #10b981; padding: 20px 22px; border-radius: 16px; margin-bottom: 16px; box-shadow: 0 8px 35px rgba(16,185,129,.18); }
.master-card { background: linear-gradient(135deg,#2a1b0a,#1a1108); border: 1px solid #f59e0b; padding: 18px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(245,158,11,.25); }
.trailing-card { background: linear-gradient(135deg,#0c192c,#091220); border: 1px solid #38bdf8; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(56,189,248,.15); }
.sentiment-card { background: linear-gradient(135deg,#1e1b4b,#172554); border: 1px solid #6366f1; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(99,102,241,.2); }
.noise-card { background: linear-gradient(135deg,#0f172a,#111827 60%,#0d1f22); border: 1px solid #14b8a6; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(20,184,166,.15); }
.rebal-card { background: linear-gradient(135deg,#1a0f2e,#0f1524 50%,#1a0f2e); border: 1px solid #a855f7; padding: 14px 18px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(168,85,247,.2); }
.journal-card { background: linear-gradient(135deg,#0f2416,#0a131a 50%,#0f2416); border: 1px solid #10b981; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(16,185,129,.15); }
.squeeze-card { background: linear-gradient(135deg,#1a1108,#0d1526 50%,#1a1108); border: 2px solid #f97316; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 25px rgba(249,115,22,.25); }
.signal-card { background: linear-gradient(135deg,#0f172a,#1a1f35 50%,#0f172a); border: 1px solid #6366f1; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(99,102,241,.2); }
.index-wrapper { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.index-card { flex: 1 1 100px; background-color: #0d131f; border: 1px solid #1e293b; padding: 10px 8px; border-radius: 10px; text-align: center; }
.index-name { color: #94a3b8; font-size: 10px; font-weight: 600; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.index-price { font-size: 13px; font-weight: 800; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px; }
.index-change { font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.text-white { color: #fff !important; }
.text-green { color: #10b981 !important; } .text-red { color: #f43f5e !important; }
.text-yellow { color: #f59e0b !important; } .text-blue { color: #3b82f6 !important; }
.text-purple { color: #a855f7 !important; } .text-indigo { color: #818cf8 !important; }
.text-orange { color: #fb923c !important; }
.badge { padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 4px; letter-spacing: 0.3px; }
.badge-green { background: rgba(16,185,129,.15); color: #34d399; border: 1px solid #10b981; }
.badge-red { background: rgba(244,63,94,.15); color: #fb7185; border: 1px solid #f43f5e; }
.badge-yellow { background: rgba(245,158,11,.15); color: #fbbf24; border: 1px solid #f59e0b; }
.badge-blue { background: rgba(59,130,246,.15); color: #60a5fa; border: 1px solid #3b82f6; }
.badge-purple { background: rgba(168,85,247,.15); color: #c084fc; border: 1px solid #a855f7; }
.badge-indigo { background: rgba(99,102,241,.15); color: #a5b4fc; border: 1px solid #6366f1; }
.badge-teal { background: rgba(20,184,166,.15); color: #5eead4; border: 1px solid #14b8a6; }
.badge-orange { background: rgba(249,115,22,.15); color: #fb923c; border: 1px solid #f97316; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #0b111e; padding: 6px; border-radius: 12px; border: 1px solid #1e293b; }
.stTabs [data-baseweb="tab"] { border-radius: 8px; color: #94a3b8; font-weight: 700; padding: 8px 12px; font-size: 12px; }
.stTabs [aria-selected="true"] { background-color: #1e293b !important; color: #fff !important; }
hr { border: none; border-top: 1px solid #1e293b; margin: 14px 0; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.3rem !important; padding-right: 0.3rem !important; max-width: 100% !important; }
    div[style*="grid-template-columns:repeat(4,1fr)"],
    div[style*="grid-template-columns: repeat(4, 1fr)"] { grid-template-columns: repeat(2, 1fr) !important; gap: 6px !important; }
    div[style*="grid-template-columns:repeat(3,1fr)"],
    div[style*="grid-template-columns: repeat(3, 1fr)"] { grid-template-columns: 1fr !important; }
    .index-card { flex: 1 1 45% !important; }
    .stTabs [data-baseweb="tab-list"] { flex-wrap: nowrap !important; overflow-x: auto !important; }
    .stTabs [data-baseweb="tab"] { padding: 6px 8px !important; font-size: 10px !important; white-space: nowrap; }
    .main-hero-card, .verdict-card, .master-card, .trailing-card, .sentiment-card, .noise-card, .rebal-card, .journal-card, .squeeze-card, .signal-card { padding: 12px 14px !important; }
    .main-hero-card > div:nth-child(2) { font-size: 24px !important; }
}
</style>
""")


# ==============================================================================
# 5) LIVE CLOCK HEADER
# ==============================================================================
def render_live_ny_header(btc_price, btc_change, usd_krw):
    btc_color = "#10b981" if btc_change >= 0 else "#f43f5e"
    btc_sign = "▲" if btc_change >= 0 else "▼"
    btc_text = f"{btc_sign} ${btc_price:,.0f}" if btc_price > 0 else "N/A"
    krw_text = f"{usd_krw:,.1f}원" if usd_krw > 0 else "N/A"
    live_clock_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:0;background:transparent;font-family:-apple-system,sans-serif;}}
.header-box{{background:linear-gradient(90deg,#0a0f1d,#111a2e);border:1px solid #1e293b;border-radius:12px;padding:10px 16px;display:flex;justify-content:space-between;align-items:center;gap:10px;box-shadow:0 4px 15px rgba(0,0,0,.3);flex-wrap:wrap;}}
.left-section{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
.clock-title{{font-weight:800;font-size:13px;color:#f8fafc;display:flex;align-items:center;gap:6px;}}
.pulse-dot{{width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 10px #10b981;}}
.clock-display{{font-family:monospace;font-size:15px;font-weight:800;color:#38bdf8;background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.3);padding:3px 10px;border-radius:6px;}}
.status-badge{{font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;}}
.countdown-text{{font-size:12px;color:#94a3b8;font-weight:600;}}
.right-section{{display:flex;align-items:center;gap:14px;font-family:monospace;font-size:13px;flex-wrap:wrap;}}
</style></head><body>
<div class="header-box">
<div class="left-section">
<div class="clock-title"><span class="pulse-dot" id="pulse-dot"></span><span>NEW YORK (ET)</span></div>
<div class="clock-display" id="ny-live-clock">--:--:-- ET</div>
<div class="status-badge" id="market-status-badge">...</div>
<div class="countdown-text" id="market-countdown">--</div>
</div>
<div class="right-section">
<div><span style="color:#94a3b8;">BTC:</span> <span style="color:{btc_color};font-weight:800;">{btc_text}</span></div>
<div style="border-left:1px solid #334155;padding-left:12px;"><span style="color:#94a3b8;">USD/KRW:</span> <span style="color:#38bdf8;font-weight:800;">{krw_text}</span></div>
</div>
</div>
<script>
function updateNYClock(){{
  try{{
    const now=new Date();
    const tf=new Intl.DateTimeFormat('en-US',{{timeZone:'America/New_York',hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}});
    const tp={{}};tf.formatToParts(now).forEach(p=>tp[p.type]=p.value);
    const h=parseInt(tp.hour,10)%24,m=parseInt(tp.minute,10),tm=h*60+m;
    const wf=new Intl.DateTimeFormat('en-US',{{timeZone:'America/New_York',weekday:'short'}});
    const wd=(wf.formatToParts(now).find(p=>p.type==='weekday')||{{}}).value||'';
    const isWk=(wd==='Sat'||wd==='Sun');
    document.getElementById('ny-live-clock').textContent=`${{String(h).padStart(2,'0')}}:${{tp.minute}}:${{tp.second}} ET`;
    const b=document.getElementById('market-status-badge'),c=document.getElementById('market-countdown'),d=document.getElementById('pulse-dot');
    if(isWk){{b.textContent="WEEKEND CLOSED";b.style.cssText="background:rgba(100,116,139,.2);color:#94a3b8;border:1px solid #475569;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent="월요일 04:00 프리마켓 오픈 대기";d.style.cssText="width:10px;height:10px;border-radius:50%;background:#64748b;";return;}}
    if(tm>=240&&tm<570){{const r=570-tm;b.textContent="⚡ PRE-MARKET";b.style.cssText="background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid #f59e0b;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent=`정규장 개장까지 ${{Math.floor(r/60)}}시간 ${{r%60}}분 전`;d.style.cssText="width:10px;height:10px;border-radius:50%;background:#f59e0b;box-shadow:0 0 10px #f59e0b;";}}
    else if(tm>=570&&tm<960){{const r=960-tm;b.textContent="🟢 REGULAR MARKET (LIVE)";b.style.cssText="background:rgba(16,185,129,.2);color:#34d399;border:1px solid #10b981;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent=`정규장 마감까지 ${{Math.floor(r/60)}}시간 ${{r%60}}분 남음`;d.style.cssText="width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 12px #10b981;";}}
    else if(tm>=960&&tm<1200){{const r=1200-tm;b.textContent="🌙 AFTER-HOURS";b.style.cssText="background:rgba(168,85,247,.15);color:#c084fc;border:1px solid #a855f7;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent=`애프터마켓 종료까지 ${{Math.floor(r/60)}}시간 ${{r%60}}분`;d.style.cssText="width:10px;height:10px;border-radius:50%;background:#a855f7;box-shadow:0 0 10px #a855f7;";}}
    else{{b.textContent="🔒 MARKET CLOSED";b.style.cssText="background:rgba(244,63,94,.15);color:#fb7185;border:1px solid #f43f5e;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent="프리마켓(04:00 ET) 오픈 대기 중";d.style.cssText="width:10px;height:10px;border-radius:50%;background:#f43f5e;";}}
  }}catch(e){{console.error(e);}}
}}
setInterval(updateNYClock,1000);updateNYClock();
</script></body></html>"""
    st.components.v1.html(live_clock_html, height=80)


# ==============================================================================
# 6) DATA FETCHERS
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["top_bar"])
def get_top_bar_data():
    try:
        d = yf.Ticker("BTC-USD").history(period="2d")
        p = safe_float(d['Close'].iloc[-1], 0.0)
        pr = safe_float(d['Close'].iloc[-2], p)
        ch = p - pr
    except Exception:
        p, ch = 0.0, 0.0
    try:
        k = safe_float(yf.Ticker("KRW=X").history(period="2d")['Close'].iloc[-1], 0.0)
    except Exception:
        k = 0.0
    return p, ch, k


@st.cache_data(ttl=CFG["cache"]["indices"])
def get_market_indices():
    tickers = {
        "10년물 국채": "^TNX", "S&P500 야간선물": "ES=F", "나스닥100 야간선물": "NQ=F",
        "다우 야간선물": "YM=F", "WTI 원유": "CL=F", "VIX 변동성": "^VIX", "금 (Gold)": "GC=F",
    }
    out = []
    for name, t in tickers.items():
        try:
            d = yf.Ticker(t).history(period="5d")
            if len(d) >= 2:
                cur = safe_float(d['Close'].iloc[-1], 0.0)
                prev = safe_float(d['Close'].iloc[-2], 0.0)
                chg = ((cur - prev) / prev) * 100 if prev > 0 else 0.0
                out.append({"name": name, "price": cur, "change": chg})
            else:
                out.append({"name": name, "price": 0.0, "change": 0.0})
        except Exception:
            out.append({"name": name, "price": 0.0, "change": 0.0})
    return out


@st.cache_data(ttl=CFG["cache"]["history"])
def get_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    last_err = None
    for attempt in range(2):
        try:
            h = yf.Ticker(ticker).history(period=period)
            if h is None or h.empty:
                if attempt == 0:
                    time.sleep(0.4)
                    continue
                return pd.DataFrame()
            if 'Close' not in h.columns or h['Close'].notna().sum() < 5:
                if attempt == 0:
                    time.sleep(0.4)
                    continue
                return pd.DataFrame()
            if h.index.tz is not None:
                try:
                    h.index = h.index.tz_localize(None)
                except Exception:
                    h.index = h.index.tz_convert(None)
            return h
        except Exception as e:
            last_err = e
            LOG.warning("get_history attempt %d failed for %s: %s", attempt + 1, ticker, e)
            if attempt == 0:
                time.sleep(0.4)
    LOG.error("get_history final failure for %s: %s", ticker, last_err)
    return pd.DataFrame()


@st.cache_data(ttl=CFG["cache"]["market_cap"])
def get_market_cap(ticker: str):
    try:
        t = yf.Ticker(ticker)
        try:
            fi = t.fast_info
            mc = fi.get("market_cap") if hasattr(fi, "get") else None
            if not mc and hasattr(fi, "__getitem__"):
                try:
                    mc = fi["market_cap"]
                except Exception:
                    mc = None
            if mc:
                return float(mc)
        except Exception:
            pass
        try:
            m = t.info.get("marketCap", None)
            return float(m) if m else None
        except Exception:
            return None
    except Exception:
        return None


@st.cache_data(ttl=CFG["cache"]["fear_greed"])
def get_fear_and_greed_index():
    score, rating = 50.0, "Neutral"
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cnn.com/markets/fear-and-greed'},
            timeout=5)
        if r.status_code == 200:
            d = r.json()
            score = safe_float(d['fear_and_greed']['score'], 50.0)
            rating = str(d['fear_and_greed']['rating']).title()
        else:
            raise ValueError("Fallback to VIX")
    except Exception:
        try:
            vix = safe_float(yf.Ticker("^VIX").history(period="2d")['Close'].iloc[-1], 18.0)
            if vix >= 30:
                score, rating = 18.0, "Extreme Fear"
            elif vix >= 22:
                score, rating = 35.0, "Fear"
            elif vix >= 16:
                score, rating = 52.0, "Neutral"
            elif vix >= 13:
                score, rating = 68.0, "Greed"
            else:
                score, rating = 82.0, "Extreme Greed"
        except Exception:
            score, rating = 50.0, "Neutral"

    if score <= 25:
        kr_label, badge_cls, bar_color = "😱 극단적 공포 (Extreme Fear)", "badge-green", "#10b981"
        advice = "대중의 패닉 셀링 구간입니다. 워런 버핏·코너스의 역발상 매수 적기이며, 트레일링 스탑은 중기 표준폭으로 넓게 유지하십시오."
    elif score <= 45:
        kr_label, badge_cls, bar_color = "😨 공포 (Fear)", "badge-blue", "#38bdf8"
        advice = "시장 경계감이 높은 저점 매집 구간입니다. 지지선 확인 후 분할 매수가 유리합니다."
    elif score <= 55:
        kr_label, badge_cls, bar_color = "😐 중립 (Neutral)", "badge-indigo", "#818cf8"
        advice = "지수 방향성보다 개별 종목의 거래량 돌파 및 정배열 수급이 수익률을 결정하는 종목 장세입니다."
    elif score <= 75:
        kr_label, badge_cls, bar_color = "🤑 탐욕 (Greed)", "badge-yellow", "#f59e0b"
        advice = "강세장 추세가 이어지고 있습니다. 보유 물량은 홀딩하되 1차 익절가 도달 시 미래에셋 트레일링 스탑을 가동하십시오."
    else:
        kr_label, badge_cls, bar_color = "🔥 극단적 탐욕 (Extreme Greed)", "badge-red", "#f43f5e"
        advice = "시장 과열 경보 구간입니다! 신규 추격매수를 자제하고 트레일링 스탑을 단기 타이트폭(①번)으로 조여서 수익을 지키십시오."

    return {
        "score": round(score, 1), "rating": rating, "kr_label": kr_label,
        "badge_cls": badge_cls, "bar_color": bar_color, "advice": advice,
    }


# ==============================================================================
# 7) 숏스퀴즈 & 감마스퀴즈
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["short_interest"])
def get_short_interest_data(ticker: str) -> dict:
    short_pct = 0.0
    short_ratio = 0.0
    shares_short = 0.0
    try:
        info = yf.Ticker(ticker).info or {}
        raw_pct = safe_float(info.get("shortPercentOfFloat", 0.0), 0.0)
        short_pct = raw_pct * 100.0 if 0 < raw_pct <= 1.0 else raw_pct
        short_ratio = safe_float(info.get("shortRatio", 0.0), 0.0)
        shares_short = safe_float(info.get("sharesShort", 0.0), 0.0)
    except Exception as e:
        LOG.warning("get_short_interest_data failed for %s: %s", ticker, e)
    return {"short_pct": round(short_pct, 2), "days_to_cover": round(short_ratio, 2), "shares_short": shares_short}


@st.cache_data(ttl=CFG["cache"]["gex"])
def get_gamma_wall_and_gex_data(ticker: str, current_price: float = 0.0, exp_date=None):
    try:
        stock = yf.Ticker(ticker)
        options = stock.options
        if not options:
            return {"call_wall": None, "put_wall": None, "max_pain": None, "exp_dates": [],
                    "cp_oi_ratio": 1.0, "total_call_oi": 0, "total_put_oi": 0,
                    "gex_status": "옵션 데이터 없음", "is_gamma_squeeze_zone": False}
        target_exp = exp_date if exp_date in options else options[0]
        opt_chain = stock.option_chain(target_exp)
        calls = opt_chain.calls[['strike', 'openInterest']].dropna()
        puts = opt_chain.puts[['strike', 'openInterest']].dropna()
        call_wall = float(calls.loc[calls['openInterest'].idxmax()]['strike']) if not calls.empty and calls['openInterest'].max() > 0 else None
        put_wall = float(puts.loc[puts['openInterest'].idxmax()]['strike']) if not puts.empty and puts['openInterest'].max() > 0 else None
        total_call_oi = int(calls['openInterest'].sum()) if not calls.empty else 0
        total_put_oi = int(puts['openInterest'].sum()) if not puts.empty else 0
        cp_oi_ratio = round(total_call_oi / total_put_oi, 2) if total_put_oi > 0 else (2.0 if total_call_oi > 0 else 1.0)
        all_strikes = np.union1d(calls['strike'], puts['strike'])
        pain_values = []
        for strike in all_strikes:
            call_loss = np.maximum(0, strike - calls['strike']) * calls['openInterest']
            put_loss = np.maximum(0, puts['strike'] - strike) * puts['openInterest']
            pain_values.append(call_loss.sum() + put_loss.sum())
        max_pain = float(all_strikes[np.argmin(pain_values)]) if len(pain_values) > 0 else None
        is_gamma_squeeze = False
        if call_wall and current_price > 0:
            dist_to_call_wall = ((call_wall - current_price) / current_price) * 100.0
            if cp_oi_ratio >= 1.35 and -3.0 <= dist_to_call_wall <= 5.5:
                is_gamma_squeeze = True
        if is_gamma_squeeze:
            gex_status = "🔥 감마스퀴즈 점화 구간 (딜러 델타헤지 매수 유입)"
        elif cp_oi_ratio >= 1.3:
            gex_status = "🟢 콜(Call) 감마 우위 (상방 자석 효과)"
        elif cp_oi_ratio <= 0.75:
            gex_status = "🔴 풋(Put) 감마 우위 (하방 변동성 주의)"
        else:
            gex_status = "⚖️ 중립 감마 (맥스페인 수렴 장세)"
        return {"call_wall": call_wall, "put_wall": put_wall, "max_pain": max_pain,
                "exp_dates": list(options), "cp_oi_ratio": cp_oi_ratio,
                "total_call_oi": total_call_oi, "total_put_oi": total_put_oi,
                "gex_status": gex_status, "is_gamma_squeeze_zone": is_gamma_squeeze,
                "target_exp": target_exp}
    except Exception:
        return {"call_wall": None, "put_wall": None, "max_pain": None, "exp_dates": [],
                "cp_oi_ratio": 1.0, "total_call_oi": 0, "total_put_oi": 0,
                "gex_status": "분석 불가", "is_gamma_squeeze_zone": False}


def evaluate_squeeze_potential(short_data, gex_data, current_price, box_high, vol_ratio):
    scfg = CFG["squeeze"]
    sp = short_data.get("short_pct", 0.0)
    dtc = short_data.get("days_to_cover", 0.0)
    cp_ratio = gex_data.get("cp_oi_ratio", 1.0)
    is_gex_zone = gex_data.get("is_gamma_squeeze_zone", False)
    sq_score = 0
    reasons = []
    if sp >= scfg["short_pct_high"]:
        sq_score += 45
        reasons.append(f"공매도 비중 극단 과열({sp:.1f}% ≥ 20%)")
    elif sp >= scfg["short_pct_mid"]:
        sq_score += 25
        reasons.append(f"공매도 비중 높음({sp:.1f}%)")
    if dtc >= scfg["dtc_high"]:
        sq_score += 20
        reasons.append(f"숏커버 소요일수({dtc:.1f}일) 장기화")
    elif dtc >= scfg["dtc_mid"]:
        sq_score += 10
        reasons.append(f"숏커버 소요일수({dtc:.1f}일)")
    if is_gex_zone:
        sq_score += 25
        reasons.append(f"콜 감마벽 돌파 임박 (Call/Put OI {cp_ratio:.2f}배)")
    elif cp_ratio >= 1.4:
        sq_score += 12
        reasons.append(f"콜 옵션 수급 집중 (C/P {cp_ratio:.2f}배)")
    if current_price >= box_high * 0.98 and vol_ratio >= 1.3:
        sq_score += 15
        reasons.append(f"고점 돌파 + 거래량({vol_ratio:.1f}x) 유입으로 숏커버 강제 트리거")
    sq_score = min(100, sq_score)
    bonus = int(round((sq_score / 100.0) * scfg["squeeze_bonus_max"])) if current_price >= box_high * 0.95 else 0
    if sq_score >= 70:
        grade, badge = "🌋 초강력 더블 스퀴즈 경보 (EXTREME SQUEEZE)", "badge-orange"
        guide = "공매도 숏커버링과 마켓메이커의 콜옵션 델타헤지 매수가 동시에 터지는 폭발 구간입니다! 섣부른 전량 매도를 피하고 트레일링 스탑으로 오버슈팅을 끝까지 발라먹으십시오."
    elif sq_score >= 40:
        grade, badge = "⚡ 스퀴즈 잠재력 우수 (HIGH POTENTIAL)", "badge-yellow"
        guide = "공매도 잔고 또는 콜옵션 감마 에너지가 축적되어 있습니다. 박스 상단 거래량 돌파 시 급격한 숏커버 슈팅이 나올 수 있습니다."
    else:
        grade, badge = "⚖️ 일반 수급 장세 (NORMAL)", "badge-blue"
        guide = "인위적인 숏스퀴즈보다 기업의 펀더멘털(실적·계약)과 6대 대가 정배열 추세에 따라 움직이는 정석 구간입니다."
    return {"sq_score": sq_score, "bonus": bonus, "grade": grade, "badge": badge,
            "reasons": reasons if reasons else ["특이 공매도/옵션 과열 신호 없음"], "guide": guide}


# ==============================================================================
# 8) SQLite — v14: signal_outcomes 테이블 추가
# ==============================================================================
def _db_conn():
    return sqlite3.connect(CFG["paths"]["db"], check_same_thread=False)


def init_db():
    try:
        with _db_conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS holdings (ticker TEXT PRIMARY KEY, buy_price REAL NOT NULL DEFAULT 0.0, qty REAL NOT NULL DEFAULT 0.0, target_roi REAL NOT NULL DEFAULT 15.0, stop_loss_pct REAL NOT NULL DEFAULT 7.0, updated_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS alert_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, signal TEXT, price REAL, message TEXT, created_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL, price REAL NOT NULL DEFAULT 0.0, qty REAL NOT NULL DEFAULT 0.0, realized_pnl REAL NOT NULL DEFAULT 0.0, strategy_tag TEXT, emotion_tag TEXT, memo TEXT, created_at TEXT)""")
            # v14 신규: 봇 신호 자동 검증
            conn.execute("""CREATE TABLE IF NOT EXISTS signal_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL, signal TEXT NOT NULL,
                signal_price REAL NOT NULL, signal_date TEXT NOT NULL,
                horizon_days INTEGER NOT NULL,
                eval_date TEXT, price_at_eval REAL, return_pct REAL, outcome TEXT,
                UNIQUE(ticker, signal, signal_date, horizon_days))""")
            conn.commit()
    except Exception as e:
        LOG.error("init_db error: %s", e)


def db_get_holdings() -> list:
    try:
        with _db_conn() as conn:
            rows = conn.execute("SELECT ticker, buy_price, qty, target_roi, stop_loss_pct, updated_at FROM holdings ORDER BY ticker").fetchall()
        return [{"ticker": r[0], "buy_price": safe_float(r[1]), "qty": safe_float(r[2]),
                 "target_roi": safe_float(r[3], 15.0), "stop_loss_pct": safe_float(r[4], 7.0),
                 "updated_at": r[5] or ""} for r in rows]
    except Exception as e:
        LOG.error("db_get_holdings error: %s", e)
        return []


def db_upsert_holding(ticker, buy_price, qty, target_roi=15.0, stop_loss_pct=7.0):
    t = ticker.strip().upper()
    if not t:
        return
    try:
        with _db_conn() as conn:
            conn.execute("""INSERT INTO holdings (ticker, buy_price, qty, target_roi, stop_loss_pct, updated_at) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET buy_price=excluded.buy_price, qty=excluded.qty, target_roi=excluded.target_roi, stop_loss_pct=excluded.stop_loss_pct, updated_at=excluded.updated_at""",
                (t, float(buy_price), float(qty), float(target_roi), float(stop_loss_pct),
                 datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
    except Exception as e:
        LOG.error("db_upsert_holding error: %s", e)


def db_delete_holding(ticker):
    try:
        with _db_conn() as conn:
            conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker.strip().upper(),))
            conn.commit()
    except Exception as e:
        LOG.error("db_delete_holding error: %s", e)


def db_log_alert(ticker, signal, price, message):
    try:
        with _db_conn() as conn:
            conn.execute("INSERT INTO alert_logs (ticker, signal, price, message, created_at) VALUES (?,?,?,?,?)",
                         (ticker, signal, float(price), message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        LOG.error("db_log_alert error: %s", e)


def db_add_journal_entry(trade_date, ticker, side, price, qty, realized_pnl, strategy_tag, emotion_tag, memo):
    try:
        with _db_conn() as conn:
            conn.execute("""INSERT INTO trade_journal (trade_date, ticker, side, price, qty, realized_pnl, strategy_tag, emotion_tag, memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade_date, ticker.strip().upper(), side, float(price), float(qty),
                 float(realized_pnl), strategy_tag, emotion_tag, memo.strip(),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        LOG.error("db_add_journal_entry error: %s", e)


def db_get_journal_entries(limit=200):
    try:
        with _db_conn() as conn:
            rows = conn.execute("""SELECT id, trade_date, ticker, side, price, qty, realized_pnl, strategy_tag, emotion_tag, memo
                FROM trade_journal ORDER BY trade_date DESC, id DESC LIMIT ?""", (limit,)).fetchall()
        return [{"id": r[0], "일자": r[1], "티커": r[2], "구분": r[3], "단가($)": r[4],
                 "수량": r[5], "실현손익($)": r[6], "적용기법": r[7], "심리상태": r[8], "복기메모": r[9]} for r in rows]
    except Exception as e:
        LOG.error("db_get_journal_entries error: %s", e)
        return []


def db_delete_journal_entry(entry_id):
    try:
        with _db_conn() as conn:
            conn.execute("DELETE FROM trade_journal WHERE id = ?", (int(entry_id),))
            conn.commit()
    except Exception as e:
        LOG.error("db_delete_journal_entry error: %s", e)


# ⭐ v14 신규: 신호 자동 검증 함수
def db_register_signal_for_eval(ticker, signal, price, horizons=(5, 10, 20)):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with _db_conn() as conn:
            for h in horizons:
                conn.execute("""INSERT OR IGNORE INTO signal_outcomes
                    (ticker, signal, signal_price, signal_date, horizon_days)
                    VALUES (?,?,?,?,?)""",
                    (ticker.upper(), signal, float(price), today, h))
            conn.commit()
    except Exception as e:
        LOG.error(f"db_register_signal_for_eval: {e}")


def db_eval_pending_signals():
    try:
        with _db_conn() as conn:
            pending = conn.execute("""SELECT id, ticker, signal_price, signal_date, horizon_days
                FROM signal_outcomes WHERE eval_date IS NULL""").fetchall()
    except Exception:
        return
    today = datetime.now().date()
    for row in pending:
        rid, tk, sig_px, sig_dt, hor = row
        try:
            sig_date = datetime.strptime(sig_dt, "%Y-%m-%d").date()
            if (today - sig_date).days < hor:
                continue
            df = get_history(tk, period="3mo")
            if df.empty:
                continue
            df_dates = [d.date() for d in df.index]
            target_idx = None
            for i, d in enumerate(df_dates):
                if d >= sig_date:
                    target_idx = i
                    break
            if target_idx is None:
                continue
            eval_idx = min(target_idx + hor, len(df) - 1)
            eval_price = float(df['Close'].iloc[eval_idx])
            ret_pct = ((eval_price / sig_px) - 1) * 100
            if ret_pct > 2:
                outcome = "WIN"
            elif ret_pct < -2:
                outcome = "LOSS"
            else:
                outcome = "NEUTRAL"
            with _db_conn() as conn:
                conn.execute("""UPDATE signal_outcomes SET eval_date=?, price_at_eval=?, return_pct=?, outcome=? WHERE id=?""",
                             (today.strftime("%Y-%m-%d"), eval_price, round(ret_pct, 2), outcome, rid))
                conn.commit()
        except Exception as e:
            LOG.warning(f"eval signal {rid}: {e}")


def db_get_signal_stats():
    try:
        with _db_conn() as conn:
            rows = conn.execute("""SELECT signal, horizon_days, COUNT(*) as total,
                SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(return_pct) as avg_ret
                FROM signal_outcomes WHERE outcome IS NOT NULL
                GROUP BY signal, horizon_days""").fetchall()
        out = []
        for r in rows:
            sig, hor, tot, wins, losses, avg_ret = r
            wr = (wins / tot * 100) if tot > 0 else 0
            out.append({"signal": sig, "horizon": hor, "total": tot, "wins": wins,
                        "losses": losses, "win_rate": round(wr, 1),
                        "avg_return": round(avg_ret or 0, 2)})
        return out
    except Exception:
        return []


def db_get_pending_signal_count() -> int:
    try:
        with _db_conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM signal_outcomes WHERE outcome IS NULL").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


init_db()


# ==============================================================================
# 9) 텔레그램 & 트레일링
# ==============================================================================
def send_telegram_alert(text, token="", chat_id=""):
    tk = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    cid = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not tk or not cid:
        return False, "텔레그램 봇 토큰 또는 채팅 ID 미설정"
    try:
        url = f"https://api.telegram.org/bot{tk}/sendMessage"
        resp = requests.post(url, json={"chat_id": cid, "text": text, "disable_web_page_preview": True}, timeout=6)
        if resp.status_code == 200:
            return True, "전송 성공!"
        return False, f"전송 실패 (HTTP {resp.status_code})"
    except Exception as e:
        return False, f"오류: {e}"


def get_stock_cap_and_trailing_profile(ticker, mkt_cap, atr_pct):
    t_upper = ticker.upper()
    tr_cfg = CFG["trail"]
    tiers = tr_cfg["tiers"]
    fb = tr_cfg["fallback"]
    if t_upper in tr_cfg["leverage_etfs"]:
        cap_tier, cap_desc, cap_badge = "🚀 2~3X 레버리지 ETF", "초고변동성 레버리지 상품", "badge-purple"
        min_tight, max_tight = tr_cfg["leverage_tier"]["tight"]
        min_core, max_core = tr_cfg["leverage_tier"]["core"]
    elif mkt_cap and mkt_cap >= tiers["mega"]["min"]:
        cap_tier, cap_desc, cap_badge = "👑 메가캡 (초대형주)", f"시총 ${mkt_cap/1e9:,.0f}B", "badge-blue"
        min_tight, max_tight = tiers["mega"]["tight"]
        min_core, max_core = tiers["mega"]["core"]
    elif mkt_cap and mkt_cap >= tiers["large"]["min"]:
        cap_tier, cap_desc, cap_badge = "🐘 대형주 (Large Cap)", f"시총 ${mkt_cap/1e9:,.1f}B", "badge-green"
        min_tight, max_tight = tiers["large"]["tight"]
        min_core, max_core = tiers["large"]["core"]
    elif mkt_cap and mkt_cap >= tiers["mid"]["min"]:
        cap_tier, cap_desc, cap_badge = "🐆 중형 성장주 (Mid Cap)", f"시총 ${mkt_cap/1e9:,.2f}B", "badge-yellow"
        min_tight, max_tight = tiers["mid"]["tight"]
        min_core, max_core = tiers["mid"]["core"]
    elif mkt_cap and mkt_cap > 0:
        cap_tier, cap_desc, cap_badge = "⚡ 소형 급등주 (Small Cap)", f"시총 ${mkt_cap/1e6:,.0f}M", "badge-red"
        min_tight, max_tight = tiers["small"]["tight"]
        min_core, max_core = tiers["small"]["core"]
    else:
        if atr_pct >= fb["high"]["atr_min"]:
            cap_tier, cap_desc, cap_badge = "⚡ 고변동 테마/소형급", "일일 변동폭 상위 종목", "badge-red"
            min_tight, max_tight = fb["high"]["tight"]
            min_core, max_core = fb["high"]["core"]
        elif atr_pct >= fb["mid"]["atr_min"]:
            cap_tier, cap_desc, cap_badge = "🐆 중형 모멘텀급", "중위 변동성 성장주", "badge-yellow"
            min_tight, max_tight = fb["mid"]["tight"]
            min_core, max_core = fb["mid"]["core"]
        else:
            cap_tier, cap_desc, cap_badge = "🐘 대형 안정급", "안정적 대형/지수군", "badge-green"
            min_tight, max_tight = fb["low"]["tight"]
            min_core, max_core = fb["low"]["core"]
    ts_tight_pct = float(np.clip(round(atr_pct * CFG["noise"]["tight_atr"], 1), min_tight, max_tight))
    ts_core_pct = float(np.clip(round(atr_pct * CFG["noise"]["chandelier_atr"], 1), min_core, max_core))
    return {"cap_tier": cap_tier, "cap_desc": cap_desc, "cap_badge": cap_badge,
            "atr_pct": atr_pct, "ts_tight_pct": ts_tight_pct, "ts_core_pct": ts_core_pct}


def normalize_indices_key(indices):
    return tuple((str(item.get("name", "")), round(safe_float(item.get("price", 0.0)), 2),
                  round(safe_float(item.get("change", 0.0)), 2)) for item in (indices or []))


# ==============================================================================
# 10) 매크로 + 뉴스
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["macro"])
def analyze_macro_and_stock_catalysts(ticker, indices_key, use_llm=False):
    idx_map = {name: {"price": price, "change": chg} for name, price, chg in indices_key}
    tnx = idx_map.get("10년물 국채", {"price": 4.2, "change": 0.0})
    wti = idx_map.get("WTI 원유", {"price": 72.0, "change": 0.0})
    vix = idx_map.get("VIX 변동성", {"price": 18.0, "change": 0.0})
    gold = idx_map.get("금 (Gold)", {"price": 2700.0, "change": 0.0})
    nq = idx_map.get("나스닥100 야간선물", {"price": 20000.0, "change": 0.0})
    es = idx_map.get("S&P500 야간선물", {"price": 5800.0, "change": 0.0})
    mc = CFG["macro"]
    macro_score = 0
    macro_alerts = []
    if nq["change"] >= mc["nq_strong"] or es["change"] >= mc["es_strong"]:
        macro_score += 12
        macro_alerts.append(f"🌃 미장 야간선물 강세 (나스닥 {nq['change']:+.1f}%, S&P {es['change']:+.1f}%)")
    elif nq["change"] <= -mc["nq_strong"] or es["change"] <= -mc["es_strong"]:
        macro_score -= 12
        macro_alerts.append(f"🌃 미장 야간선물 약세 (나스닥 {nq['change']:+.1f}%, S&P {es['change']:+.1f}%)")
    if wti['change'] >= mc["wti_spike_chg"] or wti['price'] >= mc["wti_spike_price"]:
        macro_score -= 12
        macro_alerts.append(f"🛢️ 유가 급등 (${wti['price']:.1f})")
    elif (wti['change'] <= -1.5 or wti['price'] < mc["wti_stable"]) and wti['price'] > 0:
        macro_score += 5
        macro_alerts.append(f"🛢️ 유가 안정 (${wti['price']:.1f})")
    if tnx['price'] >= mc["tnx_spike_price"] or tnx['change'] >= mc["tnx_spike_chg"]:
        macro_score -= 12
        macro_alerts.append(f"🏦 금리 발작 ({tnx['price']:.2f}%)")
    elif (tnx['change'] <= -1.0 or tnx['price'] < mc["tnx_stable"]) and tnx['price'] > 0:
        macro_score += 8
        macro_alerts.append(f"🏦 금리 안정 ({tnx['price']:.2f}%)")
    if vix['price'] >= mc["vix_crisis"] or (vix['change'] >= 5.0 and gold['change'] >= 1.0):
        macro_score -= 15
        macro_alerts.append(f"💣 지정학 경보 (VIX {vix['price']:.1f})")
    elif 0 < vix['price'] < mc["vix_calm"] and nq['change'] >= 0:
        macro_score += 7
        macro_alerts.append(f"🕊️ 위험선호 양호 (VIX {vix['price']:.1f})")
    if not macro_alerts:
        macro_alerts.append(f"⚖️ 거시 중립 (금리 {tnx['price']:.2f}% | WTI ${wti['price']:.1f} | VIX {vix['price']:.1f})")

    earnings_info = "실적 일정 미정/통과"
    earnings_imminent = False
    try:
        cal = yf.Ticker(ticker).calendar
        if isinstance(cal, dict) and cal.get('Earnings Date'):
            ed = cal['Earnings Date']
            ne = ed[0] if isinstance(ed, list) else ed
            dl = (pd.to_datetime(ne).date() - datetime.now().date()).days
            if 0 <= dl <= 7:
                earnings_info = f"⚠️ 실적 임박 (D-{dl}일: {ne})"
                earnings_imminent = True
            elif dl > 7:
                earnings_info = f"📅 차기 실적: {ne} (D-{dl}일)"
    except Exception:
        pass

    query = urllib.parse.quote(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    news_items = []
    ncfg = CFG["news"]
    ch_ = 0
    ebh = 0
    bh = 0
    gh = 0
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
        for item in root.findall('.//item')[:6]:
            raw_title = (item.find('title').text if item.find('title') is not None else "") or ""
            raw_link = (item.find('link').text if item.find('link') is not None else "#") or "#"
            raw_pub = (item.find('pubDate').text[:16] if (item.find('pubDate') is not None and item.find('pubDate').text) else "")
            tl = raw_title.lower()
            c_hit = any(k in tl for k in ncfg["contract"])
            eb_hit = any(k in tl for k in ncfg["earnings_bull"]) or any(k in tl for k in ncfg["cut_bullish"])
            bad_hit = any(k in tl for k in ncfg["bad_strict"]) or any(k in tl for k in ncfg["cut_bearish"])
            g_hit = any(k in tl for k in ncfg["geo"])
            if c_hit: ch_ += 1
            if eb_hit: ebh += 1
            if bad_hit: bh += 1
            if g_hit: gh += 1
            if bad_hit: sentiment, badge_class = "🚨 악재/주의", "badge-red"
            elif c_hit: sentiment, badge_class = "🤝 계약/수주", "badge-green"
            elif eb_hit: sentiment, badge_class = "📈 실적 호조", "badge-green"
            elif g_hit: sentiment, badge_class = "🌍 거시 이슈", "badge-yellow"
            else: sentiment, badge_class = "📰 일반/중립", "badge-blue"
            news_items.append({"title": html.escape(raw_title), "link": safe_url(raw_link),
                               "date": html.escape(raw_pub), "sentiment": sentiment, "badge_class": badge_class})
    except Exception as e:
        LOG.warning("RSS fetch failed for %s: %s", ticker, e)

    catalyst_score = (ch_ * 8) + (ebh * 6) - (bh * 12) - (gh * 4)
    if earnings_imminent:
        catalyst_score -= 5
    llm_insight = ""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if use_llm and api_key and news_items:
        try:
            headlines_txt = "\n".join(f"- {n['title']}" for n in news_items[:5])
            resp = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini",
                      "messages": [{"role": "system", "content": "미국 주식 애널리스트로서 헤드라인을 보고 핵심 호악재를 한국어 1문장(60자 이내)으로 요약하세요."},
                                   {"role": "user", "content": f"종목: {ticker}\n헤드라인:\n{headlines_txt}"}],
                      "max_tokens": 90, "temperature": 0.2},
                timeout=4)
            if resp.status_code == 200:
                llm_insight = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
    catalyst_summary = []
    if ch_ > 0: catalyst_summary.append(f"🤝 계약/파트너십 ({ch_}건)")
    if ebh > 0: catalyst_summary.append(f"📊 실적 호조 ({ebh}건)")
    if bh > 0: catalyst_summary.append(f"🚨 악재 ({bh}건 주의)")
    if gh > 0: catalyst_summary.append(f"🌍 거시 변수 ({gh}건)")
    if llm_insight: catalyst_summary.append(f"🤖 LLM: {llm_insight}")
    if not catalyst_summary: catalyst_summary.append("특이 돌발 악재 없음 (수급 중심)")

    return {"macro_score": macro_score, "macro_alerts": macro_alerts,
            "earnings_info": html.escape(earnings_info), "earnings_imminent": earnings_imminent,
            "contract_hits": ch_, "earnings_bull_hits": ebh, "bad_news_hits": bh, "geo_hits": gh,
            "catalyst_score": catalyst_score, "catalyst_summary": catalyst_summary,
            "news_items": news_items, "tnx": tnx, "wti": wti, "vix": vix}


# ==============================================================================
# 11) 노이즈 필터
# ==============================================================================
def evaluate_holding_noise_filter(ticker, hist, buy_price=0.0, qty=0.0, target_roi_pct=15.0, custom_stop_pct=7.0):
    if hist is None or hist.empty or len(hist) < 25:
        return None
    close, high, low, vol = hist['Close'], hist['High'], hist['Low'], hist['Volume']
    curr_price = safe_float(close.iloc[-1], 0.0)
    prev_price = safe_float(close.iloc[-2], curr_price)
    if curr_price <= 0:
        return None
    day_chg_pct = ((curr_price - prev_price) / prev_price) * 100.0 if prev_price > 0 else 0.0
    ema10 = safe_float(close.ewm(span=10, adjust=False).mean().iloc[-1], curr_price)
    ema20 = safe_float(close.ewm(span=20, adjust=False).mean().iloc[-1], curr_price)
    ema50 = safe_float(close.ewm(span=50, adjust=False).mean().iloc[-1], curr_price)
    ema200 = safe_float(close.ewm(span=200, adjust=False).mean().iloc[-1], ema50) if len(hist) >= 200 else ema50
    high_20 = safe_float(high.rolling(CFG["ind"]["box_period"]).max().iloc[-1], curr_price)
    low_20 = safe_float(low.rolling(CFG["ind"]["box_period"]).min().iloc[-1], curr_price)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    atr = safe_float(pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(CFG["ind"]["atr_period"]).mean().iloc[-1], curr_price * 0.03)
    if atr <= 0:
        atr = curr_price * 0.03
    atr_pct = (atr / curr_price) * 100.0
    rsi = safe_float(compute_wilder_rsi(close, CFG["ind"]["rsi_period"]).iloc[-1], 50.0)
    avg_vol = safe_float(vol.rolling(20).mean().iloc[-1], 0.0)
    curr_vol = safe_float(vol.iloc[-1], 0.0)
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
    mkt_cap = get_market_cap(ticker)
    cap_prof = get_stock_cap_and_trailing_profile(ticker, mkt_cap, atr_pct)
    ts_core_pct = cap_prof['ts_core_pct']
    ts_tight_pct = cap_prof['ts_tight_pct']
    ncfg = CFG["noise"]
    chandelier_stop = high_20 * (1.0 - ts_core_pct / 100.0)
    noise_band_pct = round(min(ts_core_pct * 0.75, atr_pct * ncfg["band_atr_mult"]), 1)
    drawdown_from_high_pct = ((curr_price - high_20) / high_20) * 100.0 if high_20 > 0 else 0.0
    eff_buy = buy_price if buy_price > 0 else curr_price
    roi_pct = ((curr_price - eff_buy) / eff_buy) * 100.0 if eff_buy > 0 else 0.0
    hard_stop_price = max(eff_buy * (1.0 - custom_stop_pct / 100.0), chandelier_stop) if buy_price > 0 else chandelier_stop
    target_price = eff_buy * (1.0 + target_roi_pct / 100.0) if buy_price > 0 else curr_price * 1.12
    noise_used_ratio = min(100.0, max(0.0, (abs(drawdown_from_high_pct) / ts_core_pct) * 100.0)) if ts_core_pct > 0 else 0.0
    is_minor_wave = abs(day_chg_pct) <= (atr_pct * ncfg["minor_atr_mult"]) and curr_price >= chandelier_stop
    bear_confirm = 0.0
    if curr_price < ema20: bear_confirm += 2.5
    if curr_price < ema50: bear_confirm += 3.5
    if vol_ratio >= CFG["ind"]["vol_exit"] and day_chg_pct < -atr_pct: bear_confirm += 2.5
    if noise_used_ratio >= ncfg["warn_ratio"]: bear_confirm += 1.5

    if (buy_price > 0 and curr_price <= eff_buy * (1.0 - custom_stop_pct / 100.0)) or curr_price <= chandelier_stop:
        signal = SIGNAL_STOP_HIT
        wave_status = "🌊 대파도 (추세 손절선 붕괴)"
        headline = f"고점 대비 {drawdown_from_high_pct:.1f}% 하락 — 샹들리에/손절선(${hard_stop_price:,.2f}) 이탈"
        action_guide = "단순 노이즈 범위를 벗어난 구조적 이탈입니다. 원칙 손절/청산으로 계좌를 보호하십시오."
    elif bear_confirm >= ncfg["confirm_bear"]:
        signal = SIGNAL_EXIT
        wave_status = "🌊 대파도 (기관 분배·추세 붕괴 변곡점)"
        headline = f"20일(${ema20:,.2f})·50일선(${ema50:,.2f}) 이탈 (하락컨펌 {bear_confirm:.1f}점)"
        action_guide = "와인스타인 하락 변곡점이 확정되었습니다. 보유 물량의 70~100%를 즉시 현금화하십시오."
    elif (buy_price > 0 and roi_pct >= target_roi_pct) or (rsi >= CFG["ind"]["rsi_take_profit"] and curr_price >= high_20):
        signal = SIGNAL_TAKE_PROFIT
        wave_status = "🌊 상방 변곡점 (슈팅/목표 익절 도달)"
        headline = f"수익률 {roi_pct:+.1f}% | Wilder RSI {rsi:.1f} 과열권 — 분할 익절 타점"
        action_guide = f"1차 물량(30~50%)을 수익 확정하고 잔여 물량은 타이트 트레일링(-{ts_tight_pct:.1f}%)으로 추종하십시오."
    elif bear_confirm >= ncfg["confirm_watch"] or curr_price < ema20:
        signal = SIGNAL_WATCH
        wave_status = "⚠️ 중파도 (생명선 공방 / 노이즈 한계 근접)"
        headline = f"20일선(${ema20:,.2f}) 공방 | 고점 대비 {drawdown_from_high_pct:.1f}% (한계 -{ts_core_pct:.1f}%)"
        action_guide = f"아직 샹들리에 청산선(${chandelier_stop:,.2f})은 방어 중이나 종가상 이탈 시 즉시 매도 준비하십시오."
    elif curr_price >= ema20 and (curr_price < ema10 or atr_pct >= 5.0):
        signal = SIGNAL_HOLD_SHORT
        wave_status = "〰️ 잔파도 (단기 눌림목 노이즈 — 무시)"
        headline = f"10일선 눌림목이나 20일 생명선(${ema20:,.2f}) 위 건전한 소화 과정"
        action_guide = f"일일 ±{noise_band_pct:.1f}% 이내는 정상 호흡입니다. 흔들리지 말고 홀딩하되 단기 스탑(-{ts_tight_pct:.1f}%)을 유지하십시오."
    else:
        signal = SIGNAL_HOLD_LONG
        wave_status = "🌊 잔파도 무시 (완벽 정배열 순항 중)"
        headline = f"10·20·50일선 정배열 + 노이즈 허용폭(-{ts_core_pct:.1f}%) 내 안정적 추세 지속"
        action_guide = f"리버모어·미너비니의 'Sit Tight' 구간입니다. 일일 잔파도(±{atr_pct:.1f}%)에 털리지 말고 대시세를 누리십시오."

    return {"ticker": html.escape(ticker.upper()), "curr_price": curr_price, "day_chg_pct": day_chg_pct,
            "buy_price": eff_buy, "qty": qty, "roi_pct": roi_pct,
            "pnl_usd": (curr_price - eff_buy) * qty if buy_price > 0 and qty > 0 else 0.0,
            "ema10": ema10, "ema20": ema20, "ema50": ema50, "ema200": ema200,
            "high_20": high_20, "low_20": low_20, "atr": atr, "atr_pct": round(atr_pct, 1),
            "rsi": round(rsi, 1), "vol_ratio": round(vol_ratio, 1),
            "ts_core_pct": ts_core_pct, "ts_tight_pct": ts_tight_pct,
            "chandelier_stop": chandelier_stop, "hard_stop_price": hard_stop_price,
            "target_price": target_price, "noise_band_pct": noise_band_pct,
            "drawdown_from_high_pct": round(drawdown_from_high_pct, 1),
            "noise_used_ratio": round(noise_used_ratio, 1), "is_minor_wave": is_minor_wave,
            "signal": signal, "severity": SIGNAL_SEVERITY.get(signal, 0),
            "badge": SIGNAL_BADGE.get(signal, "badge-blue"),
            "wave_status": wave_status, "headline": headline,
            "action_guide": action_guide, "cap_tier": cap_prof['cap_tier']}


@st.cache_data(ttl=CFG["cache"]["noise_filter"])
def evaluate_holding_noise_filter_cached(ticker, buy_price, qty, target_roi_pct, custom_stop_pct):
    h = get_history(ticker)
    return evaluate_holding_noise_filter(ticker, h, buy_price, qty, target_roi_pct, custom_stop_pct)


# ==============================================================================
# 12) 스캐너 / 백테스트 / WFA / 리스크
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["scanner"])
def scan_watchlist(ticker_string):
    tickers = list(dict.fromkeys(t.strip().upper() for t in ticker_string.replace(',', ' ').split() if t.strip()))
    if not tickers:
        return []
    try:
        data = yf.download(tickers, period="3mo", group_by='ticker', threads=True, progress=False)
    except Exception:
        return []
    signals = []
    for t in tickers:
        try:
            df = data[t].dropna() if len(tickers) > 1 else data.dropna()
            if len(df) < 20:
                continue
            close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
            curr_price = safe_float(close.iloc[-1], 0.0)
            prev_price = safe_float(close.iloc[-2], curr_price)
            if curr_price <= 0:
                continue
            change_pct = ((curr_price - prev_price) / prev_price) * 100.0 if prev_price > 0 else 0.0
            ema20 = safe_float(close.ewm(span=20, adjust=False).mean().iloc[-1], curr_price)
            box_high = safe_float(high.rolling(20).max().iloc[-1], curr_price)
            box_low = safe_float(low.rolling(20).min().iloc[-1], curr_price)
            rsi = safe_float(compute_wilder_rsi(close, 14).iloc[-1], 50.0)
            avg_vol = safe_float(vol.rolling(20).mean().iloc[-1], 0.0)
            curr_vol = safe_float(vol.iloc[-1], 0.0)
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            atr_val = safe_float(pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1], curr_price * 0.035)
            atr_pct = (atr_val / curr_price) * 100.0 if curr_price > 0 else 3.5
            ts_rec = round(float(np.clip(atr_pct * 2.6, 5.5, 16.5)), 1)
            action, badge = "⏸️ WAIT", "badge-blue"
            if curr_price >= box_high and vol_ratio >= 1.5:
                action, badge = "🔥 STRONG BUY", "badge-green"
            elif curr_price >= box_high:
                action, badge = "📈 BUY", "badge-green"
            elif curr_price < ema20 and rsi <= 25.0:
                action, badge = "🟢 PANIC BUY", "badge-green"
            elif curr_price < ema20:
                action, badge = "⚠️ EXIT", "badge-red"
            elif curr_price > ema20:
                action, badge = "✅ HOLD", "badge-yellow"
            signals.append({"ticker": html.escape(t), "price": curr_price, "change_pct": change_pct,
                            "action": action, "badge": badge, "rsi": rsi, "vol": vol_ratio,
                            "box_high": box_high, "box_low": box_low,
                            "atr_pct": round(atr_pct, 1), "ts_rec": ts_rec, "is_buy": "BUY" in action})
        except Exception:
            pass
    po = {"🔥 STRONG BUY": 0, "🟢 PANIC BUY": 1, "📈 BUY": 2, "✅ HOLD": 3, "⏸️ WAIT": 4, "⚠️ EXIT": 5}
    signals.sort(key=lambda x: (po.get(x['action'], 99), -x['change_pct']))
    return signals


def _simulate_df(df_in, init_capital=10000.0, box_win=20, atr_mult=2.8):
    df = df_in.copy()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['Box_High_Prev'] = df['High'].rolling(box_win).max().shift(1)
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    df['RSI'] = compute_wilder_rsi(df['Close'], 14)
    tr1 = df['High'] - df['Low']
    tr2 = (df['High'] - df['Close'].shift(1)).abs()
    tr3 = (df['Low'] - df['Close'].shift(1)).abs()
    df['ATR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    df = df.dropna().copy()
    if len(df) < 15:
        return {}
    cash = init_capital
    shares = 0.0
    entry_price = 0.0
    entry_date = None
    peak_price = 0.0
    trades = []
    equity_curve = []
    for dt, row in df.iterrows():
        px = float(row['Close'])
        ema20 = float(row['EMA20'])
        ema50 = float(row['EMA50'])
        box_h = float(row['Box_High_Prev'])
        vol_r = float(row['Volume']) / float(row['Vol_MA20']) if row['Vol_MA20'] > 0 else 1.0
        rsi_v = float(row['RSI'])
        atr_v = float(row['ATR']) if row['ATR'] > 0 else px * 0.03
        atr_p = (atr_v / px) * 100.0
        ts_pct = float(np.clip(atr_p * atr_mult, 5.5, 16.0))
        if shares > 0:
            peak_price = max(peak_price, float(row['High']))
            chandelier_exit = peak_price * (1.0 - ts_pct / 100.0)
            hard_stop = entry_price * 0.93
            roi_now = ((px - entry_price) / entry_price) * 100.0
            exit_reason = None
            if px <= max(hard_stop, chandelier_exit):
                exit_reason = f"샹들리에/손절 이탈 (-{ts_pct:.1f}%)"
            elif px < ema50 and px < ema20:
                exit_reason = "20·50일선 추세 붕괴"
            elif rsi_v >= 78.0 and roi_now >= 12.0:
                exit_reason = f"RSI 과열 익절 ({rsi_v:.0f})"
            if exit_reason:
                cash = shares * px
                trades.append({"매수일": entry_date.strftime("%Y-%m-%d"), "매수가($)": round(entry_price, 2),
                               "청산일": dt.strftime("%Y-%m-%d"), "청산가($)": round(px, 2),
                               "수익률(%)": round(roi_now, 2), "청산사유": exit_reason})
                shares = 0.0
                entry_price = 0.0
                peak_price = 0.0
        else:
            breakout_buy = (px >= box_h and vol_r >= 1.25 and px > ema20)
            trend_pullback_buy = (px > ema20 and ema20 > ema50 and 40.0 <= rsi_v <= 62.0)
            panic_buy = (px < ema20 and rsi_v <= 26.0)
            if breakout_buy or trend_pullback_buy or panic_buy:
                shares = cash / px
                cash = 0.0
                entry_price = px
                entry_date = dt
                peak_price = px
        equity_curve.append({"date": dt, "strategy_eq": cash + (shares * px)})
    if shares > 0:
        last_px = float(df['Close'].iloc[-1])
        roi_now = ((last_px - entry_price) / entry_price) * 100.0
        trades.append({"매수일": entry_date.strftime("%Y-%m-%d"), "매수가($)": round(entry_price, 2),
                       "청산일": "보유중", "청산가($)": round(last_px, 2),
                       "수익률(%)": round(roi_now, 2), "청산사유": "보유중"})
    eq_df = pd.DataFrame(equity_curve).set_index("date")
    first_px = float(df['Close'].iloc[0])
    eq_df["bh_eq"] = (df['Close'] / first_px) * init_capital
    strat_ret = ((eq_df["strategy_eq"].iloc[-1] / init_capital) - 1.0) * 100.0
    bh_ret = ((eq_df["bh_eq"].iloc[-1] / init_capital) - 1.0) * 100.0
    strat_peak = eq_df["strategy_eq"].cummax()
    strat_dd = ((eq_df["strategy_eq"] - strat_peak) / strat_peak) * 100.0
    mdd_strat = float(strat_dd.min())
    bh_peak = eq_df["bh_eq"].cummax()
    bh_dd = ((eq_df["bh_eq"] - bh_peak) / bh_peak) * 100.0
    mdd_bh = float(bh_dd.min())
    wins = [t for t in trades if t["수익률(%)"] > 0]
    win_rate = (len(wins) / len(trades)) * 100.0 if trades else 0.0
    return {"eq_df": eq_df, "trades": trades, "strat_ret": round(strat_ret, 2),
            "bh_ret": round(bh_ret, 2), "mdd_strat": round(mdd_strat, 2),
            "mdd_bh": round(mdd_bh, 2), "win_rate": round(win_rate, 1),
            "total_trades": len(trades), "final_equity": round(float(eq_df["strategy_eq"].iloc[-1]), 2)}


def run_strategy_backtest(ticker, period="2y", init_capital=10000.0):
    df = get_history(ticker, period=period)
    if df.empty or len(df) < 40:
        return {}
    return _simulate_df(df, init_capital=init_capital)


def run_walk_forward(ticker, period="3y", n_splits=4, is_ratio=0.7):
    df = get_history(ticker, period=period)
    if df.empty or len(df) < 120:
        return {}
    total_len = len(df)
    fold_size = total_len // n_splits
    if fold_size < 35:
        return {}
    param_grid = [(15, 2.2), (20, 2.8), (25, 3.2)]
    folds = []
    oos_returns = []
    is_returns = []
    for i in range(n_splits):
        start_idx = i * fold_size
        end_idx = total_len if i == n_splits - 1 else (i + 1) * fold_size
        seg = df.iloc[start_idx:end_idx]
        split_pt = int(len(seg) * is_ratio)
        is_df = seg.iloc[:split_pt]
        oos_df = seg.iloc[max(0, split_pt - 25):]
        best_ret = -999.0
        best_params = (20, 2.8)
        for bw, am in param_grid:
            r_is = _simulate_df(is_df, 10000.0, box_win=bw, atr_mult=am)
            if r_is and r_is["strat_ret"] > best_ret:
                best_ret = r_is["strat_ret"]
                best_params = (bw, am)
        r_oos = _simulate_df(oos_df, 10000.0, box_win=best_params[0], atr_mult=best_params[1])
        oos_ret = r_oos.get("strat_ret", 0.0) if r_oos else 0.0
        oos_mdd = r_oos.get("mdd_strat", 0.0) if r_oos else 0.0
        is_ret = best_ret if best_ret > -900 else 0.0
        is_returns.append(is_ret)
        oos_returns.append(oos_ret)
        folds.append({"Fold": f"Fold {i+1}",
                      "IS 구간": f"{is_df.index[0].strftime('%y.%m.%d')}~{is_df.index[-1].strftime('%y.%m.%d')}",
                      "OOS 구간": f"{seg.iloc[split_pt].name.strftime('%y.%m.%d')}~{seg.index[-1].strftime('%y.%m.%d')}",
                      "최적 파라미터": f"Box={best_params[0]}일, ATR×{best_params[1]}",
                      "IS 수익률(%)": round(is_ret, 2),
                      "OOS 수익률(%)": round(oos_ret, 2),
                      "OOS MDD(%)": round(oos_mdd, 2)})
    cum_oos = 1.0
    for r in oos_returns:
        cum_oos *= (1.0 + r / 100.0)
    cum_oos_pct = (cum_oos - 1.0) * 100.0
    avg_is = float(np.mean(is_returns)) if is_returns else 0.0
    avg_oos = float(np.mean(oos_returns)) if oos_returns else 0.0
    wfe = (avg_oos / avg_is) * 100.0 if abs(avg_is) > 0.5 else 100.0
    pos_folds = sum(1 for r in oos_returns if r >= 0)
    consistency = (pos_folds / len(oos_returns)) * 100.0 if oos_returns else 0.0
    if cum_oos_pct > 0 and consistency >= 50.0:
        verdict = "✅ 강건성 통과 (ROBUST)"
    elif cum_oos_pct >= -5.0:
        verdict = "🟡 보통 (MODERATE)"
    else:
        verdict = "🔴 과최적화 주의 (OVERFIT)"
    return {"ticker": ticker, "folds": folds, "cum_oos_pct": round(cum_oos_pct, 2),
            "avg_is_pct": round(avg_is, 2), "avg_oos_pct": round(avg_oos, 2),
            "wfe": round(float(np.clip(wfe, -200.0, 250.0)), 1),
            "consistency": round(consistency, 1), "verdict": verdict}


def build_full_risk_report(holdings, benchmark="SPY"):
    if not holdings:
        return {}
    tickers = [h["ticker"].upper() for h in holdings]
    all_syms = list(dict.fromkeys(tickers + [benchmark]))
    try:
        raw = yf.download(all_syms, period="6mo", group_by="ticker", threads=True, progress=False)
    except Exception:
        return {}
    close_dict = {}
    for s in all_syms:
        try:
            s_df = raw[s]["Close"].dropna() if len(all_syms) > 1 else raw["Close"].dropna()
            if len(s_df) >= 20:
                close_dict[s] = s_df
        except Exception:
            pass
    valid_holdings = [h for h in holdings if h["ticker"].upper() in close_dict]
    if not valid_holdings:
        return {}
    prices_df = pd.DataFrame(close_dict).dropna()
    if len(prices_df) < 20:
        return {}
    rets_df = prices_df.pct_change().dropna()
    pos_values = []
    for h in valid_holdings:
        t = h["ticker"].upper()
        curr_px = float(prices_df[t].iloc[-1])
        qty = h["qty"] if h["qty"] > 0 else 10.0
        vol_i = float(rets_df[t].std() * np.sqrt(252) * 100.0)
        pos_values.append({"ticker": t, "value": curr_px * qty, "curr_price": curr_px, "qty": qty, "ann_vol": max(5.0, vol_i)})
    total_val = sum(p["value"] for p in pos_values)
    if total_val <= 0:
        return {}
    weights = np.array([p["value"] / total_val for p in pos_values])
    inv_vols = np.array([1.0 / p["ann_vol"] for p in pos_values])
    rp_weights = inv_vols / inv_vols.sum()
    port_syms = [p["ticker"] for p in pos_values]
    port_rets = (rets_df[port_syms] * weights).sum(axis=1)
    ann_vol = float(port_rets.std() * np.sqrt(252) * 100.0)
    ann_ret = float(port_rets.mean() * 252 * 100.0)
    sharpe = (ann_ret - 4.0) / ann_vol if ann_vol > 0 else 0.0
    var_95_pct = float(np.percentile(port_rets, 5) * 100.0)
    var_99_pct = float(np.percentile(port_rets, 1) * 100.0)
    tail_95 = port_rets[port_rets <= np.percentile(port_rets, 5)]
    cvar_95_pct = float(tail_95.mean() * 100.0) if len(tail_95) > 0 else var_95_pct
    beta = 1.0
    if benchmark in rets_df.columns:
        bm_rets = rets_df[benchmark]
        cov = float(np.cov(port_rets, bm_rets)[0, 1])
        bm_var = float(np.var(bm_rets))
        beta = cov / bm_var if bm_var > 0 else 1.0
    hhi = float(np.sum(weights ** 2) * 100.0)
    corr_matrix = rets_df[port_syms].corr().round(2)
    weights_table = []
    rebal_actions = []
    for p, w, rpw in zip(pos_values, weights, rp_weights):
        cur_w = round(w * 100.0, 1)
        opt_w = round(rpw * 100.0, 1)
        diff_w = round(opt_w - cur_w, 1)
        weights_table.append({"종목": p["ticker"], "평가금액($)": round(p["value"], 1),
                              "현재비중(%)": cur_w, "권장비중(역변동성%)": opt_w, "조정폭(%p)": diff_w})
        if abs(diff_w) >= 5.0:
            act = f"비중 {abs(diff_w):.1f}%p 축소 권장" if diff_w < 0 else f"비중 {abs(diff_w):.1f}%p 확대 여력"
            rebal_actions.append(f"<b>{p['ticker']}</b>: 현재 {cur_w}% → 권장 {opt_w}% ({act})")
    return {"total_val": round(total_val, 2), "ann_vol": round(ann_vol, 2),
            "sharpe": round(sharpe, 2), "beta": round(beta, 2),
            "var_95_pct": round(var_95_pct, 2), "var_95_usd": round(abs(var_95_pct / 100.0) * total_val, 2),
            "var_99_pct": round(var_99_pct, 2), "cvar_95_pct": round(cvar_95_pct, 2),
            "cvar_95_usd": round(abs(cvar_95_pct / 100.0) * total_val, 2),
            "hhi": round(hhi, 1), "corr_matrix": corr_matrix, "weights_table": weights_table,
            "rebal_actions": rebal_actions,
            "stress_5pct_usd": round(total_val * 0.05 * beta, 1),
            "stress_10pct_usd": round(total_val * 0.10 * beta, 1)}


# ==============================================================================
# 14) TAB 1: 개별 종목 분석
# ==============================================================================
def render_tab_analysis(indices, usd_krw):
    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = "IREN"
    c_inp, c1, c2, c3, c4, c5, c6 = st.columns([2.5, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8])
    with c_inp:
        ticker_input = st.text_input("종목 코드 입력", value=st.session_state.selected_ticker,
                                     label_visibility="collapsed", placeholder="예: TSLA")
        ticker = ticker_input.upper().strip()
    chips = [(c1, "NVDA"), (c2, "TSLA"), (c3, "PLTR"), (c4, "MSTR"), (c5, "IREN"), (c6, "IONQ")]
    for col, q in chips:
        with col:
            if st.button(q, key=f"chip_{q}", use_container_width=True):
                st.session_state.selected_ticker = q
                st.rerun()
    if not ticker:
        return
    safe_ticker = html.escape(ticker)
    hist = get_history(ticker)
    if hist.empty or len(hist) < 25:
        st.warning(f"'{safe_ticker}' 데이터가 없습니다.")
        return
    hist = hist.copy()
    current_price = safe_float(hist['Close'].iloc[-1], 0.0)
    prev_close = safe_float(hist['Close'].iloc[-2], current_price)
    if current_price <= 0:
        st.warning(f"'{safe_ticker}' 데이터 비정상")
        return
    change = current_price - prev_close
    change_pct = (change / prev_close) * 100 if prev_close > 0 else 0.0
    hist['EMA10'] = hist['Close'].ewm(span=10, adjust=False).mean()
    hist['EMA20'] = hist['Close'].ewm(span=20, adjust=False).mean()
    hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()
    hist['EMA200'] = hist['Close'].ewm(span=200, adjust=False).mean()
    hist['Box_High'] = hist['High'].rolling(20).max()
    hist['Box_Low'] = hist['Low'].rolling(20).min()
    hist['BB_Mid'] = hist['Close'].rolling(20).mean()
    hist['BB_Std'] = hist['Close'].rolling(20).std().fillna(0.0)
    hist['BB_Upper'] = hist['BB_Mid'] + 2 * hist['BB_Std']
    hist['BB_Lower'] = hist['BB_Mid'] - 2 * hist['BB_Std']
    hist['Typical'] = (hist['High'] + hist['Low'] + hist['Close']) / 3
    vc = hist['Volume'].cumsum().replace(0, np.nan)
    vr5 = hist['Volume'].rolling(5).sum().replace(0, np.nan)
    hist['VWAP_Year'] = ((hist['Typical'] * hist['Volume']).cumsum() / vc).bfill().fillna(hist['Close'])
    hist['VWAP_Week'] = ((hist['Typical'] * hist['Volume']).rolling(5).sum() / vr5).bfill().fillna(hist['Close'])
    hist['Vol_MA20'] = hist['Volume'].rolling(20).mean().fillna(0.0)
    hist['RSI'] = compute_wilder_rsi(hist['Close'], 14)
    ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
    ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
    hist['MACD'] = ema12 - ema26
    hist['MACD_Signal'] = hist['MACD'].ewm(span=9, adjust=False).mean()
    hist['MACD_Hist'] = hist['MACD'] - hist['MACD_Signal']
    ema10 = safe_float(hist['EMA10'].iloc[-1], current_price)
    ema20 = safe_float(hist['EMA20'].iloc[-1], current_price)
    ema50 = safe_float(hist['EMA50'].iloc[-1], current_price)
    ema200 = safe_float(hist['EMA200'].iloc[-1], ema50) if len(hist) >= 200 else ema50
    box_high = safe_float(hist['Box_High'].iloc[-1], current_price)
    box_low = safe_float(hist['Box_Low'].iloc[-1], current_price)
    rsi = safe_float(hist['RSI'].iloc[-1], 50.0)
    avg_vol = safe_float(hist['Vol_MA20'].iloc[-1], 0.0)
    curr_vol = safe_float(hist['Volume'].iloc[-1], 0.0)
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
    vwap_year_val = safe_float(hist['VWAP_Year'].iloc[-1], current_price)
    vwap_week_val = safe_float(hist['VWAP_Week'].iloc[-1], current_price)
    bb_upper_val = safe_float(hist['BB_Upper'].iloc[-1], current_price)
    bb_lower_val = safe_float(hist['BB_Lower'].iloc[-1], current_price)
    bb_mid_val = safe_float(hist['BB_Mid'].iloc[-1], current_price)
    tr1 = hist['High'] - hist['Low']
    tr2 = (hist['High'] - hist['Close'].shift(1)).abs()
    tr3 = (hist['Low'] - hist['Close'].shift(1)).abs()
    atr = safe_float(pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1], current_price * 0.03)
    if atr <= 0:
        atr = current_price * 0.03
    atr_pct = (atr / current_price) * 100
    mkt_cap = get_market_cap(ticker)
    cap_profile = get_stock_cap_and_trailing_profile(ticker, mkt_cap, atr_pct)
    ts_tight_pct = cap_profile['ts_tight_pct']
    ts_core_pct = cap_profile['ts_core_pct']
    fng = get_fear_and_greed_index()
    indices_key = normalize_indices_key(indices)
    use_llm = bool(os.getenv("OPENAI_API_KEY"))
    cat = analyze_macro_and_stock_catalysts(ticker, indices_key, use_llm=use_llm)
    noise_eval = evaluate_holding_noise_filter(ticker, hist)
    short_data = get_short_interest_data(ticker)
    gex_data = get_gamma_wall_and_gex_data(ticker, current_price)
    squeeze_eval = evaluate_squeeze_potential(short_data, gex_data, current_price, box_high, vol_ratio)
    color = "text-red" if change < 0 else "text-green"
    arrow = "▼" if change < 0 else "▲"

    is_oneil = current_price >= box_high and vol_ratio >= 1.5
    oneil_status = "EXPLOSIVE 🚀" if is_oneil else ("VOL-UP 🟢" if vol_ratio >= 1.2 else "WAIT ⚪")
    is_minervini = current_price > ema10 and ema10 > ema20 and ema20 > ema50 and current_price > ema200
    bw = (bb_upper_val - bb_lower_val) / bb_mid_val if bb_mid_val > 0 else 0.0
    bws = (hist['BB_Upper'] - hist['BB_Lower']) / hist['BB_Mid'].replace(0, np.nan)
    avg_bw = safe_float(bws.rolling(20).mean().iloc[-1], bw)
    is_vcp = bw < avg_bw * 0.95 if avg_bw > 0 else False
    minervini_status = "SEPA PASS 🟢" if is_minervini else ("VCP 수축 🟡" if is_vcp else "WAIT ⚪")
    darvas_status = "BOX BREAK 🔥" if current_price >= box_high else ("IN-BOX 🟢" if box_low <= current_price < box_high and current_price >= ema20 else "LOW-BOX 🔴")
    if current_price > ema50 and ema50 > ema200:
        weinstein_stage, weinstein_status = "2단계 상승 국면 (최적 매수)", "STAGE 2 🟢"
    elif current_price < ema50 and ema50 < ema200:
        weinstein_stage, weinstein_status = "4단계 하락 국면 (금지)", "STAGE 4 🔴"
    elif current_price > ema200 and current_price < ema50:
        weinstein_stage, weinstein_status = "3단계 천장 분배 (주의)", "STAGE 3 ⚠️"
    else:
        weinstein_stage, weinstein_status = "1단계 바닥 매집", "STAGE 1 🟡"
    is_panic = current_price < ema20 and rsi <= 25.0
    livermore_status = "PANIC BUY 🟢" if is_panic else ("PIVOT 돌파 🟢" if current_price >= box_high else ("과매도 🟡" if rsi <= 35.0 else "NEUTRAL ⚪"))
    is_tudor = current_price > ema200 and current_price > vwap_year_val
    if is_tudor and current_price > vwap_week_val:
        tudor_status = "기관수급 우위 🟢"
    elif current_price <= bb_lower_val:
        tudor_status = "BB하단 과매도 🟡"
    elif current_price < ema200:
        tudor_status = "200일선 하회 🔴"
    else:
        tudor_status = "수급 공방 ⚪"
    pass_count = sum([1 if (is_oneil or vol_ratio >= 1.2) else 0, 1 if (is_minervini or is_vcp) else 0,
                      1 if (current_price >= box_high or (box_low <= current_price < box_high and current_price >= ema20)) else 0,
                      1 if ("STAGE 2" in weinstein_status or "STAGE 1" in weinstein_status) else 0,
                      1 if (is_panic or current_price >= box_high) else 0, 1 if is_tudor else 0])
    master_score = 40 + pass_count * 10
    if is_oneil: master_score += 10
    if is_panic: master_score += 15
    if current_price < ema20 and not is_panic: master_score -= 20
    master_score = max(0, min(100, master_score))

    if current_price >= box_high and vol_ratio >= 1.5:
        summoned = "👑 [제1명인 소환] 윌리엄 오닐 & 니콜라스 다바스"
        meta_action, meta_badge = "🔥 강력 돌파 매수 (SUPER STRONG BUY)", "badge-green"
        meta_headline = "CANSLIM 거래량 폭발 + 다바스 박스 돌파"
        meta_desc = f"20일 신고가(${box_high:,.2f}) 돌파 + 거래량 {vol_ratio:.1f}배."
        stop_loss = max(box_high * 0.96, current_price - 2 * atr)
        target_1, target_2 = current_price * 1.10, current_price * 1.25
        tp1_ratio, tp2_ratio, hold_ratio = 0.30, 0.40, 0.30
        seed_alloc = "계좌의 20~25%"
        sizing_rule = "1차(30%) 익절 후 손절선을 매수 본전가(BE)로 이동"
    elif current_price >= box_high:
        summoned = "👑 [제2명인 소환] 니콜라스 다바스 & 제시 리버모어"
        meta_action, meta_badge = "📈 피봇 돌파 매수 (TREND BUY)", "badge-green"
        meta_headline = "다바스 박스권 상단 저항 돌파"
        meta_desc = "미너비니 'Sell Half' 법칙에 따라 1차 목표가에서 40% 수익 확정."
        stop_loss = current_price * 0.96
        target_1, target_2 = current_price * 1.07, current_price * 1.15
        tp1_ratio, tp2_ratio, hold_ratio = 0.40, 0.30, 0.30
        seed_alloc = "계좌의 15~20%"
        sizing_rule = "1차(40%) 익절 확정 후 잔여 물량 추세 추종"
    elif current_price < ema20 and rsi <= 25.0:
        summoned = "👑 [제5명인 소환] 래리 코너스 & 폴 튜더 존스"
        meta_action, meta_badge = "🟢 공포 투매 역발상 (PANIC BUY)", "badge-green"
        meta_headline = f"과매도 클라이맥스 (RSI {rsi:.1f})"
        meta_desc = "코너스 '70:30' 익절 법칙."
        stop_loss = current_price * 0.94
        target_1, target_2 = current_price * 1.06, current_price * 1.12
        tp1_ratio, tp2_ratio, hold_ratio = 0.70, 0.30, 0.00
        seed_alloc = "계좌의 10~15%"
        sizing_rule = "1차(+6%) 70% 익절 후 30% 본전 스탑"
    elif is_minervini and current_price > ema10:
        summoned = "👑 [제3명인 소환] 마크 미너비니 & 스탠 와인스타인"
        meta_action, meta_badge = "✅ 주도주 정배열 홀딩 (STRONG HOLD)", "badge-yellow"
        meta_headline = "와인스타인 2단계 + 완벽 정배열"
        meta_desc = "1·2차 30%씩 분할 익절, 40% 코어는 20일선 이탈까지 홀딩."
        stop_loss = ema20 * 0.98
        target_1, target_2 = current_price * 1.08, current_price * 1.18
        tp1_ratio, tp2_ratio, hold_ratio = 0.30, 0.30, 0.40
        seed_alloc = "기존 물량 홀딩"
        sizing_rule = "코어 40%는 20일선 종가 이탈까지 홀딩"
    elif current_price < ema20:
        summoned = "👑 [제4명인 소환] 스탠 와인스타인 & 폴 튜더 존스"
        meta_action, meta_badge = "⚠️ 생명선 이탈 관망 (RISK OFF)", "badge-red"
        meta_headline = f"20일선(${ema20:,.2f}) 이탈 — 방어 모드"
        meta_desc = "튜더 존스 '20일선 방어' 법칙."
        stop_loss = current_price * 0.97
        target_1, target_2 = current_price * 1.03, current_price * 1.05
        tp1_ratio, tp2_ratio, hold_ratio = 0.70, 0.30, 0.00
        seed_alloc = "0% (현금 확보)"
        sizing_rule = "70% 이상 비중 축소, 반등 시 잔량 매도"
    else:
        summoned = "👑 [제6명인 소환] 존 볼린저 & 마크 미너비니"
        meta_action, meta_badge = "⏸️ 변동성 수축 관망 (VCP WAIT)", "badge-blue"
        meta_headline = "볼린저 수축 & 박스 에너지 응축"
        meta_desc = "박스 수렴 구간. 정찰병 소액 진입 후 돌파 시 확대."
        stop_loss = box_low * 0.98
        target_1, target_2 = current_price * 1.05, current_price * 1.10
        tp1_ratio, tp2_ratio, hold_ratio = 0.50, 0.30, 0.20
        seed_alloc = "계좌의 5~10%"
        sizing_rule = "박스 상단 50% 익절, 돌파 시 잔량 홀딩"

    grand = int(np.clip(master_score + cat['macro_score'] + cat['catalyst_score'] + squeeze_eval['bonus'], 0, 100))
    has_macro_crisis = cat['macro_score'] <= -15
    has_bad = cat['bad_news_hits'] >= 2
    has_good = cat['contract_hits'] >= 1 or cat['earnings_bull_hits'] >= 1

    if has_bad and current_price < ema20:
        fv_title, fv_color = "🚨 [최종 결론] 개별 악재 + 추세 이탈 — 진입 금지", "#f43f5e"
        fv_summary = f"악재 {cat['bad_news_hits']}건 + 20일선 이탈. 물타기 중단, 현금 수성."
    elif has_macro_crisis and "BUY" in meta_action:
        fv_title, fv_color = "⚠️ [최종 결론] 차트 돌파지만 매크로 경보 — 시드 50% 축소", "#f59e0b"
        fv_summary = f"매크로 경보 발령. 시드 절반만 진입 + 타이트 스탑(-{ts_tight_pct:.1f}%)."
    elif cat['earnings_imminent'] and "BUY" in meta_action:
        fv_title, fv_color = f"⚡ [최종 결론] {cat['earnings_info']} — 분할 대응", "#fbbf24"
        fv_summary = "실적 직전 풀시드 금지. 선취매 50%만 유지."
    elif grand >= 75 and ("BUY" in meta_action or "HOLD" in meta_action):
        fv_title, fv_color = "🏆 [최종 결론] 매크로 안정 + 6대 대가 승인", "#10b981"
        bonus = "스퀴즈 모멘텀 가세 + " if squeeze_eval['bonus'] >= 5 else ""
        fv_summary = f"{bonus}종합 {grand}점. {seed_alloc} 진입 후 1차(${target_1:,.2f}) {int(tp1_ratio*100)}% 익절, 코어 트레일링 -{ts_core_pct:.1f}%."
    elif "PANIC" in meta_action:
        fv_title, fv_color = "🟢 [최종 결론] 극단 공포 투매 클라이맥스", "#34d399"
        fv_summary = f"RSI {rsi:.1f}. 1차 반등(${target_1:,.2f}) 시 70% 수익 확정."
    elif current_price < ema20:
        fv_title, fv_color = "🛡️ [최종 결론] 추세 약세 — 현금 확보", "#f43f5e"
        fv_summary = f"20일선(${ema20:,.2f}) 이탈. 회복 전 보수적 대응."
    else:
        fv_title, fv_color = "🧭 [최종 결론] 에너지 응축 · 추세 지속", "#38bdf8"
        fv_summary = f"종합 {grand}점. 박스 하단(${box_low:,.2f}) 방어, 상단(${box_high:,.2f}) 돌파 시 확대."

    ts_from_curr_tight = current_price * (1 - ts_tight_pct / 100)
    ts_from_curr_core = current_price * (1 - ts_core_pct / 100)
    ts_from_high_core = box_high * (1 - ts_core_pct / 100)

    render_html(f"""
    <div class="main-hero-card">
        <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
            <span style="font-size:24px; font-weight:800; color:#fff;">{safe_ticker}</span>
            <span class="badge {cap_profile['cap_badge']}">{cap_profile['cap_tier']}</span>
            <span class="badge {meta_badge}">{meta_action.split('(')[0].strip()}</span>
            <span class="badge badge-purple">종합 {grand}점</span>
            <span class="badge {squeeze_eval['badge']}">스퀴즈 {squeeze_eval['sq_score']}점</span>
        </div>
        <div style="font-size:30px; font-weight:800; font-family:'JetBrains Mono'; margin:6px 0;" class="{color}">
            ${current_price:,.2f} <span style="font-size:16px;">{arrow} ${abs(change):,.2f} ({change_pct:+.2f}%)</span>
        </div>
        <div style="color:#94a3b8; font-size:12px;">
            {cap_profile['cap_desc']} | ATR: <b class="text-white">${atr:.2f} ({atr_pct:.1f}%)</b> | 거래량: <b class="text-white">{vol_ratio:.1f}x</b> | Wilder RSI: <b class="text-white">{rsi:.1f}</b>
        </div>
    </div>""")

    mb = "".join([f"<div style='margin-bottom:2px;'>• {html.escape(m)}</div>" for m in cat['macro_alerts']])
    cb = "".join([f"<div style='margin-bottom:2px;'>• {html.escape(c)}</div>" for c in cat['catalyst_summary']])
    render_html(f"""
    <div class="verdict-card" style="border-color:{fv_color};">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,.12); padding-bottom:8px;">
            <span style="font-size:15px; font-weight:800; color:{fv_color};">{fv_title}</span>
            <span class="badge badge-indigo">{cat['earnings_info']}</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:10px;">
            <div style="background:rgba(0,0,0,.4); padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.08);">
                <div style="font-size:11px; font-weight:800; color:#38bdf8; margin-bottom:4px;">🌍 ① 거시·지정학</div>
                <div style="font-size:10px; color:#cbd5e1; line-height:1.45;">{mb}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.08);">
                <div style="font-size:11px; font-weight:800; color:#a855f7; margin-bottom:4px;">🏢 ② 실적·계약·악재</div>
                <div style="font-size:10px; color:#cbd5e1; line-height:1.45;">{cb}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.08);">
                <div style="font-size:11px; font-weight:800; color:#fbbf24; margin-bottom:4px;">👑 ③ 6대 대가 + 스퀴즈</div>
                <div style="font-size:10px; color:#cbd5e1; line-height:1.45;">
                    • 6대 거장: <b class="text-white">{pass_count}/6 ({master_score}점)</b><br>
                    • 스퀴즈 가산: <b class="text-orange">+{squeeze_eval['bonus']}점</b>
                </div>
            </div>
        </div>
        <div style="background:rgba(15,23,42,.85); border-left:4px solid {fv_color}; padding:10px 14px; border-radius:8px;">
            <div style="font-size:12px; font-weight:700; color:#f8fafc; line-height:1.6;">
                💡 <b>AI 펀드매니저 지침:</b> {html.escape(fv_summary)}
            </div>
        </div>
    </div>""")

    call_wall = gex_data.get("call_wall")
    put_wall = gex_data.get("put_wall")
    max_pain = gex_data.get("max_pain")
    sq_reasons_str = " / ".join(squeeze_eval["reasons"])
    render_html(f"""
    <div class="squeeze-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(249,115,22,.3); padding-bottom:8px;">
            <span style="font-size:14px; font-weight:800; color:#fb923c;">🔥 숏스퀴즈 & 옵션 감마스퀴즈 레이더</span>
            <span class="badge {squeeze_eval['badge']}">{squeeze_eval['grade']} ({squeeze_eval['sq_score']}/100)</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; text-align:center; font-family:'JetBrains Mono'; margin-bottom:10px;">
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">공매도 비중</div>
                <div style="font-size:14px; font-weight:800; color:#fb923c;">{short_data['short_pct']:.1f}%</div>
                <div style="font-size:9px; color:#64748b;">20%↑ 과열</div>
            </div>
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">커버일수</div>
                <div style="font-size:14px; font-weight:800; color:#fbbf24;">{short_data['days_to_cover']:.1f}일</div>
                <div style="font-size:9px; color:#64748b;">Short Ratio</div>
            </div>
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">Call/Put OI</div>
                <div style="font-size:14px; font-weight:800; color:#38bdf8;">{gex_data['cp_oi_ratio']:.2f}x</div>
                <div style="font-size:9px; color:#64748b;">콜 우위</div>
            </div>
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">콜벽/맥스페인</div>
                <div style="font-size:13px; font-weight:800; color:#10b981;">{f'${call_wall:,.1f}' if call_wall else 'N/A'} / {f'${max_pain:,.1f}' if max_pain else 'N/A'}</div>
                <div style="font-size:9px; color:#64748b;">풋지지 {f'${put_wall:,.1f}' if put_wall else 'N/A'}</div>
            </div>
        </div>
        <div style="font-size:11px; color:#cbd5e1; line-height:1.55;">
            • <b>GEX 판정:</b> <span class="text-white">{gex_data['gex_status']}</span> ({html.escape(sq_reasons_str)})<br>
            • <b>대응:</b> {squeeze_eval['guide']}
        </div>
    </div>""")

    if noise_eval:
        nb_color = "#10b981" if noise_eval['noise_used_ratio'] < 55 else ("#f59e0b" if noise_eval['noise_used_ratio'] < 85 else "#f43f5e")
        render_html(f"""
        <div class="noise-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
                <span style="font-size:14px; font-weight:800; color:#2dd4bf;">🌊 보유주 노이즈 필터</span>
                <span class="badge {noise_eval['badge']}">{noise_eval['signal']} | {noise_eval['wave_status']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1; margin-bottom:4px;">
                <span>20일 고점(${box_high:,.2f}) 대비: <b class="mono text-white">{noise_eval['drawdown_from_high_pct']:+.1f}%</b> (한계: <b class="mono text-yellow">-{ts_core_pct:.1f}%</b>)</span>
                <span>소진율: <b class="mono" style="color:{nb_color};">{noise_eval['noise_used_ratio']:.0f}%</b></span>
            </div>
            <div style="width:100%; height:9px; background:#090d16; border-radius:6px; overflow:hidden; margin-bottom:8px; border:1px solid #1e293b;">
                <div style="width:{min(100, max(4, noise_eval['noise_used_ratio']))}%; height:100%; background:{nb_color};"></div>
            </div>
            <div style="font-size:11px; color:#e2e8f0; line-height:1.5;">
                • <b>진단:</b> {noise_eval['headline']}<br>
                • <b>지침:</b> {noise_eval['action_guide']}
            </div>
        </div>""")

    render_html(f"""
    <div class="sentiment-card">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
            <span style="font-size:14px; font-weight:800; color:#a5b4fc;">🧭 CNN Fear & Greed Index</span>
            <span class="badge {fng['badge_cls']}">{fng['kr_label']} ({fng['score']}/100)</span>
        </div>
        <div style="width:100%; height:10px; background:#0f172a; border-radius:6px; overflow:hidden; margin-bottom:8px; border:1px solid #312e81;">
            <div style="width:{min(100, max(5, fng['score']))}%; height:100%; background:{fng['bar_color']};"></div>
        </div>
        <div style="font-size:11px; color:#e0e7ff; line-height:1.5;">• <b>코칭:</b> {fng['advice']}</div>
    </div>""")

    render_html(f"""
    <div class="master-card">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:12px; border-bottom:1px solid rgba(245,158,11,.3); padding-bottom:8px;">
            <span style="font-size:15px; font-weight:800; color:#fbbf24;">{summoned}</span>
            <span style="font-size:11px; color:#cbd5e1; background:rgba(245,158,11,.2); padding:3px 8px; border-radius:6px; font-weight:700;">{weinstein_stage}</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:12px;">
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">① 오닐</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{oneil_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">② 미너비니</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{minervini_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">③ 다바스</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{darvas_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">④ 와인스타인</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{weinstein_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">⑤ 리버모어</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{livermore_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">⑥ 튜더존스</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{tudor_status}</div>
            </div>
        </div>
        <div style="background:rgba(0,0,0,.45); border-left:3px solid #f59e0b; padding:10px 14px; border-radius:6px; margin-bottom:12px;">
            <div style="font-size:13px; font-weight:800; color:#fef08a;">{meta_headline}</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:3px; line-height:1.5;">{meta_desc}</div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; text-align:center; font-family:'JetBrains Mono'; margin-bottom:10px;">
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px;">
                <div style="font-size:10px; color:#94a3b8;">박스 하단</div>
                <div style="font-size:13px; font-weight:800; color:#10b981;">${box_low:,.2f}</div>
            </div>
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px;">
                <div style="font-size:10px; color:#94a3b8;">타이트 손절</div>
                <div style="font-size:13px; font-weight:800; color:#f43f5e;">${stop_loss:,.2f}</div>
            </div>
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px; border:1px solid rgba(56,189,248,.25);">
                <div style="font-size:10px; color:#94a3b8;">1차({int(tp1_ratio*100)}%)</div>
                <div style="font-size:13px; font-weight:800; color:#38bdf8;">${target_1:,.2f}</div>
            </div>
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px; border:1px solid rgba(168,85,247,.25);">
                <div style="font-size:10px; color:#94a3b8;">2차({int(tp2_ratio*100)}%)</div>
                <div style="font-size:13px; font-weight:800; color:#a855f7;">${target_2:,.2f}</div>
            </div>
        </div>
        <div style="background:rgba(15,23,42,.75); border:1px solid rgba(245,158,11,.35); border-radius:8px; padding:9px 12px; font-size:11px;">
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px; margin-bottom:4px;">
                <span style="color:#fbbf24; font-weight:800;">⚖️ 분할: 1차({int(tp1_ratio*100)}%) : 2차({int(tp2_ratio*100)}%) : 홀딩({int(hold_ratio*100)}%)</span>
                <span style="color:#38bdf8; font-weight:700;">시드: {seed_alloc}</span>
            </div>
            <div style="color:#cbd5e1;">• <b>수칙:</b> {sizing_rule}</div>
        </div>
    </div>""")

    render_html(f"""
    <div class="trailing-card">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(56,189,248,.25); padding-bottom:8px;">
            <span style="font-size:14px; font-weight:800; color:#38bdf8;">🛡️ 미래에셋 트레일링 스탑</span>
            <span class="badge {cap_profile['cap_badge']}">{cap_profile['cap_tier']} | ATR {atr_pct:.1f}%</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; text-align:center;">
            <div style="background:rgba(0,0,0,.4); border:1px solid rgba(56,189,248,.3); padding:10px 6px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">① 단기</div>
                <div style="font-size:18px; font-weight:800; color:#38bdf8; font-family:'JetBrains Mono';">-{ts_tight_pct:.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">${ts_from_curr_tight:,.2f}</div>
            </div>
            <div style="background:rgba(16,185,129,.1); border:1px solid #10b981; padding:10px 6px; border-radius:8px;">
                <div style="font-size:10px; color:#34d399;">② 중기</div>
                <div style="font-size:18px; font-weight:800; color:#10b981; font-family:'JetBrains Mono';">-{ts_core_pct:.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">${ts_from_curr_core:,.2f}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); border:1px solid rgba(168,85,247,.3); padding:10px 6px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">③ 샹들리에</div>
                <div style="font-size:18px; font-weight:800; color:#c084fc; font-family:'JetBrains Mono';">${ts_from_high_core:,.2f}</div>
                <div style="font-size:10px; color:#cbd5e1;">20일 고점 대비</div>
            </div>
        </div>
    </div>""")

    with st.expander("💰 수익 & 분할익절 계산기", expanded=False):
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            buy_price = st.number_input("평단($)", value=float(round(current_price, 2)), step=0.1)
        with col_b2:
            qty = st.number_input("수량(주)", value=100.0, step=10.0)
        with col_b3:
            fee_rate = st.selectbox("수수료", options=[0.0007, 0.001, 0.0025, 0.0],
                                    format_func=lambda x: f"{x*100:.2f}%" if x > 0 else "무료", index=2)
        if buy_price > 0 and qty > 0:
            invest_usd = buy_price * qty
            current_usd = current_price * qty
            fee_usd = (invest_usd + current_usd) * fee_rate
            net_usd = (current_usd - invest_usd) - fee_usd
            net_krw = net_usd * usd_krw
            roi_pct = (net_usd / invest_usd) * 100.0
            p_color = "text-green" if net_usd >= 0 else "text-red"
            qty_tp1 = int(round(qty * tp1_ratio))
            qty_tp2 = int(round(qty * tp2_ratio))
            qty_hold = max(0, int(qty) - qty_tp1 - qty_tp2)
            p_tp1 = (target_1 - buy_price) * qty_tp1 * (1 - fee_rate)
            p_tp2 = (target_2 - buy_price) * qty_tp2 * (1 - fee_rate)
            render_html(f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px; margin-top:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:700; font-size:13px;">순손익:</span>
                    <span class="{p_color} mono" style="font-size:16px; font-weight:800;">${net_usd:,.2f} ({roi_pct:+.2f}%) / {net_krw:+,.0f}원</span>
                </div>
                <hr style="margin:8px 0;">
                <div style="font-size:11px; color:#cbd5e1; line-height:1.6;">
                    • <b>1차 (${target_1:,.2f}):</b> {qty_tp1}주 → <b class="text-green">+${p_tp1:,.1f}</b><br>
                    • <b>2차 (${target_2:,.2f}):</b> {qty_tp2}주 → <b class="text-green">+${p_tp2:,.1f}</b><br>
                    • <b>코어:</b> {qty_hold}주 → 트레일링 -{ts_core_pct:.1f}%
                </div>
            </div>""")
            b_save1, b_save2 = st.columns(2)
            with b_save1:
                if st.button("💾 보유주식 DB에 저장", use_container_width=True):
                    db_upsert_holding(ticker, buy_price, qty, 15.0, 7.0)
                    st.success(f"{ticker} 저장 완료!")
            with b_save2:
                if st.button("📓 매매일지에 기록", use_container_width=True):
                    db_add_journal_entry(datetime.now().strftime("%Y-%m-%d"), ticker, "익절/청산",
                                         current_price, qty, round(net_usd, 2),
                                         summoned.split("]")[1].strip() if "]" in summoned else "6대 대가",
                                         "원칙준수", f"평단 ${buy_price:,.2f} → ${current_price:,.2f} ({roi_pct:+.1f}%)")
                    st.success(f"{ticker} 매매일지 기록 완료!")

    col_c1, col_c2, col_c3 = st.columns([1, 1, 1.5])
    with col_c1: show_vwap_y = st.checkbox("1년 VWAP", value=True)
    with col_c2: show_vwap_w = st.checkbox("5일 VWAP", value=False)
    with col_c3: show_gamma = st.checkbox("감마벽 라인", value=True)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.15, 0.15, 0.15],
                        subplot_titles=(f"{ticker} 가격 & 추세", "거래량", "MACD", "Wilder RSI(14)"))
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                                 increasing_line_color='#10b981', decreasing_line_color='#f43f5e',
                                 increasing_fillcolor='#10b981', decreasing_fillcolor='#f43f5e'), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA10'], line=dict(color='#38bdf8', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'], line=dict(color='#fbbf24', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'], line=dict(color='#a855f7', width=1.2, dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['Box_High'], line=dict(color='#ef4444', width=1, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['Box_Low'], line=dict(color='#10b981', width=1, dash='dash')), row=1, col=1)
    if show_vwap_y:
        fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Year'], line=dict(color='#f97316', width=1.2)), row=1, col=1)
    if show_vwap_w:
        fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Week'], line=dict(color='#ec4899', width=1.2)), row=1, col=1)
    if show_gamma and call_wall:
        fig.add_hline(y=call_wall, line=dict(color="#f43f5e", width=1.5, dash="dash"), row=1, col=1)
    if show_gamma and put_wall:
        fig.add_hline(y=put_wall, line=dict(color="#10b981", width=1.5, dash="dash"), row=1, col=1)
    vcolors = ['#10b981' if c >= o else '#f43f5e' for c, o in zip(hist['Close'], hist['Open'])]
    fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=vcolors, opacity=0.8), row=2, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['Vol_MA20'], line=dict(color='#94a3b8', width=1)), row=2, col=1)
    mcolors = ['#10b981' if v >= 0 else '#f43f5e' for v in hist['MACD_Hist']]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_Hist'], marker_color=mcolors), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'], line=dict(color='#38bdf8', width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_Signal'], line=dict(color='#fbbf24', width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], line=dict(color='#a855f7', width=1.5)), row=4, col=1)
    fig.add_hline(y=70, line=dict(color="rgba(244,63,94,0.7)", width=1, dash="dot"), row=4, col=1)
    fig.add_hline(y=30, line=dict(color="rgba(16,185,129,0.7)", width=1, dash="dot"), row=4, col=1)
    fig.add_hline(y=25, line=dict(color="#10b981", width=1.5, dash="dash"), row=4, col=1)
    fig.update_layout(template="plotly_dark", height=660, margin=dict(l=30, r=30, t=30, b=20),
                      xaxis_rangeslider_visible=False, showlegend=False,
                      paper_bgcolor="#080c14", plot_bgcolor="#080c14", hovermode="x unified")
    fig.update_xaxes(gridcolor="#1e293b", showgrid=True)
    fig.update_yaxes(gridcolor="#1e293b", showgrid=True)
    st.plotly_chart(fig, use_container_width=True)

    render_html("""<div style="font-weight:700; color:#38bdf8; font-size:13px; margin:14px 0 8px 0;">📰 실시간 뉴스 & AI 판독</div>""")
    for n in cat['news_items']:
        render_html(f"""
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:10px 14px; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <span class="badge {n['badge_class']}">{n['sentiment']}</span>
                <span style="font-size:10px; color:#64748b;">{n['date']}</span>
            </div>
            <a href="{n['link']}" target="_blank" rel="noopener noreferrer" style="color:#e2e8f0; font-size:12px; font-weight:700; text-decoration:none;">{n['title']}</a>
        </div>""")


# ==============================================================================
# 15) TAB 2: 보유 모니터 (v14: 신호 발생 시 자동 예약)
# ==============================================================================
def render_tab_holdings_monitor(usd_krw):
    render_html("""
    <div style="margin-bottom:12px;">
        <div style="font-size:18px; font-weight:800; color:#fff;">🛡️ 보유주식 노이즈 필터 모니터 & AI 리밸런싱</div>
        <div style="font-size:12px; color:#94a3b8; margin-top:2px;">
            작은 파도는 무시, 큰 변곡점만 포착. <b>신호 발생 시 봇 승률 자동 검증 예약</b>.
        </div>
    </div>""")
    with st.expander("➕ 종목 추가/삭제 & 📲 텔레그램", expanded=False):
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.1, 1.1, 1.1])
        with c1: in_t = st.text_input("티커", value="NVDA", key="db_t").upper().strip()
        with c2: in_bp = st.number_input("평단($)", value=125.0, min_value=0.0, step=0.5, key="db_bp")
        with c3: in_q = st.number_input("수량(주)", value=50.0, min_value=0.0, step=1.0, key="db_q")
        with c4: in_tr = st.number_input("목표수익(%)", value=15.0, min_value=1.0, step=1.0, key="db_tr")
        with c5: in_sl = st.number_input("손절폭(%)", value=7.0, min_value=1.0, step=0.5, key="db_sl")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 저장", use_container_width=True, type="primary"):
                db_upsert_holding(in_t, in_bp, in_q, in_tr, in_sl)
                st.rerun()
        with b2:
            if st.button("🗑️ 삭제", use_container_width=True):
                db_delete_holding(in_t)
                st.rerun()
        with b3:
            auto_ref = st.checkbox("60초 자동", value=False)
            if auto_ref and HAS_AUTOREFRESH:
                st_autorefresh(interval=60_000, key="holdings_autorefresh")
        st.markdown("---")
        tcol1, tcol2 = st.columns(2)
        with tcol1: tg_token = st.text_input("Bot Token", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
        with tcol2: tg_chat = st.text_input("Chat ID", value=os.getenv("TELEGRAM_CHAT_ID", ""))
    holdings = db_get_holdings()
    if not holdings:
        st.info("등록된 보유 종목이 없습니다.")
        if st.button("🧪 샘플 (IREN·NVDA·TSLA·PLTR) 로드"):
            for sym, bp, q in [("IREN", 12.5, 200), ("NVDA", 125.0, 50), ("TSLA", 240.0, 40), ("PLTR", 42.0, 100)]:
                db_upsert_holding(sym, bp, q, 15.0, 7.0)
            st.rerun()
        return
    eval_list = []
    for h in holdings:
        res = evaluate_holding_noise_filter_cached(
            ticker=h["ticker"], buy_price=h["buy_price"], qty=h["qty"],
            target_roi_pct=h["target_roi"], custom_stop_pct=h["stop_loss_pct"])
        if res:
            eval_list.append(res)
            # v14: severity >= 2 신호는 자동 검증 예약
            if res['severity'] >= 2:
                db_register_signal_for_eval(res['ticker'], res['signal'], res['curr_price'])
    eval_list.sort(key=lambda x: (-x['severity'], -abs(x['day_chg_pct'])))
    urgent_list = [x for x in eval_list if x['severity'] >= 3]
    watch_cnt = sum(1 for x in eval_list if x['severity'] == 2)
    calm_cnt = sum(1 for x in eval_list if x['severity'] <= 1)
    total_pnl_usd = sum(x['pnl_usd'] for x in eval_list)
    pnl_color = "#10b981" if total_pnl_usd >= 0 else "#f43f5e"
    cut_candidates = [x['ticker'] for x in eval_list if x['severity'] >= 4]
    tp_candidates = [x['ticker'] for x in eval_list if x['severity'] == 3]
    strong_leaders = [x['ticker'] for x in eval_list if x['signal'] == SIGNAL_HOLD_LONG]
    rebal_msgs = []
    if cut_candidates:
        rebal_msgs.append(f"🔴 <b>즉시 축소/청산:</b> {', '.join(cut_candidates)}")
    if tp_candidates:
        rebal_msgs.append(f"🔵 <b>분할 익절 대상:</b> {', '.join(tp_candidates)}")
    if strong_leaders:
        rebal_msgs.append(f"🟢 <b>코어 홀딩:</b> {', '.join(strong_leaders)}")
    if not rebal_msgs:
        rebal_msgs.append("⚖️ 전 종목 허용 노이즈 범위 내 등락 — 기존 비중 유지.")
    render_html(f"""
    <div class="rebal-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
            <span style="font-size:14px; font-weight:800; color:#c084fc;">🔄 AI 리밸런싱 & 자금 재배치</span>
            <span class="mono" style="font-size:13px; font-weight:800; color:{pnl_color};">
                총 평가손익: ${total_pnl_usd:+,.2f} ({total_pnl_usd*usd_krw:+,.0f}원)
            </span>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;">
            <span class="badge badge-red">🚨 행동요망: {len(urgent_list)}</span>
            <span class="badge badge-yellow">🟠 경계: {watch_cnt}</span>
            <span class="badge badge-green">🌊 홀딩: {calm_cnt}</span>
        </div>
        <div style="font-size:11px; color:#e9d5ff; line-height:1.55;">
            {"<br>".join(f"• {m}" for m in rebal_msgs)}
        </div>
    </div>""")
    if st.button("📲 텔레그램 리포트 전송", use_container_width=True):
        lines = [f"⚡ [GANGJIN] 리포트 ({datetime.now().strftime('%H:%M')})"]
        for it in eval_list:
            lines.append(f"• {it['ticker']}: {it['signal']} | ${it['curr_price']:,.2f} ({it['roi_pct']:+.1f}%) | 청산 ${it['chandelier_stop']:,.2f}")
            if it['severity'] >= 3:
                db_log_alert(it['ticker'], it['signal'], it['curr_price'], it['headline'])
        ok, msg = send_telegram_alert("\n".join(lines), tg_token, tg_chat)
        if ok: st.success(msg)
        else: st.warning(msg)
    for item in eval_list:
        d_col = "#10b981" if item['day_chg_pct'] >= 0 else "#f43f5e"
        r_col = "#10b981" if item['roi_pct'] >= 0 else "#f43f5e"
        nb_col = "#10b981" if item['noise_used_ratio'] < 55 else ("#f59e0b" if item['noise_used_ratio'] < 85 else "#f43f5e")
        border_col = "#f43f5e" if item['severity'] >= 4 else ("#3b82f6" if item['severity'] == 3 else ("#f59e0b" if item['severity'] == 2 else "#1e293b"))
        render_html(f"""
        <div style="background:#0f172a; border:1.5px solid {border_col}; border-radius:12px; padding:14px 16px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span style="font-size:18px; font-weight:800; font-family:'JetBrains Mono'; color:#fff;">{item['ticker']}</span>
                    <span class="badge {item['badge']}">{item['signal']}</span>
                    <span style="font-size:11px; color:#94a3b8; font-weight:700;">{item['wave_status']}</span>
                </div>
                <div class="mono" style="text-align:right;">
                    <span style="font-size:16px; font-weight:800; color:#fff;">${item['curr_price']:,.2f}</span>
                    <span style="font-size:12px; font-weight:700; color:{d_col}; margin-left:6px;">({item['day_chg_pct']:+.2f}%)</span>
                </div>
            </div>
            <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; text-align:center; font-family:'JetBrains Mono'; background:rgba(0,0,0,.35); padding:8px; border-radius:8px; margin-bottom:8px; font-size:11px;">
                <div><div style="color:#64748b; font-size:9px;">평단/수익</div><div style="color:{r_col}; font-weight:800;">${item['buy_price']:,.2f} ({item['roi_pct']:+.1f}%)</div></div>
                <div><div style="color:#64748b; font-size:9px;">ATR</div><div style="color:#e2e8f0; font-weight:700;">±{item['atr_pct']:.1f}%</div></div>
                <div><div style="color:#64748b; font-size:9px;">샹들리에</div><div style="color:#f43f5e; font-weight:800;">${item['chandelier_stop']:,.2f}</div></div>
                <div><div style="color:#64748b; font-size:9px;">EMA20/RSI</div><div style="color:#38bdf8; font-weight:700;">${item['ema20']:,.2f}|{item['rsi']:.0f}</div></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:10px; color:#94a3b8; margin-bottom:3px;">
                <span>낙폭: <b class="text-white">{item['drawdown_from_high_pct']:+.1f}%</b></span>
                <span>소진: <b style="color:{nb_col};">{item['noise_used_ratio']:.0f}%</b></span>
            </div>
            <div style="width:100%; height:7px; background:#090d16; border-radius:4px; overflow:hidden; margin-bottom:8px;">
                <div style="width:{min(100, max(4, item['noise_used_ratio']))}%; height:100%; background:{nb_col};"></div>
            </div>
            <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
                • <b style="color:#fef08a;">{item['headline']}</b><br>
                • <b>지침:</b> {item['action_guide']}
            </div>
        </div>""")


# ==============================================================================
# 16) TAB 3: 스캐너
# ==============================================================================
def render_tab_scanner():
    render_html("""
    <div style="margin-bottom:12px;">
        <div style="font-size:18px; font-weight:800; color:#fff;">🎯 100종목 스캐너</div>
        <div style="font-size:12px; color:#94a3b8; margin-top:2px;">6대 거장 + Wilder RSI + ATR 트레일링 스탑</div>
    </div>""")
    presets = {
        "🔥 서학개미 Top 100": "NVDA TSLA AAPL MSFT AMZN GOOGL META PLTR AMD COIN MSTR SOXL TQQQ SMCI MARA RIOT IREN CLSK IONQ RKLB ASTS ARM TSM AVGO CRWD PANW NFLX DIS INTC SOFI HOOD OPEN LCID RIVN U RBLX SNOW BABA NIO XPEV LI BIDU PDD BILI UPST AFRM SQ PYPL SHOP SE CPNG PATH AI PLUG ENPH SEDG FCEL CHPT BLNK QS DKNG PENN WYNN LVS CCL RCL NCLH UAL DAL AAL LUV BA RTX LMT GD NOC XOM CVX OXY SLB HAL COP F GM TM HMC NKE LULU SBUX MCD KO PEP PG JNJ PFE MRK LLY UNH ABBV",
        "🤖 AI & 반도체": "NVDA AMD TSM AVGO ARM ASML QCOM MU INTC MRVL AMAT LRCX KLAC ON NXPI ADI MPWR SMCI",
        "⚡ 양자 & 우주": "IONQ RGTI QBTS QUBT RKLB LUNR ASTS PL RDYW BKSY SPIR",
        "💎 크립토": "MSTR COIN MARA RIOT IREN CLSK CIFR HUT BITF CORZ WULF BTDR",
    }
    p1, p2 = st.columns([1, 2])
    with p1: sel = st.selectbox("프리셋", list(presets.keys()), key="s_preset")
    with p2: txt = st.text_area("티커", value=presets[sel], height=70, key="s_txt")
    b1, b2 = st.columns([1, 2])
    with b1: start = st.button("🚀 스캔", type="primary", use_container_width=True)
    with b2: filt = st.radio("필터", ["전체", "🔥 STRONG BUY", "🟢 PANIC BUY", "매수 전체"], horizontal=True, key="s_filt")
    if start or "s_res" in st.session_state:
        if start:
            with st.spinner("스캔 중..."):
                st.session_state.s_res = scan_watchlist(txt)
        data = st.session_state.get("s_res", [])
        if not data:
            st.warning("결과 없음")
            return
        ff = data
        if filt == "🔥 STRONG BUY": ff = [r for r in data if "STRONG" in r['action']]
        elif filt == "🟢 PANIC BUY": ff = [r for r in data if "PANIC" in r['action']]
        elif filt == "매수 전체": ff = [r for r in data if r['is_buy']]
        render_html(f"""<div style="margin:12px 0;font-size:13px;font-weight:700;">총 {len(data)}개 중 <b style="color:#38bdf8;">{len(ff)}개</b> 포착</div>""")
        for it_ in ff:
            cc = "#10b981" if it_['change_pct'] >= 0 else "#f43f5e"
            cs = "+" if it_['change_pct'] >= 0 else ""
            render_html(f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="display:flex; align-items:center; gap:10px; min-width:160px;">
                    <span style="font-size:16px; font-weight:800; font-family:'JetBrains Mono'; color:#fff;">{it_['ticker']}</span>
                    <span class="badge {it_['badge']}">{it_['action']}</span>
                </div>
                <div class="mono" style="text-align:right; min-width:100px;">
                    <div style="font-size:14px; font-weight:800; color:#fff;">${it_['price']:,.2f}</div>
                    <div style="font-size:11px; color:{cc};">{cs}{it_['change_pct']:.2f}%</div>
                </div>
                <div style="font-size:11px; color:#94a3b8; display:flex; gap:12px; flex-wrap:wrap;">
                    <span>RSI <b class="text-white">{it_['rsi']:.1f}</b></span>
                    <span>거래량 <b class="text-white">{it_['vol']:.1f}x</b></span>
                    <span>ATR <b class="text-white">{it_['atr_pct']:.1f}%</b></span>
                    <span>TS <b style="color:#38bdf8;">-{it_['ts_rec']:.1f}%</b></span>
                </div>
            </div>""")
        csv = pd.DataFrame(data).to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 CSV", csv, f"scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")


# ==============================================================================
# 17) TAB 4: 백테스트
# ==============================================================================
def render_tab_backtest():
    render_html("""<div style="margin-bottom:12px;">
    <div style="font-size:18px;font-weight:800;color:#fff;">🧪 전략 백테스트</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:2px;">6대 대가 + 샹들리에 vs Buy&Hold</div>
    </div>""")
    c1, c2, c3 = st.columns([1.5, 1.2, 1.5])
    with c1: bt_t = st.text_input("티커", value="NVDA", key="bt_t").upper().strip()
    with c2: bt_p = st.selectbox("기간", ["1y", "2y", "5y"], index=1)
    with c3: bt_cap = st.number_input("시드($)", value=10000.0, min_value=1000.0, step=1000.0)
    if st.button("🚀 실행", type="primary", use_container_width=True) or "bt_res" not in st.session_state:
        with st.spinner(f"{bt_t} 백테스트 중..."):
            st.session_state.bt_res = run_strategy_backtest(bt_t, bt_p, bt_cap)
    res = st.session_state.get("bt_res", {})
    if not res:
        st.warning("데이터 부족")
        return
    sc = "#10b981" if res['strat_ret'] >= 0 else "#f43f5e"
    bcc = "#10b981" if res['bh_ret'] >= 0 else "#f43f5e"
    render_html(f"""
    <div class="glass-card">
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono';">
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">AI 전략</div>
                <div style="font-size:18px; font-weight:800; color:{sc};">{res['strat_ret']:+.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">${res['final_equity']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">Buy&Hold</div>
                <div style="font-size:18px; font-weight:800; color:{bcc};">{res['bh_ret']:+.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">전략 MDD</div>
                <div style="font-size:18px; font-weight:800; color:#38bdf8;">{res['mdd_strat']:.1f}%</div>
                <div style="font-size:10px; color:#64748b;">보유 {res['mdd_bh']:.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">승률 / 매매</div>
                <div style="font-size:18px; font-weight:800; color:#fbbf24;">{res['win_rate']:.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">{res['total_trades']}회</div>
            </div>
        </div>
    </div>""")
    eq = res["eq_df"]
    f = go.Figure()
    f.add_trace(go.Scatter(x=eq.index, y=eq["strategy_eq"], name="전략", line=dict(color="#10b981", width=2.2)))
    f.add_trace(go.Scatter(x=eq.index, y=eq["bh_eq"], name="Buy&Hold", line=dict(color="#64748b", width=1.5, dash="dot")))
    f.update_layout(template="plotly_dark", height=360, margin=dict(l=30, r=30, t=30, b=20),
                    paper_bgcolor="#080c14", plot_bgcolor="#080c14", hovermode="x unified",
                    legend=dict(orientation="h", y=1.1))
    st.plotly_chart(f, use_container_width=True)
    if res["trades"]:
        with st.expander(f"📋 거래 내역 ({len(res['trades'])}건)", expanded=False):
            st.dataframe(pd.DataFrame(res["trades"]), use_container_width=True, hide_index=True)


# ==============================================================================
# 18) TAB 5: WFA
# ==============================================================================
def render_tab_wfa():
    render_html("""<div style="margin-bottom:12px;">
    <div style="font-size:18px;font-weight:800;color:#fff;">🔬 Walk-Forward 전진 분석</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:2px;">IS 최적화 → OOS 실전 검증. 실전 강건성(WFE).</div>
    </div>""")
    c1, c2, c3 = st.columns(3)
    with c1: wt = st.text_input("티커", value="NVDA", key="wfa_t").upper().strip()
    with c2: wp = st.selectbox("기간", ["2y", "3y", "5y"], index=1, key="wfa_p")
    with c3: ws = st.selectbox("Fold", [3, 4, 5], index=1, key="wfa_s")
    if st.button("🔬 WFA 실행", type="primary", use_container_width=True) or "wfa_res" not in st.session_state:
        with st.spinner(f"{wt} WFA 연산 중..."):
            st.session_state.wfa_res = run_walk_forward(wt, period=wp, n_splits=int(ws))
    wr = st.session_state.get("wfa_res", {})
    if not wr:
        st.warning("데이터 부족")
        return
    oc = "#10b981" if wr["cum_oos_pct"] >= 0 else "#f43f5e"
    render_html(f"""
    <div class="glass-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:14px; font-weight:800; color:#38bdf8;">🏆 판정: {wr['verdict']}</span>
            <span class="badge badge-teal">일관성: {wr['consistency']:.0f}%</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono';">
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">OOS 누적</div>
                <div style="font-size:18px; font-weight:800; color:{oc};">{wr['cum_oos_pct']:+.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">평균 IS vs OOS</div>
                <div style="font-size:15px; font-weight:800; color:#f8fafc;">{wr['avg_is_pct']:+.1f}% / {wr['avg_oos_pct']:+.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">WFE</div>
                <div style="font-size:18px; font-weight:800; color:#fbbf24;">{wr['wfe']:.1f}%</div>
            </div>
        </div>
    </div>""")
    st.markdown("##### 📊 Fold별 성적")
    st.dataframe(pd.DataFrame(wr["folds"]), use_container_width=True, hide_index=True)


# ==============================================================================
# 19) TAB 6: 리스크
# ==============================================================================
def render_tab_portfolio_risk(usd_krw):
    render_html("""<div style="margin-bottom:12px;">
    <div style="font-size:18px;font-weight:800;color:#fff;">📊 포트폴리오 통합 리스크 & 역변동성 리밸런싱</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:2px;">VaR · CVaR · 베타 · 상관계수 · 리스크 패리티</div>
    </div>""")
    holdings = db_get_holdings()
    if not holdings:
        st.info("보유주식 DB 비어 있어 기본(NVDA·TSLA·PLTR·IREN)으로 시뮬레이션합니다.")
        holdings = [{"ticker": "NVDA", "qty": 50.0}, {"ticker": "TSLA", "qty": 40.0},
                    {"ticker": "PLTR", "qty": 100.0}, {"ticker": "IREN", "qty": 200.0}]
    if st.button("📊 리스크 진단", type="primary", use_container_width=True) or "risk_rep" not in st.session_state:
        with st.spinner("VaR·상관계수 연산 중..."):
            st.session_state.risk_rep = build_full_risk_report(holdings)
    rep = st.session_state.get("risk_rep", {})
    if not rep:
        st.warning("리스크 리포트 생성 실패")
        return
    render_html(f"""
    <div class="glass-card">
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono'; margin-bottom:10px;">
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">VaR 95%</div>
                <div style="font-size:16px; font-weight:800; color:#f43f5e;">{rep['var_95_pct']:.2f}%</div>
                <div style="font-size:10px; color:#fca5a5;">-${rep['var_95_usd']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">CVaR 95%</div>
                <div style="font-size:16px; font-weight:800; color:#fb7185;">{rep['cvar_95_pct']:.2f}%</div>
                <div style="font-size:10px; color:#fca5a5;">-${rep['cvar_95_usd']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">β vs SPY</div>
                <div style="font-size:16px; font-weight:800; color:#38bdf8;">{rep['beta']:.2f}</div>
                <div style="font-size:10px; color:#94a3b8;">연변동 {rep['ann_vol']:.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">샤프 / HHI</div>
                <div style="font-size:16px; font-weight:800; color:#10b981;">{rep['sharpe']:.2f}</div>
                <div style="font-size:10px; color:#94a3b8;">집중 {rep['hhi']:.0f}점</div>
            </div>
        </div>
        <div style="background:rgba(244,63,94,.1); border:1px solid rgba(244,63,94,.3); border-radius:8px; padding:8px 12px; font-size:11px; color:#fecdd3;">
            • <b>🔥 스트레스:</b> SPY -5% 시 -${rep['stress_5pct_usd']:,.0f} | SPY -10% 시 -${rep['stress_10pct_usd']:,.0f}
        </div>
    </div>""")
    if rep.get("rebal_actions"):
        render_html(f"""
        <div class="rebal-card">
            <div style="font-size:13px; font-weight:800; color:#c084fc; margin-bottom:6px;">⚖️ 리스크 패리티(역변동성) 비중 리밸런싱</div>
            <div style="font-size:11px; color:#e9d5ff; line-height:1.55;">
                {"<br>".join(f"• {a}" for a in rep['rebal_actions'])}
            </div>
        </div>""")
    cL, cR = st.columns([1.2, 1.3])
    with cL:
        st.markdown("##### ⚖️ 현재 vs 권장 비중")
        st.dataframe(pd.DataFrame(rep["weights_table"]), use_container_width=True, hide_index=True)
    with cR:
        st.markdown("##### 🔗 상관계수")
        st.dataframe(rep["corr_matrix"], use_container_width=True)


# ==============================================================================
# 20) TAB 7 (v14): 매매일지 + 봇 신호 자동 검증 (이중 시스템)
# ==============================================================================
def render_tab_journal(usd_krw):
    # v14: 탭 진입 시 자동으로 N일 지난 신호 평가
    db_eval_pending_signals()

    render_html("""
    <div style="margin-bottom:12px;">
        <div style="font-size:18px; font-weight:800; color:#fff;">📓 매매일지 & 신호 이중 검증 센터</div>
        <div style="font-size:12px; color:#94a3b8; margin-top:2px;">
            <b>① 봇 신호 자동 승률 검증</b> (시스템) + <b>② 내 매매일지</b> (수동) — 이중 추적.
        </div>
    </div>""")

    # ─── v14 신규: 봇 신호 자동 승률 검증 ───
    signal_stats = db_get_signal_stats()
    pending_cnt = db_get_pending_signal_count()
    if signal_stats:
        sig10 = [s for s in signal_stats if s['horizon'] == 10]
        total_sig = sum(s['total'] for s in sig10)
        total_win = sum(s['wins'] for s in sig10)
        overall_win = (total_win / total_sig * 100) if total_sig > 0 else 0
        stat_rows = []
        for s in sorted(signal_stats, key=lambda x: (-x['horizon'], -x['win_rate'])):
            wr_color = "#10b981" if s['win_rate'] >= 55 else ("#f59e0b" if s['win_rate'] >= 45 else "#f43f5e")
            ret_color = "#10b981" if s['avg_return'] >= 0 else "#f43f5e"
            stat_rows.append(f"""
            <div style="background:rgba(0,0,0,.35); border:1px solid #1e293b; border-radius:8px; padding:8px 12px; margin-bottom:5px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:13px; font-weight:800; color:#fff;">{s['signal']}</span>
                    <span class="badge badge-indigo">{s['horizon']}일</span>
                </div>
                <div style="font-size:11px; font-family:'JetBrains Mono'; display:flex; gap:10px; flex-wrap:wrap;">
                    <span style="color:#94a3b8;">총 <b class="text-white">{s['total']}</b></span>
                    <span style="color:#10b981;">승 <b>{s['wins']}</b></span>
                    <span style="color:#f43f5e;">패 <b>{s['losses']}</b></span>
                    <span style="color:{wr_color}; font-weight:800;">승률 {s['win_rate']:.1f}%</span>
                    <span style="color:{ret_color};">평균 {s['avg_return']:+.2f}%</span>
                </div>
            </div>""")
        render_html(f"""
        <div class="signal-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
                <span style="font-size:14px; font-weight:800; color:#a5b4fc;">🤖 봇 신호 자동 승률 검증 (5/10/20일 후 평가)</span>
                <span class="badge {('badge-green' if overall_win >= 55 else ('badge-yellow' if overall_win >= 45 else 'badge-red'))}">
                    전체 승률 {overall_win:.0f}% ({total_win}/{total_sig}) | 대기 {pending_cnt}건
                </span>
            </div>
            <div style="font-size:11px; color:#cbd5e1; margin-bottom:6px;">
                • Tab 2 진입 시마다 자동 예약 → 지정된 일자가 지나면 자동으로 WIN/LOSS 판정
            </div>
            {"".join(stat_rows)}
        </div>""")
    else:
        render_html(f"""
        <div class="signal-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
                <span style="font-size:14px; font-weight:800; color:#a5b4fc;">🤖 봇 신호 자동 승률 검증</span>
                <span class="badge badge-indigo">현재 예약 대기: {pending_cnt}건</span>
            </div>
            <div style="font-size:11px; color:#94a3b8; text-align:center; padding:20px 0;">
                아직 검증 완료된 신호가 없습니다.<br>
                <span style="font-size:10px;">Tab 2에서 보유 종목을 등록하면 신호가 자동 예약되며, 5/10/20일 뒤 실제 주가로 승률이 산출됩니다.</span>
            </div>
        </div>""")

    # ─── 수동 매매일지 ───
    with st.expander("✍️ 신규 매매일지 기록하기", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1: j_date = st.text_input("매매일자", value=datetime.now().strftime("%Y-%m-%d"), key="j_dt")
        with c2: j_ticker = st.text_input("티커", value="IREN", key="j_tk").upper().strip()
        with c3: j_side = st.selectbox("구분", ["1차익절", "2차익절", "트레일링청산", "원칙손절", "신규매수"], key="j_sd")
        with c4: j_pnl = st.number_input("실현손익 ($)", value=250.0, step=10.0, key="j_pnl")
        c5, c6, c7, c8 = st.columns([1, 1, 1.3, 1.3])
        with c5: j_px = st.number_input("체결단가 ($)", value=15.5, min_value=0.0, step=0.1, key="j_px")
        with c6: j_qty = st.number_input("수량 (주)", value=100.0, min_value=0.0, step=1.0, key="j_qty")
        with c7: j_strat = st.selectbox("적용 대가 기법",
            ["오닐 CANSLIM 돌파", "미너비니 SEPA/VCP", "다바스 박스 돌파",
             "와인스타인 2단계", "코너스 RSI 역발상", "튜더존스 200일선", "기타/재량"], key="j_st")
        with c8: j_emo = st.selectbox("매매 심리 상태",
            ["✅ 원칙준수 (냉정)", "🔥 FOMO 추격매수", "😨 공포 조기매도", "😡 복수/뇌동매매"], key="j_em")
        j_memo = st.text_input("한줄 복기 메모", value="거래량 1.8배 돌파 확인 후 분할 익절 원칙 준수", key="j_mm")
        if st.button("💾 매매일지 저장", type="primary", use_container_width=True):
            db_add_journal_entry(j_date, j_ticker, j_side, j_px, j_qty, j_pnl, j_strat, j_emo, j_memo)
            st.rerun()

    entries = db_get_journal_entries()
    if not entries:
        st.info("아직 기록된 매매일지가 없습니다. 위 입력창에서 첫 매매 복기를 기록해보세요!")
        return

    pnls = [safe_float(e["실현손익($)"], 0.0) for e in entries]
    total_realized = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls)) * 100.0 if pnls else 0.0
    profit_factor = (sum(wins) / sum(losses)) if sum(losses) > 0 else (9.99 if sum(wins) > 0 else 0.0)
    tot_col = "#10b981" if total_realized >= 0 else "#f43f5e"

    render_html(f"""
    <div class="journal-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
            <span style="font-size:14px; font-weight:800; color:#34d399;">📋 내 매매일지 퍼포먼스 (총 {len(entries)}건)</span>
            <span class="badge badge-green">수동 복기 시스템</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono';">
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">누적 실현손익 ($)</div>
                <div style="font-size:17px; font-weight:800; color:{tot_col};">${total_realized:+,.2f}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">누적 실현손익 (원화)</div>
                <div style="font-size:15px; font-weight:800; color:{tot_col};">{total_realized*usd_krw:+,.0f}원</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">실현 승률</div>
                <div style="font-size:17px; font-weight:800; color:#fbbf24;">{win_rate:.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">손익비 (PF)</div>
                <div style="font-size:17px; font-weight:800; color:#38bdf8;">{profit_factor:.2f}</div>
            </div>
        </div>
    </div>""")

    df_j = pd.DataFrame(entries)
    st.dataframe(df_j.drop(columns=["id"], errors="ignore"), use_container_width=True, hide_index=True)

    c_del, c_dl = st.columns([1.5, 1.5])
    with c_del:
        del_id = st.selectbox("삭제할 기록", options=[e["id"] for e in entries],
                              format_func=lambda x: f"#{x} ({next((e['티커']+' '+e['일자'] for e in entries if e['id']==x), '')})")
        if st.button("🗑️ 선택 일지 삭제", use_container_width=True):
            db_delete_journal_entry(del_id)
            st.rerun()
    with c_dl:
        st.write("")
        st.write("")
        st.download_button("📥 매매일지 CSV", data=df_j.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"trading_journal_{datetime.now().strftime('%Y%m%d')}.csv",
                           mime="text/csv", use_container_width=True)


# ==============================================================================
# 21) MAIN ENTRY
# ==============================================================================
def main():
    btc_price, btc_change, usd_krw = get_top_bar_data()
    eff_krw = usd_krw if usd_krw > 0 else CFG["usd_krw_fallback"]
    render_live_ny_header(btc_price, btc_change, eff_krw)
    indices = get_market_indices()
    idx_cards = []
    for item in indices:
        color = "text-green" if item['change'] >= 0 else "text-red"
        sign = "+" if item['change'] >= 0 else ""
        if "국채" in item['name'] or "금리" in item['name']:
            price_display = f"{item['price']:.2f}%"
        elif item['price'] > 1000:
            price_display = f"{item['price']:,.0f}"
        else:
            price_display = f"{item['price']:,.2f}"
        idx_cards.append(f"""<div class="index-card">
<div class="index-name">{html.escape(item['name'])}</div>
<div class="index-price {color}">{price_display}</div>
<div class="index-change {color}">{sign}{item['change']:.2f}%</div>
</div>""")
    render_html(f"""<div class="index-wrapper">{"".join(idx_cards)}</div>""")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 개별분석", "🛡️ 보유모니터", "🎯 스캐너", "🧪 백테스트",
        "🔬 WFA검증", "📊 리스크", "📓 매매일지",
    ])
    with tab1:
        render_tab_analysis(indices, eff_krw)
    with tab2:
        render_tab_holdings_monitor(eff_krw)
    with tab3:
        render_tab_scanner()
    with tab4:
        render_tab_backtest()
    with tab5:
        render_tab_wfa()
    with tab6:
        render_tab_portfolio_risk(eff_krw)
    with tab7:
        render_tab_journal(eff_krw)


if __name__ == "__main__":
    main()