import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import pytz
from datetime import datetime, time as dtime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Try importing st_autorefresh if available
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ==============================================================================
# HTML HELPER: STRIP INDENTATION TO PREVENT STREAMLIT MARKDOWN CODE-BLOCK BUG
# ==============================================================================
def render_html(html_str):
    """
    Strips all leading and trailing whitespace from every line.
    Prevents Markdown parser from treating lines with 4+ spaces as <pre><code> blocks.
    """
    cleaned = "\n".join(line.strip() for line in html_str.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


# ==============================================================================
# 1. PAGE CONFIG & MODERN BLOOMBERG / TRADINGVIEW THEME CSS
# ==============================================================================
st.set_page_config(
    page_title="GANGJIN AI TRADER PRO",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="collapsed"
)

render_html("""
<meta name="google" content="notranslate">
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Pretendard:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
}
.mono {
    font-family: 'JetBrains Mono', monospace;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.block-container { 
    padding-top: 0.8rem; 
    padding-bottom: 2rem; 
    max-width: 1400px; 
} 
.stApp { 
    background-color: #080c14; 
    color: #e6edf3;
}

/* Input & Select Box styling */
div[data-baseweb="input"], div[data-baseweb="textarea"] { 
    background-color: #0f1523 !important; 
    border: 1px solid #1e293b !important; 
    border-radius: 10px !important; 
    color: #ffffff !important; 
}
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { 
    color: #ffffff !important; 
    font-size: 14px !important; 
    font-weight: 700 !important; 
}
div[data-baseweb="select"] > div { 
    background-color: #0f1523 !important; 
    border-color: #1e293b !important; 
    color: #ffffff !important; 
    border-radius: 10px !important;
}

/* Cards */
.glass-card {
    background: linear-gradient(135deg, rgba(17, 24, 39, 0.85), rgba(15, 23, 42, 0.65));
    border: 1px solid rgba(51, 65, 85, 0.5);
    backdrop-filter: blur(12px);
    padding: 16px 20px;
    border-radius: 14px;
    margin-bottom: 14px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

.main-hero-card {
    background: linear-gradient(135deg, #0d1e16 0%, #0a131a 50%, #0c1524 100%);
    border: 1px solid #1e3a2f;
    padding: 18px 22px;
    border-radius: 14px;
    margin-bottom: 14px;
    box-shadow: 0 8px 32px rgba(16, 185, 129, 0.08);
}

/* Market Indices Bar */
.index-wrapper { 
    display: flex;
    flex-wrap: wrap;
    gap: 8px; 
    margin-bottom: 16px; 
}
.index-card { 
    flex: 1 1 120px;
    background-color: #0d131f; 
    border: 1px solid #1e293b; 
    padding: 10px 8px; 
    border-radius: 10px; 
    text-align: center; 
    transition: transform 0.15s ease, border-color 0.15s ease;
}
.index-card:hover {
    transform: translateY(-2px);
    border-color: #3b82f6;
}
.index-name { 
    color: #94a3b8; 
    font-size: 11px; 
    font-weight: 600; 
    margin-bottom: 3px; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis;
}
.index-price { 
    font-size: 13px; 
    font-weight: 800; 
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 2px;
}
.index-change { 
    font-size: 10px; 
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

/* Typography & Colors */
.text-white { color: #ffffff !important; }
.text-muted { color: #94a3b8 !important; }
.text-green { color: #10b981 !important; }
.text-red { color: #f43f5e !important; }
.text-yellow { color: #f59e0b !important; }
.text-blue { color: #3b82f6 !important; }
.text-purple { color: #a855f7 !important; }

/* Badges */
.badge {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 800;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    letter-spacing: 0.3px;
}
.badge-green { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid #10b981; }
.badge-red { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid #f43f5e; }
.badge-yellow { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid #f59e0b; }
.badge-blue { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid #3b82f6; }
.badge-purple { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid #a855f7; }

/* Tabs styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: #0b111e;
    padding: 6px;
    border-radius: 12px;
    border: 1px solid #1e293b;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    color: #94a3b8;
    font-weight: 700;
    padding: 8px 18px;
}
.stTabs [aria-selected="true"] {
    background-color: #1e293b !important;
    color: #ffffff !important;
}

hr { border: none; border-top: 1px solid #1e293b; margin: 14px 0; }
</style>
""")


# ==============================================================================
# 2. REAL-TIME NEW YORK TIME CLOCK & MARKET STATUS (Client-Side Dynamic JS)
# ==============================================================================
def render_live_ny_header(btc_price, btc_change, usd_krw):
    """
    Client-side pure JavaScript ticker clock that ticks every second in New York Time (ET),
    calculates market status (Pre-market, Regular, Post-market, Closed) and countdown,
    ensuring a true real-time display without reloading the Python Streamlit process.
    """
    btc_color = "#10b981" if btc_change >= 0 else "#f43f5e"
    btc_sign = "▲" if btc_change >= 0 else "▼"

    live_clock_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
    body {{
        margin: 0;
        padding: 0;
        background: transparent;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .header-box {{
        background: linear-gradient(90deg, #0a0f1d, #111a2e);
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 10px 16px;
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }}
    .left-section {{
        display: flex;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
    }}
    .clock-title {{
        font-weight: 800;
        font-size: 13px;
        color: #f8fafc;
        letter-spacing: 0.5px;
        display: flex;
        align-items: center;
        gap: 6px;
    }}
    .pulse-dot {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background-color: #10b981;
        box-shadow: 0 0 10px #10b981;
    }}
    .clock-display {{
        font-family: "JetBrains Mono", monospace, monospace;
        font-size: 15px;
        font-weight: 800;
        color: #38bdf8;
        background: rgba(56,189,248,0.1);
        border: 1px solid rgba(56,189,248,0.3);
        padding: 3px 10px;
        border-radius: 6px;
    }}
    .status-badge {{
        font-size: 11px;
        font-weight: 800;
        padding: 4px 10px;
        border-radius: 12px;
        letter-spacing: 0.5px;
    }}
    .countdown-text {{
        font-size: 12px;
        color: #94a3b8;
        font-weight: 600;
    }}
    .right-section {{
        display: flex;
        align-items: center;
        gap: 16px;
        font-family: "JetBrains Mono", monospace, monospace;
        font-size: 13px;
    }}
    </style>
    </head>
    <body>
    <div class="header-box">
        <div class="left-section">
            <div class="clock-title">
                <span class="pulse-dot" id="pulse-dot"></span>
                <span>NEW YORK (ET)</span>
            </div>
            <div class="clock-display" id="ny-live-clock">--:--:-- ET</div>
            <div class="status-badge" id="market-status-badge">CALCULATING...</div>
            <div class="countdown-text" id="market-countdown">--</div>
        </div>
        <div class="right-section">
            <div style="color: #cbd5e1;">
                <span style="color:#94a3b8; font-weight:600;">BTC/USD:</span>
                <span style="color: {btc_color}; font-weight:800; margin-left:4px;">{btc_sign} ${btc_price:,.0f}</span>
            </div>
            <div style="color: #cbd5e1; border-left: 1px solid #334155; padding-left: 14px;">
                <span style="color:#94a3b8; font-weight:600;">USD/KRW:</span>
                <span style="color: #38bdf8; font-weight:800; margin-left:4px;">{usd_krw:,.1f}원</span>
            </div>
        </div>
    </div>

    <script>
    function updateNYClock() {{
        try {{
            const now = new Date();
            const nyFormatter = new Intl.DateTimeFormat('en-US', {{
                timeZone: 'America/New_York',
                hour12: false,
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            }});
            
            const parts = nyFormatter.formatToParts(now);
            const timeObj = {{}};
            parts.forEach(p => timeObj[p.type] = p.value);
            
            const hours = parseInt(timeObj.hour, 10);
            const minutes = parseInt(timeObj.minute, 10);
            const totalMinutes = hours * 60 + minutes;

            const nyDate = new Date(now.toLocaleString('en-US', {{ timeZone: 'America/New_York' }}));
            const dayOfWeek = nyDate.getDay();

            const clockEl = document.getElementById('ny-live-clock');
            if (clockEl) {{
                clockEl.textContent = `${{timeObj.hour}}:${{timeObj.minute}}:${{timeObj.second}} ET`;
            }}

            const badgeEl = document.getElementById('market-status-badge');
            const countdownEl = document.getElementById('market-countdown');
            const dotEl = document.getElementById('pulse-dot');

            if (dayOfWeek === 0 || dayOfWeek === 6) {{
                if (badgeEl) {{
                    badgeEl.textContent = "WEEKEND CLOSED";
                    badgeEl.style.backgroundColor = "rgba(100, 116, 139, 0.2)";
                    badgeEl.style.color = "#94a3b8";
                    badgeEl.style.border = "1px solid #475569";
                }}
                if (countdownEl) countdownEl.textContent = "월요일 04:00 프리마켓 오픈 대기";
                if (dotEl) {{
                    dotEl.style.backgroundColor = "#64748b";
                    dotEl.style.boxShadow = "none";
                }}
                return;
            }}

            if (totalMinutes >= 240 && totalMinutes < 570) {{
                const remMin = 570 - totalMinutes;
                const remH = Math.floor(remMin / 60);
                const remM = remMin % 60;
                if (badgeEl) {{
                    badgeEl.textContent = "⚡ PRE-MARKET";
                    badgeEl.style.backgroundColor = "rgba(245, 158, 11, 0.15)";
                    badgeEl.style.color = "#fbbf24";
                    badgeEl.style.border = "1px solid #f59e0b";
                }}
                if (countdownEl) countdownEl.textContent = `정규장 개장까지 ${{remH}}시간 ${{remM}}분 전`;
                if (dotEl) {{
                    dotEl.style.backgroundColor = "#f59e0b";
                    dotEl.style.boxShadow = "0 0 10px #f59e0b";
                }}
            }} else if (totalMinutes >= 570 && totalMinutes < 960) {{
                const remMin = 960 - totalMinutes;
                const remH = Math.floor(remMin / 60);
                const remM = remMin % 60;
                if (badgeEl) {{
                    badgeEl.textContent = "🟢 REGULAR MARKET (LIVE)";
                    badgeEl.style.backgroundColor = "rgba(16, 185, 129, 0.2)";
                    badgeEl.style.color = "#34d399";
                    badgeEl.style.border = "1px solid #10b981";
                }}
                if (countdownEl) countdownEl.textContent = `정규장 마감까지 ${{remH}}시간 ${{remM}}분 남음`;
                if (dotEl) {{
                    dotEl.style.backgroundColor = "#10b981";
                    dotEl.style.boxShadow = "0 0 12px #10b981";
                }}
            }} else if (totalMinutes >= 960 && totalMinutes < 1200) {{
                const remMin = 1200 - totalMinutes;
                const remH = Math.floor(remMin / 60);
                const remM = remMin % 60;
                if (badgeEl) {{
                    badgeEl.textContent = "🌙 AFTER-HOURS";
                    badgeEl.style.backgroundColor = "rgba(168, 85, 247, 0.15)";
                    badgeEl.style.color = "#c084fc";
                    badgeEl.style.border = "1px solid #a855f7";
                }}
                if (countdownEl) countdownEl.textContent = `애프터마켓 종료까지 ${{remH}}시간 ${{remM}}분`;
                if (dotEl) {{
                    dotEl.style.backgroundColor = "#a855f7";
                    dotEl.style.boxShadow = "0 0 10px #a855f7";
                }}
            }} else {{
                if (badgeEl) {{
                    badgeEl.textContent = "🔒 MARKET CLOSED";
                    badgeEl.style.backgroundColor = "rgba(244, 63, 94, 0.15)";
                    badgeEl.style.color = "#fb7185";
                    badgeEl.style.border = "1px solid #f43f5e";
                }}
                if (countdownEl) countdownEl.textContent = "프리마켓(04:00 ET) 오픈 대기 중";
                if (dotEl) {{
                    dotEl.style.backgroundColor = "#f43f5e";
                    dotEl.style.boxShadow = "none";
                }}
            }}
        }} catch(e) {{
            console.error(e);
        }}
    }}

    setInterval(updateNYClock, 1000);
    updateNYClock();
    </script>
    </body>
    </html>
    """
    st.components.v1.html(live_clock_html, height=72)


# ==============================================================================
# 3. DATA FETCHING & CACHING (ROBUST & RESILIENT)
# ==============================================================================
@st.cache_data(ttl=60)
def get_top_bar_data():
    """Fetch BTC price and USD/KRW FX rate with fallback."""
    try:
        btc_data = yf.Ticker("BTC-USD").history(period="2d")
        btc_price = float(btc_data['Close'].iloc[-1])
        btc_prev = float(btc_data['Close'].iloc[-2])
        btc_change = btc_price - btc_prev
    except Exception:
        btc_price, btc_change = 85200.0, 1250.0

    try:
        usd_krw_data = yf.Ticker("KRW=X").history(period="2d")
        usd_krw = float(usd_krw_data['Close'].iloc[-1])
    except Exception:
        usd_krw = 1420.0

    return btc_price, btc_change, usd_krw


@st.cache_data(ttl=60)
def get_market_indices():
    """Fetch key macro indexes (10Y Yield, Dow/SP500/Nasdaq Futures, WTI, VIX, Gold)."""
    tickers = {
        "10년물 국채": "^TNX",
        "S&P500 선물": "ES=F",
        "나스닥100 선물": "NQ=F",
        "다우 선물": "YM=F",
        "WTI 원유": "CL=F",
        "VIX 변동성": "^VIX",
        "금 (Gold)": "GC=F"
    }
    results = []
    for name, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if len(data) >= 2:
                current = float(data['Close'].iloc[-1])
                prev = float(data['Close'].iloc[-2])
                change = ((current - prev) / prev) * 100
                results.append({"name": name, "price": current, "change": change})
            else:
                results.append({"name": name, "price": 0.0, "change": 0.0})
        except Exception:
            results.append({"name": name, "price": 0.0, "change": 0.0})
    return results


@st.cache_data(ttl=300)
def get_google_news(ticker):
    """Fetch Google News RSS for ticker with sentiment classification."""
    query = urllib.parse.quote(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    news_items = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        response = urllib.request.urlopen(req, timeout=5)
        xml_data = response.read()
        root = ET.fromstring(xml_data)

        positive_words = ['surge', 'jump', 'gain', 'beat', 'bull', 'upgrade', 'record', 'soar', 'buy', 'growth', 'profit']
        negative_words = ['drop', 'fall', 'plunge', 'miss', 'bear', 'downgrade', 'slump', 'crash', 'sell', 'loss', 'probe']

        for item in root.findall('.//item')[:5]:
            title = item.find('title').text or ""
            link = item.find('link').text or "#"
            pub_date = item.find('pubDate').text[:16] if item.find('pubDate') is not None else ""

            title_lower = title.lower()
            pos_hits = sum(w in title_lower for w in positive_words)
            neg_hits = sum(w in title_lower for w in negative_words)
            if pos_hits > neg_hits:
                sentiment = "호재 (Bullish)"
                badge_class = "badge-green"
            elif neg_hits > pos_hits:
                sentiment = "악재 (Bearish)"
                badge_class = "badge-red"
            else:
                sentiment = "중립 (Neutral)"
                badge_class = "badge-blue"

            news_items.append({
                "title": title,
                "link": link,
                "date": pub_date,
                "sentiment": sentiment,
                "badge_class": badge_class
            })
    except Exception:
        pass
    return news_items


@st.cache_data(ttl=3600)
def get_gamma_wall(ticker, exp_date=None):
    """
    Calculate Option Gamma Wall (Call Wall, Put Wall, and Max Pain).
    Call Wall = strike with highest Call Open Interest (Resistance)
    Put Wall = strike with highest Put Open Interest (Support)
    """
    try:
        stock = yf.Ticker(ticker)
        options = stock.options
        if not options:
            return None, None, None, []

        target_exp = exp_date if exp_date in options else options[0]
        opt_chain = stock.option_chain(target_exp)

        calls = opt_chain.calls[['strike', 'openInterest', 'volume']].dropna()
        puts = opt_chain.puts[['strike', 'openInterest', 'volume']].dropna()

        call_wall = calls.loc[calls['openInterest'].idxmax()]['strike'] if not calls.empty and calls['openInterest'].max() > 0 else None
        put_wall = puts.loc[puts['openInterest'].idxmax()]['strike'] if not puts.empty and puts['openInterest'].max() > 0 else None

        all_strikes = np.union1d(calls['strike'], puts['strike'])
        pain_values = []
        for strike in all_strikes:
            call_loss = np.maximum(0, strike - calls['strike']) * calls['openInterest']
            put_loss = np.maximum(0, puts['strike'] - strike) * puts['openInterest']
            total_loss = call_loss.sum() + put_loss.sum()
            pain_values.append(total_loss)
        
        max_pain = all_strikes[np.argmin(pain_values)] if len(pain_values) > 0 else None

        return call_wall, put_wall, max_pain, list(options)
    except Exception:
        return None, None, None, []


# ==============================================================================
# 4. ADVANCED TECHNICAL ANALYSIS & 4 MASTERS LOGIC
# ==============================================================================
def compute_technical_indicators(hist):
    """
    Computes technical indicators with clean timezone-stripped index.
    """
    df = hist.copy()
    if df.index.tz is not None:
        try:
            df.index = df.index.tz_localize(None)
        except Exception:
            df.index = df.index.tz_convert(None)

    close = df['Close']
    high = df['High']
    low = df['Low']
    vol = df['Volume']

    df['EMA10'] = close.ewm(span=10, adjust=False).mean()
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    df['SMA50'] = close.rolling(window=50).mean()
    df['SMA200'] = close.rolling(window=200).mean()

    df['Box_High'] = high.rolling(window=20).max()
    df['Box_Low'] = low.rolling(window=20).min()

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)

    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + 2 * df['BB_Std']
    df['BB_Lower'] = df['BB_Mid'] - 2 * df['BB_Std']

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    typical = (high + low + close) / 3
    df['Typical'] = typical
    df['VWAP_Year'] = (typical * vol).cumsum() / vol.cumsum()
    df['VWAP_Week'] = (typical * vol).rolling(window=5).sum() / vol.rolling(window=5).sum()
    
    df['Vol_MA20'] = vol.rolling(window=20).mean()
    df['Vol_Ratio'] = vol / df['Vol_MA20'].replace(0, np.nan)
    df['Vol_Ratio'] = df['Vol_Ratio'].fillna(1.0)

    return df


def evaluate_trading_signal(df):
    """Multi-factor AI Trading Decision Matrix (JINGANG / 4 Masters)."""
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    price = curr['Close']
    prev_close = prev['Close']
    change = price - prev_close
    change_pct = (change / prev_close) * 100

    box_high = curr['Box_High']
    box_low = curr['Box_Low']
    ema10 = curr['EMA10']
    ema20 = curr['EMA20']
    rsi = curr['RSI']
    vol_ratio = curr['Vol_Ratio']
    atr = curr['ATR'] if not np.isnan(curr['ATR']) else price * 0.03

    score = 50
    score_reasons = []

    if price > ema10 and ema10 > ema20:
        score += 20
        score_reasons.append("단기 및 중기 정배열 (추세 강력)")
    elif price < ema20:
        score -= 20
        score_reasons.append("20일선 하회 (추세 이탈 경고)")

    if price >= box_high:
        if vol_ratio >= 1.5:
            score += 25
            score_reasons.append(f"20일 박스권 신고가 돌파 + 대량 거래량({vol_ratio:.1f}배)")
        else:
            score += 10
            score_reasons.append("박스권 상단 터치 (거래량 확인 필요)")
    elif price <= box_low:
        score -= 15
        score_reasons.append("박스권 하단 이탈 위험")

    if rsi <= 25.0:
        score += 25
        score_reasons.append(f"투매 극단 과매도 타점 (RSI {rsi:.1f} <= 25)")
    elif rsi >= 75.0:
        score -= 10
        score_reasons.append(f"단기 과열 주의 (RSI {rsi:.1f} >= 75)")

    if curr['MACD_Hist'] > 0 and prev['MACD_Hist'] <= 0:
        score += 10
        score_reasons.append("MACD 골든크로스 발생")

    score = max(0, min(100, score))

    if price >= box_high and vol_ratio >= 1.5:
        action = "🔥 STRONG BUY"
        css_class = "text-green"
        badge_class = "badge-green"
        reason = "박스권 상단 돌파 + 거래량 폭발 (미너비니 / 오닐 CANSLIM 돌파)"
        stop_loss = max(box_high * 0.96, price - 2 * atr)
        target_1 = price * 1.10
        target_2 = price * 1.25
    elif price >= box_high:
        action = "📈 BUY"
        css_class = "text-green"
        badge_class = "badge-green"
        reason = "20일 박스권 상단 돌파 (추가 거래량 동반 시 강세 지속)"
        stop_loss = price * 0.96
        target_1 = price * 1.07
        target_2 = price * 1.15
    elif price < ema20 and rsi <= 25.0:
        action = "🟢 PANIC BUY"
        css_class = "text-green"
        badge_class = "badge-green"
        reason = f"공포 투매 과매도 반등 타점 (RSI {rsi:.1f} 극단 과매도 V자 반등 노림)"
        stop_loss = price * 0.94
        target_1 = price * 1.06
        target_2 = price * 1.12
    elif price < ema20:
        action = "⚠️ EXIT"
        css_class = "text-red"
        badge_class = "badge-red"
        reason = f"생명선(EMA20 ${ema20:.2f}) 이탈로 리스크 관리 구간 진입"
        stop_loss = price * 0.97
        target_1 = price * 1.03
        target_2 = price * 1.06
    elif price > ema10:
        action = "✅ HOLD"
        css_class = "text-yellow"
        badge_class = "badge-yellow"
        reason = "10일 이동평균선 상회로 안정적 상승 파동 유지 중"
        stop_loss = ema10 * 0.98
        target_1 = price * 1.05
        target_2 = price * 1.12
    else:
        action = "⏸️ WAIT"
        css_class = "text-muted"
        badge_class = "badge-blue"
        reason = "추세 수렴 관망 구간 (돌파 혹은 저점 지지 대기)"
        stop_loss = price * 0.95
        target_1 = price * 1.05
        target_2 = price * 1.08

    return {
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "action": action,
        "css_class": css_class,
        "badge_class": badge_class,
        "reason": reason,
        "score": score,
        "score_reasons": score_reasons,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "box_high": box_high,
        "box_low": box_low,
        "ema10": ema10,
        "ema20": ema20,
        "rsi": rsi,
        "vol_ratio": vol_ratio,
        "atr": atr
    }


# ==============================================================================
# 5. PROFESSIONAL PLOTLY INTERACTIVE CHART (TradingView / Bloomberg Style)
# ==============================================================================
def create_advanced_trading_chart(df, ticker, show_vwap_y, show_vwap_w, call_wall, put_wall):
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.55, 0.15, 0.15, 0.15],
        subplot_titles=(
            f"{ticker} 가격 & 추세 채널",
            "거래량 (Volume)",
            "MACD (12, 26, 9)",
            "RSI (14)"
        )
    )

    # 1. Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="캔들",
        increasing_line_color='#10b981', decreasing_line_color='#f43f5e',
        increasing_fillcolor='#10b981', decreasing_fillcolor='#f43f5e'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['EMA10'], name="EMA 10", line=dict(color='#38bdf8', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name="EMA 20", line=dict(color='#fbbf24', width=1.5)), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], name="BB 상단", line=dict(color='rgba(148, 163, 184, 0.4)', width=1, dash='dot')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], name="BB 하단", line=dict(color='rgba(148, 163, 184, 0.4)', width=1, dash='dot'),
                             fill='tonexty', fillcolor='rgba(148, 163, 184, 0.04)'), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['Box_High'], name="20일 박스 상단", line=dict(color='#ef4444', width=1.2, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Box_Low'], name="20일 박스 하단", line=dict(color='#10b981', width=1.2, dash='dash')), row=1, col=1)

    if show_vwap_y and 'VWAP_Year' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['VWAP_Year'], name="1년 VWAP", line=dict(color='#a855f7', width=1.5)), row=1, col=1)
    if show_vwap_w and 'VWAP_Week' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['VWAP_Week'], name="5일 VWAP", line=dict(color='#ec4899', width=1.5)), row=1, col=1)

    if call_wall:
        fig.add_hline(y=call_wall, line=dict(color="#f43f5e", width=2, dash="dash"),
                      annotation_text=f"콜 감마벽: ${call_wall:.1f}", annotation_position="top right", row=1, col=1)
    if put_wall:
        fig.add_hline(y=put_wall, line=dict(color="#10b981", width=2, dash="dash"),
                      annotation_text=f"풋 감마벽: ${put_wall:.1f}", annotation_position="bottom right", row=1, col=1)

    # 2. Volume
    vol_colors = ['#10b981' if c >= o else '#f43f5e' for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="거래량", marker_color=vol_colors, opacity=0.8), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Vol_MA20'], name="20일 평균 거래량", line=dict(color='#94a3b8', width=1.2)), row=2, col=1)

    # 3. MACD
    hist_colors = ['#10b981' if v >= 0 else '#f43f5e' for v in df['MACD_Hist']]
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name="MACD Hist", marker_color=hist_colors), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name="MACD", line=dict(color='#38bdf8', width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], name="Signal", line=dict(color='#f59e0b', width=1.2)), row=3, col=1)

    # 4. RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#a855f7', width=1.5)), row=4, col=1)
    fig.add_hline(y=70, line=dict(color="rgba(244, 63, 94, 0.7)", width=1, dash="dot"), row=4, col=1)
    fig.add_hline(y=30, line=dict(color="rgba(16, 185, 129, 0.7)", width=1, dash="dot"), row=4, col=1)
    fig.add_hline(y=25, line=dict(color="#10b981", width=1.5, dash="dash"),
                  annotation_text="투매 타점 (25)", annotation_position="bottom right", row=4, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=720,
        margin=dict(l=40, r=40, t=40, b=30),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        paper_bgcolor="#080c14",
        plot_bgcolor="#080c14",
        hovermode="x unified"
    )

    fig.update_xaxes(gridcolor="#1e293b", showgrid=True)
    fig.update_yaxes(gridcolor="#1e293b", showgrid=True)

    return fig


# ==============================================================================
# 6. WATCHLIST SCANNER (MULTI-THREADED, 100+ STOCKS)
# ==============================================================================
PRESET_WATCHLISTS = {
    "🔥 서학개미 Top 100": (
        "NVDA TSLA AAPL MSFT AMZN GOOGL META PLTR AMD COIN MSTR SOXL TQQQ SMCI "
        "MARA RIOT IREN CLSK IONQ RKLB ASTS ARM TSM AVGO CRWD PANW NFLX DIS INTC "
        "SOFI HOOD OPEN LCID RIVN U RBLX SNOW BABA NIO XPEV LI BIDU PDD BILI "
        "UPST AFRM SQ PYPL SHOP SE CPNG PATH AI PLUG ENPH SEDG FCEL CHPT BLNK QS "
        "DKNG PENN WYNN LVS CCL RCL NCLH UAL DAL AAL LUV BA RTX LMT GD NOC "
        "XOM CVX OXY SLB HAL COP F GM TM HMC NKE LULU SBUX MCD KO PEP PG "
        "JNJ PFE MRK LLY UNH ABBV"
    ),
    "🤖 AI & 반도체 주도주": (
        "NVDA AMD TSM AVGO ARM ASML QCOM MU INTC MRVL AMAT LRCX KLAC ON NXPI ADI MPWR SMCI"
    ),
    "⚡ 양자 & 우주 혁신주": (
        "IONQ RGTI QBTS QUBT RKLB LUNR ASTS PL RDYW BKSY SPIR"
    ),
    "💎 비트코인 & 크립토 테마": (
        "MSTR COIN MARA RIOT IREN CLSK CIFR HUT BITF CORZ WULF BTDR"
    )
}

@st.cache_data(ttl=180)
def scan_multi_tickers(ticker_string):
    raw_tickers = [t.strip().upper() for t in ticker_string.replace(',', ' ').split() if t.strip()]
    unique_tickers = list(dict.fromkeys(raw_tickers))
    if not unique_tickers:
        return []

    try:
        data = yf.download(unique_tickers, period="3mo", group_by='ticker', threads=True, progress=False)
    except Exception:
        return []

    results = []
    for t in unique_tickers:
        try:
            df = data[t].dropna() if len(unique_tickers) > 1 else data.dropna()
            if len(df) < 20:
                continue

            close = df['Close']
            high = df['High']
            low = df['Low']
            vol = df['Volume']

            curr_price = float(close.iloc[-1])
            prev_price = float(close.iloc[-2])
            change_pct = ((curr_price - prev_price) / prev_price) * 100

            ema10 = float(close.ewm(span=10, adjust=False).mean().iloc[-1])
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            box_high = float(high.rolling(window=20).max().iloc[-1])
            box_low = float(low.rolling(window=20).min().iloc[-1])

            delta = close.diff()
            gain = (delta.where(delta > 0, 0.0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])

            avg_vol = float(vol.rolling(window=20).mean().iloc[-1])
            curr_vol = float(vol.iloc[-1])
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

            action = "⏸️ WAIT"
            badge = "badge-blue"
            if curr_price >= box_high and vol_ratio >= 1.5:
                action = "🔥 STRONG BUY"
                badge = "badge-green"
            elif curr_price >= box_high:
                action = "📈 BUY"
                badge = "badge-green"
            elif curr_price < ema20 and rsi <= 25.0:
                action = "🟢 PANIC BUY"
                badge = "badge-green"
            elif curr_price < ema20:
                action = "⚠️ EXIT"
                badge = "badge-red"
            elif curr_price > ema10:
                action = "✅ HOLD"
                badge = "badge-yellow"

            results.append({
                "ticker": t,
                "price": curr_price,
                "change_pct": change_pct,
                "action": action,
                "badge": badge,
                "rsi": rsi,
                "vol_ratio": vol_ratio,
                "box_high": box_high,
                "box_low": box_low,
                "is_buy": "BUY" in action
            })
        except Exception:
            continue

    priority_order = {"🔥 STRONG BUY": 0, "🟢 PANIC BUY": 1, "📈 BUY": 2, "✅ HOLD": 3, "⏸️ WAIT": 4, "⚠️ EXIT": 5}
    results.sort(key=lambda x: (priority_order.get(x['action'], 99), -x['change_pct']))
    return results


# ==============================================================================
# 7. MAIN CONTROLLER
# ==============================================================================
def main():
    # 1. Top Live Bar
    btc_price, btc_change, usd_krw = get_top_bar_data()
    render_live_ny_header(btc_price, btc_change, usd_krw)

    # 2. Major Global Market Indices Bar (Rendered via clean HTML without indentation)
    indices = get_market_indices()
    idx_cards = []
    for item in indices:
        color = "text-green" if item['change'] >= 0 else "text-red"
        sign = "+" if item['change'] >= 0 else ""
        if "금리" in item['name'] or item['price'] < 10:
            price_display = f"{item['price']:.2f}%"
        elif item['price'] > 1000:
            price_display = f"{item['price']:,.0f}"
        else:
            price_display = f"{item['price']:,.2f}"
        
        idx_cards.append(f"""<div class="index-card">
<div class="index-name">{item['name']}</div>
<div class="index-price {color}">{price_display}</div>
<div class="index-change {color}">{sign}{item['change']:.2f}%</div>
</div>""")

    render_html(f"""<div class="index-wrapper">
{"".join(idx_cards)}
</div>""")

    # 3. Main Navigation Tabs
    tab1, tab2 = st.tabs(["📊 개별 종목 정밀 분석", "🎯 100종목 실시간 스캐너"])

    # --------------------------------------------------------------------------
    # TAB 1: 개별 종목 정밀 분석
    # --------------------------------------------------------------------------
    with tab1:
        col_t1, col_t2 = st.columns([3, 1])
        with col_t1:
            st.markdown('<h2 style="margin:0 0 10px 0; font-weight:800; letter-spacing:-0.5px;">GANGJIN AI TRADER <span style="font-size:14px; color:#38bdf8; font-weight:700;">PRO v3.5</span></h2>', unsafe_allow_html=True)
        with col_t2:
            auto_refresh = st.toggle("🔄 60초 자동 갱신", value=False)
            if auto_refresh and HAS_AUTOREFRESH:
                st_autorefresh(interval=60000, key="auto_refresh")

        if "selected_ticker" not in st.session_state:
            st.session_state.selected_ticker = "IREN"

        # Non-nested, flat horizontal ticker selector
        c_inp, c1, c2, c3, c4, c5, c6, c7 = st.columns([2.5, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7])
        with c_inp:
            ticker_input = st.text_input(
                "종목 코드 입력",
                value=st.session_state.selected_ticker,
                label_visibility="collapsed",
                placeholder="티커 입력 (예: NVDA, TSLA, IREN)"
            )
            ticker = ticker_input.strip().upper()

        chips = [(c1, "NVDA"), (c2, "TSLA"), (c3, "PLTR"), (c4, "MSTR"), (c5, "IREN"), (c6, "IONQ"), (c7, "SOXL")]
        for col, q in chips:
            with col:
                if st.button(q, key=f"chip_{q}", use_container_width=True):
                    st.session_state.selected_ticker = q
                    st.rerun()

        if ticker:
            with st.spinner(f"{ticker} 데이터 및 AI 분석 연산 중..."):
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="1y")
                except Exception as e:
                    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
                    return

            if hist.empty or len(hist) < 25:
                st.warning(f"'{ticker}'에 대한 유효한 주가 데이터가 없습니다. 종목 코드를 확인해주세요.")
            else:
                df = compute_technical_indicators(hist)
                eval_res = evaluate_trading_signal(df)
                call_wall, put_wall, max_pain, exp_dates = get_gamma_wall(ticker)

                change_sign = "▲" if eval_res['change'] >= 0 else "▼"
                
                # Hero Card
                render_html(f"""
                <div class="main-hero-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
                        <div>
                            <div style="display:flex; align-items:center; gap:10px;">
                                <span style="font-size:26px; font-weight:800; color:#ffffff; letter-spacing:-0.5px;">{ticker}</span>
                                <span class="{eval_res['badge_class']}">{eval_res['action']}</span>
                                <span class="badge badge-purple">AI 스코어: {eval_res['score']}점</span>
                            </div>
                            <div style="font-size:32px; font-weight:800; font-family:'JetBrains Mono', monospace; margin:6px 0;" class="{eval_res['css_class']}">
                                ${eval_res['price']:,.2f} <span style="font-size:18px; font-weight:700;">{change_sign} ${abs(eval_res['change']):,.2f} ({eval_res['change_pct']:+.2f}%)</span>
                            </div>
                            <div style="color:#94a3b8; font-size:13px;">
                                20일 거래량 배율: <b style="color:#ffffff;">{eval_res['vol_ratio']:.1f}x</b> | RSI(14): <b style="color:#ffffff;">{eval_res['rsi']:.1f}</b> | ATR(변동폭): <b style="color:#ffffff;">${eval_res['atr']:.2f}</b>
                            </div>
                        </div>
                        <div style="text-align:right; min-width:220px;">
                            <div style="background:rgba(15,23,42,0.8); border:1px solid #1e293b; padding:10px 14px; border-radius:10px;">
                                <div style="font-size:11px; color:#94a3b8; font-weight:600; margin-bottom:4px;">🎯 4대 명인 매매 타점 가이드</div>
                                <div style="font-size:12px; color:#cbd5e1; display:flex; justify-content:space-between;">
                                    <span>지지선:</span> <b class="text-green">${eval_res['box_low']:,.2f}</b>
                                </div>
                                <div style="font-size:12px; color:#cbd5e1; display:flex; justify-content:space-between;">
                                    <span>손절선:</span> <b class="text-red">${eval_res['stop_loss']:,.2f}</b>
                                </div>
                                <div style="font-size:12px; color:#cbd5e1; display:flex; justify-content:space-between;">
                                    <span>1차 익절(+10%):</span> <b class="text-green">${eval_res['target_1']:,.2f}</b>
                                </div>
                                <div style="font-size:12px; color:#cbd5e1; display:flex; justify-content:space-between;">
                                    <span>2차 익절(+20%):</span> <b class="text-green">${eval_res['target_2']:,.2f}</b>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                """)

                col_ai, col_opt = st.columns([1.5, 1])
                with col_ai:
                    reasons_html = "".join([f"<li>{r}</li>" for r in eval_res['score_reasons']])
                    render_html(f"""
                    <div class="glass-card" style="height:100%;">
                        <div style="font-weight:700; color:#38bdf8; margin-bottom:8px;">
                            🧠 4대 명인 통합 엔진 판단 사유
                        </div>
                        <div style="font-size:14px; font-weight:700; color:#f8fafc; margin-bottom:6px;">
                            {eval_res['reason']}
                        </div>
                        <ul style="font-size:12px; color:#94a3b8; margin:0; padding-left:18px; line-height:1.7;">
                            {reasons_html}
                        </ul>
                    </div>
                    """)

                with col_opt:
                    call_str = f"${call_wall:,.1f}" if call_wall else "N/A"
                    put_str = f"${put_wall:,.1f}" if put_wall else "N/A"
                    pain_str = f"${max_pain:,.1f}" if max_pain else "N/A"
                    render_html(f"""
                    <div class="glass-card" style="height:100%;">
                        <div style="font-weight:700; color:#a855f7; margin-bottom:8px;">
                            🎯 옵션 감마벽 & Max Pain (수급 지지/저항)
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px;">
                            <span style="color:#94a3b8;">콜 감마벽 (저항선):</span>
                            <span style="font-weight:800; color:#f43f5e; font-family:'JetBrains Mono';">{call_str}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px;">
                            <span style="color:#94a3b8;">풋 감마벽 (지지선):</span>
                            <span style="font-weight:800; color:#10b981; font-family:'JetBrains Mono';">{put_str}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:13px;">
                            <span style="color:#94a3b8;">옵션 맥스페인:</span>
                            <span style="font-weight:800; color:#fbbf24; font-family:'JetBrains Mono';">{pain_str}</span>
                        </div>
                        <div style="font-size:10px; color:#64748b; margin-top:8px;">
                            * 최근 월물 미결제약정(Open Interest) 집중도 분석 기준
                        </div>
                    </div>
                    """)

                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                col_c1, col_c2, col_c3 = st.columns([1, 1, 2])
                with col_c1:
                    show_vwap_y = st.checkbox("1년 누적 VWAP 표시", value=True)
                with col_c2:
                    show_vwap_w = st.checkbox("5일 VWAP 표시", value=False)
                with col_c3:
                    show_gamma_lines = st.checkbox("차트에 감마벽(Call/Put Wall) 라인 표시", value=True)

                c_wall = call_wall if show_gamma_lines else None
                p_wall = put_wall if show_gamma_lines else None

                fig = create_advanced_trading_chart(df, ticker, show_vwap_y, show_vwap_w, c_wall, p_wall)
                st.plotly_chart(fig, use_container_width=True)

                # Profit Calculator & News Row
                col_calc, col_news = st.columns([1.2, 1])

                with col_calc:
                    with st.expander("💰 미래에셋/키움 해외주식 실시간 수익 시뮬레이터", expanded=True):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            buy_price = st.number_input("내 평단가 ($)", value=float(round(eval_res['price'], 2)), step=0.1)
                        with c2:
                            qty = st.number_input("보유 수량 (주)", value=100.0, step=10.0)
                        with c3:
                            fee_rate = st.selectbox("증권사 수수료", options=[0.0007, 0.001, 0.0025, 0.0], format_func=lambda x: f"{x*100:.2f}% (우대/일반)" if x>0 else "0% (수수료 무료)", index=2)

                        if buy_price > 0 and qty > 0:
                            invest_usd = buy_price * qty
                            current_usd = eval_res['price'] * qty
                            gross_profit = current_usd - invest_usd
                            fee_usd = (invest_usd + current_usd) * fee_rate
                            net_profit_usd = gross_profit - fee_usd
                            net_profit_krw = net_profit_usd * usd_krw
                            roi_pct = (net_profit_usd / invest_usd) * 100

                            p_color = "text-green" if net_profit_usd >= 0 else "text-red"
                            render_html(f"""
                            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px; margin-top:10px;">
                                <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                                    <span style="color:#94a3b8; font-size:12px;">총 매수원금:</span>
                                    <span style="font-family:'JetBrains Mono'; font-weight:700;">${invest_usd:,.2f} ({invest_usd*usd_krw:,.0f}원)</span>
                                </div>
                                <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                                    <span style="color:#94a3b8; font-size:12px;">현재 평가총액:</span>
                                    <span style="font-family:'JetBrains Mono'; font-weight:700;">${current_usd:,.2f}</span>
                                </div>
                                <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                                    <span style="color:#94a3b8; font-size:12px;">예상 수수료:</span>
                                    <span style="font-family:'JetBrains Mono'; color:#f43f5e;">-${fee_usd:,.2f}</span>
                                </div>
                                <hr style="margin:8px 0;">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="font-weight:700; font-size:13px;">순손익 (세전):</span>
                                    <span class="{p_color}" style="font-size:18px; font-weight:800; font-family:'JetBrains Mono';">
                                        ${net_profit_usd:,.2f} ({roi_pct:+.2f}%)
                                    </span>
                                </div>
                                <div style="text-align:right; font-size:13px;" class="{p_color}">
                                    약 <b>{net_profit_krw:,.0f} 원</b>
                                </div>
                            </div>
                            """)

                with col_news:
                    st.markdown("""<div style="font-weight:700; color:#38bdf8; margin-bottom:8px;">📰 실시간 구글 뉴스 & AI 센티멘트 피드</div>""", unsafe_allow_html=True)
                    news_list = get_google_news(ticker)
                    if news_list:
                        for n in news_list:
                            render_html(f"""
                            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:10px; margin-bottom:8px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                    <span class="{n['badge_class']}">{n['sentiment']}</span>
                                    <span style="font-size:10px; color:#64748b;">{n['date']}</span>
                                </div>
                                <a href="{n['link']}" target="_blank" style="color:#e2e8f0; font-size:12px; font-weight:700; text-decoration:none; line-height:1.4;">
                                    {n['title']}
                                </a>
                            </div>
                            """)
                    else:
                        st.markdown("<div style='color:#64748b; font-size:12px;'>최신 뉴스를 불러올 수 없습니다.</div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # TAB 2: 100종목 실시간 스캐너
    # --------------------------------------------------------------------------
    with tab2:
        st.markdown('<h3 style="margin:0 0 10px 0; font-weight:800;">🎯 100종목 실시간 AI 스캐너</h3>', unsafe_allow_html=True)
        st.markdown('<p style="color:#94a3b8; font-size:13px; margin-bottom:14px;">월가 4대 명인 전략(박스권 돌파, 거래량 폭발, 공포 투매 과매도 반등)을 100개 종목에 일괄 적용하여 최적의 매수 타점을 포착합니다.</p>', unsafe_allow_html=True)

        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            selected_preset = st.selectbox("테마별 프리셋 선택", list(PRESET_WATCHLISTS.keys()))
        with col_p2:
            custom_input = st.text_area("스캔할 종목 티커 (공백 또는 콤마로 구분)", value=PRESET_WATCHLISTS[selected_preset], height=70)

        col_btn, col_filter = st.columns([1, 2])
        with col_btn:
            scan_triggered = st.button("🚀 실시간 100종목 초고속 스캔 시작", type="primary", use_container_width=True)
        with col_filter:
            signal_filter = st.radio("신호 필터", ["전체 보기", "🔥 STRONG BUY만", "🟢 PANIC BUY만", "모든 매수 신호(BUY 전체)"], horizontal=True)

        if scan_triggered or "last_scan_results" in st.session_state:
            if scan_triggered:
                with st.spinner("100개 종목 멀티스레드 다운로드 및 퀀트 분석 연산 중..."):
                    results = scan_multi_tickers(custom_input)
                    st.session_state.last_scan_results = results
            else:
                results = st.session_state.last_scan_results

            if not results:
                st.warning("스캔 결과가 없습니다. 티커를 확인해주세요.")
            else:
                filtered = results
                if signal_filter == "🔥 STRONG BUY만":
                    filtered = [r for r in results if "STRONG" in r['action']]
                elif signal_filter == "🟢 PANIC BUY만":
                    filtered = [r for r in results if "PANIC" in r['action']]
                elif signal_filter == "모든 매수 신호(BUY 전체)":
                    filtered = [r for r in results if r['is_buy']]

                render_html(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin:14px 0 10px 0;">
                    <span style="font-weight:700; font-size:14px;">총 {len(results)}개 종목 중 <span style="color:#38bdf8;">{len(filtered)}개</span> 포착</span>
                    <span style="font-size:12px; color:#94a3b8;">* STRONG BUY: 박스 돌파+거래량 1.5배 | PANIC BUY: 20일선 아래+RSI 25 이하</span>
                </div>
                """)

                for item in filtered:
                    chg_color = "#10b981" if item['change_pct'] >= 0 else "#f43f5e"
                    chg_sign = "+" if item['change_pct'] >= 0 else ""

                    render_html(f"""
                    <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px 16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                        <div style="display:flex; align-items:center; gap:14px; min-width:180px;">
                            <span style="font-size:18px; font-weight:800; font-family:'JetBrains Mono'; color:#ffffff;">{item['ticker']}</span>
                            <span class="{item['badge']}">{item['action']}</span>
                        </div>
                        <div style="font-family:'JetBrains Mono'; text-align:right; min-width:120px;">
                            <div style="font-size:15px; font-weight:800; color:#ffffff;">${item['price']:,.2f}</div>
                            <div style="font-size:12px; font-weight:700; color:{chg_color};">{chg_sign}{item['change_pct']:.2f}%</div>
                        </div>
                        <div style="font-size:12px; color:#94a3b8; display:flex; gap:16px;">
                            <span>RSI: <b style="color:#ffffff;">{item['rsi']:.1f}</b></span>
                            <span>거래량 배율: <b style="color:#ffffff;">{item['vol_ratio']:.1f}x</b></span>
                            <span>20일 박스권: <b style="color:#10b981;">${item['box_low']:.2f}</b> ~ <b style="color:#f43f5e;">${item['box_high']:.2f}</b></span>
                        </div>
                    </div>
                    """)

                df_export = pd.DataFrame(results)
                csv = df_export.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 스캔 결과 CSV 다운로드",
                    data=csv,
                    file_name=f"scanner_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )


if __name__ == "__main__":
    main()