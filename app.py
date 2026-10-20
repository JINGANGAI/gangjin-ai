import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import datetime
import os

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="GANGJIN AI TRADER", layout="centered", page_icon="📈", initial_sidebar_state="collapsed")

# --- 2. 고급 다크 테마 CSS ---
st.markdown("""
<meta name="google" content="notranslate">
<style>
    .stApp { background-color: #0d0d12 !important; }
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 600px; } 

    div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"] { 
        background-color: #1c1c24 !important; border: 1px solid #2c2c35 !important; border-radius: 12px !important; color: white !important; 
    }
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { color: white !important; font-weight: 600 !important; }

    .main-price-card { background-color: #1c1c24 !important; border: 1px solid #2c2c35 !important; padding: 20px !important; border-radius: 20px !important; margin-bottom: 15px !important; margin-top: 10px !important; }
    
    .index-wrapper { display: flex !important; justify-content: space-between !important; gap: 6px !important; margin-bottom: 20px !important; }
    .index-card { flex: 1 !important; background-color: #1c1c24 !important; border: 1px solid #2c2c35 !important; padding: 10px 2px !important; border-radius: 12px !important; text-align: center !important; min-width: 0 !important; }
    .index-name { color: #a1a1a6 !important; font-size: 10px !important; font-weight: 600 !important; margin-bottom: 4px !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;}
    .index-price { font-size: 12px !important; font-weight: 700 !important; margin-bottom: 2px !important;}
    .index-change { font-size: 9px !important; font-weight: 600 !important;}

    .detail-card { background-color: #1c1c24 !important; border: 1px solid #2c2c35 !important; padding: 20px !important; border-radius: 20px !important; }
    
    .text-white { color: #ffffff !important; font-weight: 700 !important; }
    .text-gray { color: #a1a1a6 !important; font-size: 13px !important; line-height: 1.7 !important; }
    .text-green { color: #00e676 !important; font-weight: 700 !important; }
    .text-red { color: #ff453a !important; font-weight: 700 !important; }
    .text-yellow { color: #ffd60a !important; font-weight: 700 !important; }
    .price-large { font-size: 32px !important; font-weight: 800 !important; color: #ffffff !important; margin: 5px 0 !important; letter-spacing: -0.5px !important;}
    
    .badge-green { background-color: rgba(0, 230, 118, 0.1) !important; color: #00e676 !important; border: 1px solid rgba(0, 230, 118, 0.3) !important; padding: 6px 12px !important; border-radius: 20px !important; font-size: 12px !important; font-weight: 700 !important; white-space: nowrap !important; display: inline-block !important; }
    .badge-red { background-color: rgba(255, 69, 58, 0.1) !important; color: #ff453a !important; border: 1px solid rgba(255, 69, 58, 0.3) !important; padding: 6px 12px !important; border-radius: 20px !important; font-size: 12px !important; font-weight: 700 !important; white-space: nowrap !important; display: inline-block !important; }
    
    hr { border: 0.5px solid #2c2c35 !important; margin: 15px 0 !important; }
    button[data-baseweb="tab"] { color: #a1a1a6 !important; font-weight: 600 !important; }
    button[aria-selected="true"] { color: #00e676 !important; border-bottom-color: #00e676 !important; }
    a.news-link { color: #0a84ff !important; text-decoration: none !important; font-size: 13px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. 데이터 함수들 ---
@st.cache_data(ttl=60) 
def get_market_indices():
    tickers = {"10년물 금리": "^TNX", "다우 선물": "YM=F", "S&P500 선물": "ES=F", "나스닥 선물": "NQ=F", "WTI": "CL=F"}
    results = []
    for name, ticker in tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if not data.empty:
                current = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                change = ((current - prev) / prev) * 100
                results.append({"name": name, "price": current, "change": change})
            else:
                results.append({"name": name, "price": 0, "change": 0})
        except:
            results.append({"name": name, "price": 0, "change": 0})
    return results

@st.cache_data(ttl=300) 
def get_google_news(ticker):
    query = urllib.parse.quote(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    news_items = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=5)
        root = ET.fromstring(response.read())
        for item in root.findall('.//item')[:3]:
            news_items.append({"title": item.find('title').text, "link": item.find('link').text, "date": item.find('pubDate').text[:16]})
        return news_items
    except:
        return []

@st.cache_data(ttl=3600) 
def get_gamma_wall(ticker, exp_date):
    try:
        opt_chain = yf.Ticker(ticker).option_chain(exp_date)
        calls = opt_chain.calls.groupby('strike')['openInterest'].sum()
        puts = opt_chain.puts.groupby('strike')['openInterest'].sum()
        return (calls.idxmax() if not calls.empty and calls.max() > 0 else None, puts.idxmax() if not puts.empty and puts.max() > 0 else None)
    except:
        return None, None

@st.cache_data(ttl=180)
def scan_watchlist(ticker_string):
    tickers = [t.strip().upper() for t in ticker_string.replace(',', ' ').split() if t.strip()]
    if not tickers: return []
    try:
        data = yf.download(tickers, period="3mo", group_by='ticker', threads=True, progress=False)
    except: return []

    signals = []
    for t in tickers:
        try:
            df = data[t].dropna() if len(tickers) > 1 else data.dropna()
            if len(df) < 20: continue
            
            c, h, l, v = df['Close'], df['High'], df['Low'], df['Volume']
            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
            box_high = h.rolling(20).max().iloc[-1]
            delta = c.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = (100 - (100 / (1 + gain / loss))).iloc[-1]
            vol_ratio = v.iloc[-1] / v.rolling(20).mean().iloc[-1] if v.rolling(20).mean().iloc[-1] else 1.0
            
            action = "WAIT"
            if c.iloc[-1] >= box_high and vol_ratio >= 1.5: action = "🔥 STRONG BUY"
            elif c.iloc[-1] >= box_high: action = "📈 BUY"
            elif c.iloc[-1] < ema20 and rsi <= 25.0: action = "🟢 PANIC BUY"
                
            if "BUY" in action:
                signals.append({"ticker": t, "price": c.iloc[-1], "action": action, "rsi": rsi, "vol": vol_ratio})
        except: pass
    signals.sort(key=lambda x: 0 if "PANIC" in x["action"] else (1 if "STRONG" in x["action"] else 2))
    return signals

# --- 4. 상단 타이틀 및 현재 시간 ---
# 서버 시간(UTC)에 9시간을 더해 한국 시간(KST)으로 표시
kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
current_time = kst_now.strftime('%H:%M:%S')

st.markdown(f"""
<div style="display:flex; justify-content:space-between; color:#a1a1a6; font-size:13px; margin-bottom: 15px; padding-left:5px;">
    <span>📈 LIVE | {current_time} KST</span>
    <span>BTC $81,402</span>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 개별 종목 분석", "🎯 100종목 스캐너"])

# ==========================================
# TAB 1: 개별 종목 분석
# ==========================================
with tab1:
    st.markdown('<h2 class="text-white" style="margin-bottom: 10px; font-size: 24px;">GANGJIN AI TRADER</h2>', unsafe_allow_html=True)
    ticker = st.text_input("종목 코드", value="IREN", label_visibility="collapsed", placeholder="종목 코드를 입력하세요").upper().strip()

    if ticker:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                change = current_price - hist['Close'].iloc[-2]
                change_pct = (change / hist['Close'].iloc[-2]) * 100
                
                ema10 = hist['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
                ema20 = hist['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
                box_high = hist['High'].rolling(20).max().iloc[-1]
                box_low = hist['Low'].rolling(20).min().iloc[-1]
                
                delta = hist['Close'].diff()
                rsi = (100 - (100 / (1 + delta.where(delta > 0, 0).rolling(14).mean() / -delta.where(delta < 0, 0).rolling(14).mean()))).iloc[-1]
                vol_ratio = hist['Volume'].iloc[-1] / hist['Volume'].rolling(20).mean().iloc[-1] if hist['Volume'].rolling(20).mean().iloc[-1] else 1.0

                hist['MA20'] = hist['Close'].rolling(20).mean()
                hist['BB_Mid'] = hist['Close'].rolling(20).mean()
                hist['BB_Std'] = hist['Close'].rolling(20).std()
                hist['BB_Upper'] = hist['BB_Mid'] + 2 * hist['BB_Std']
                hist['BB_Lower'] = hist['BB_Mid'] - 2 * hist['BB_Std']
                hist['Typical'] = (hist['High'] + hist['Low'] + hist['Close']) / 3
                hist['VWAP_Year'] = (hist['Typical'] * hist['Volume']).cumsum() / hist['Volume'].cumsum()
                hist['VWAP_Week'] = (hist['Typical'] * hist['Volume']).rolling(5).sum() / hist['Volume'].rolling(5).sum()
                day_vwap = (hist['Typical'].iloc[-1] * hist['Volume'].iloc[-1]) / hist['Volume'].iloc[-1] 
                
                color = "text-red" if change < 0 else "text-green"
                arrow = "▼" if change < 0 else "▲"
                
                # 4대 명인 로직
                if current_price >= box_high and vol_ratio >= 1.5:
                    action, css_class, reason = "🔥 STRONG BUY", "text-green", "박스권 돌파 + 거래량 폭발"
                    stop_loss, target_1, target_2 = current_price * 0.95, current_price * 1.10, current_price * 1.20
                elif current_price >= box_high:
                    action, css_class, reason = "📈 BUY", "text-green", "박스권 상단 돌파"
                    stop_loss, target_1, target_2 = current_price * 0.96, current_price * 1.07, current_price * 1.15
                elif current_price < ema20:
                    support_level = box_low if box_low < current_price else current_price * 0.97
                    stop_loss, target_1, target_2 = support_level * 0.98, current_price * 1.03, current_price * 1.05
                    if rsi <= 25.0:
                        action, css_class, reason = "🟢 PANIC BUY", "text-green", f"투매 과매도 반등 타점 (RSI {rsi:.1f})"
                    else:
                        action, css_class, reason = "⚠️ EXIT", "text-red", f"EMA20 이탈 (${ema20:.2f})"
                elif current_price > ema10:
                    action, css_class, reason = "✅ HOLD", "text-yellow", "10일선 상회 (추세 유지)"
                    stop_loss, target_1, target_2 = ema10 * 0.98, current_price * 1.05, current_price * 1.10
                else:
                    action, css_class, reason = "WAIT", "text-gray", "관망 구간"
                    stop_loss, target_1, target_2 = current_price * 0.955, current_price * 1.05, current_price * 1.08

                # 1. 메인 가격 카드
                st.markdown(f"""
                <div class="main-price-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <div class="text-white" style="font-size: 22px;">{ticker}</div>
                            <div class="text-gray" style="margin-bottom: 5px;">LIVE: ${current_price:,.2f}</div>
                            <div class="price-large {color}">{arrow} {change:,.2f} ({change_pct:.2f}%)</div>
                        </div>
                        <div style="text-align:right; margin-top: 5px;">
                            <div class="badge-green" style="margin-bottom: 8px;">RSI: {rsi:.1f}</div><br>
                            <div class="badge-red">변동성 주의</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 2. 글로벌 지수
                indices_data = get_market_indices()
                html_indices = '<div class="index-wrapper">'
                for idx in indices_data:
                    idx_color = "text-green" if idx['change'] >= 0 else "text-red"
                    sign = "+" if idx['change'] >= 0 else ""
                    price_str = f"{idx['price']:.2f}%" if idx['name'] == "10년물 금리" else (f"{idx['price']:,.0f}" if idx['price'] > 1000 else f"{idx['price']:,.2f}")
                    html_indices += f'<div class="index-card"><div class="index-name">{idx["name"]}</div><div class="index-price {idx_color}">{price_str}</div><div class="index-change {idx_color}">{sign}{idx["change"]:.1f}%</div></div>'
                html_indices += '</div>'
                st.markdown(html_indices, unsafe_allow_html=True)

                # 3. 수익 계산기 (미래에셋 기준)
                with st.expander("💰 수익 계산기 (미래에셋 기준)"):
                    col1, col2 = st.columns(2)
                    with col1:
                        buy_price = st.number_input("매수 평단가 ($)", value=float(current_price * 0.95), step=0.1)
                    with col2:
                        shares = st.number_input("보유 수량 (주)", value=10, step=1)
                    
                    if buy_price > 0 and shares > 0:
                        invest = buy_price * shares
                        current_val = current_price * shares
                        profit = current_val - invest
                        profit_pct = (profit / invest) * 100
                        
                        if profit > 0:
                            st.markdown(f"**현재 수익금:** <span class='text-green'>+${profit:,.2f} (+{profit_pct:.2f}%)</span>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"**현재 수익금:** <span class='text-red'>${profit:,.2f} ({profit_pct:.2f}%)</span>", unsafe_allow_html=True)

                # 4. 4대 명인 분석 카드
                with st.container(border=True):
                    st.markdown(f'<div class="text-white" style="font-size: 16px; margin-bottom: 10px;">🧠 4대 명인 분석 (아이렌봇)</div>', unsafe_allow_html=True)
                    st.markdown(f"""
                        <div class="text-gray">
                        • 20일 박스: <b>${box_low:,.2f} ~ ${box_high:,.2f}</b><br>
                        • EMA10: <b>${ema10:,.2f}</b> | EMA20: <b>${ema20:,.2f}</b><br>
                        • 거래량 비율: <b>{vol_ratio:.1f}x</b>
                        </div>
                        <hr>
                        <div class="text-white" style="font-size: 16px; margin-bottom: 10px;">🤖 AI 액션</div>
                        <div class="text-gray" style="margin-bottom: 15px;">
                            • 판단: <span class="{css_class}" style="font-size: 18px;">{action}</span><br>
                            • 사유: {reason}
                        </div>
                        <hr>
                        <div class="text-white" style="font-size: 16px; margin-bottom: 10px;">🎯 매매 가이드</div>
                        <div class="text-gray">
                            • 지지선: <span class="text-green">${box_low:,.2f}</span> | • 손절선: <span class="text-red">${stop_loss:,.2f}</span><br>
                            • 1차 익절: <span class="text-green">${target_1:,.2f}</span> | • 2차 익절: <span class="text-green">${target_2:,.2f}</span>
                        </div>
                    """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                
                # 5. 옵션 및 차트 설정
                col_a, col_b = st.columns(2)
                with col_a:
                    auto_refresh = st.checkbox("🔄 1분 자동 새로고침", value=False)
                    if auto_refresh: st_autorefresh(interval=60000, key="auto_refresh") 
                with col_b:
                    show_gamma = st.checkbox("🎯 감마벽 표시", value=False)

                with st.expander("📊 보조지표(VWAP) 상세 설정"):
                    c1, c2, c3 = st.columns(3)
                    show_vwap_year = c1.checkbox("1년 VWAP", value=True)
                    show_vwap_week = c2.checkbox("1주 VWAP", value=False)
                    show_vwap_day = c3.checkbox("당일 VWAP", value=False)
                    
                call_wall, put_wall = None, None
                if show_gamma:
                    try:
                        options_list = stock.options
                        if options_list:
                            selected_exp = st.selectbox("📅 만기일 선택", options_list)
                            call_wall, put_wall = get_gamma_wall(ticker, selected_exp)
                    except: pass

                # 6. 차트 렌더링
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
                fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], increasing_line_color='#ff453a', decreasing_line_color='#0a84ff', name='주가'), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_Upper'], line=dict(color='rgba(255,255,255,0.2)', width=1, dash='dot'), name='BB 상한'), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_Lower'], line=dict(color='rgba(255,255,255,0.2)', width=1, dash='dot'), name='BB 하한'), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=hist['MA20'], line=dict(color='#ffd60a', width=1.5), name='MA20'), row=1, col=1)

                if show_vwap_year: fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Year'], line=dict(color='#00e676', width=1.5, dash='dash'), name='1년 VWAP'), row=1, col=1)
                if show_vwap_week: fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Week'], line=dict(color='#0a84ff', width=1.5), name='1주 VWAP'), row=1, col=1)
                if show_vwap_day: fig.add_hline(y=day_vwap, line_dash="solid", line_color="#a1a1a6", line_width=1.5, row=1, col=1)
                if show_gamma:
                    if call_wall: fig.add_hline(y=call_wall, line_dash="dash", line_color="#ff453a", line_width=2, row=1, col=1)
                    if put_wall: fig.add_hline(y=put_wall, line_dash="dash", line_color="#0a84ff", line_width=2, row=1, col=1)

                fig.add_hline(y=current_price, line_dash="solid", line_color="#ffffff", line_width=1, row=1, col=1)
                colors = ['#ff453a' if r['Close'] >= r['Open'] else '#0a84ff' for _, r in hist.iterrows()]
                fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=colors, name='거래량'), row=2, col=1)
                fig.add_hline(y=box_high, line_dash="dot", line_color="#ff453a", line_width=1, row=1, col=1)
                fig.add_hline(y=box_low, line_dash="dot", line_color="#00e676", line_width=1, row=1, col=1)

                fig.update_layout(
                    template='plotly_dark', paper_bgcolor='#0d0d12', plot_bgcolor='#0d0d12', height=450, margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False, showlegend=False,
                    xaxis=dict(showgrid=False, rangebreaks=[dict(bounds=["sat", "mon"])], tickfont=dict(color="#a1a1a6")),
                    yaxis=dict(showgrid=True, gridcolor='#1c1c24', tickfont=dict(color='#a1a1a6'), tickformat=",.2f"),
                    yaxis2=dict(showgrid=False, tickfont=dict(color='#a1a1a6'), tickformat="~s")
                )
                st.plotly_chart(fig, use_container_width=True)

                # 7. 뉴스
                st.markdown("<br>", unsafe_allow_html=True)
                news_list = get_google_news(ticker)
                if news_list:
                    st.markdown('<div class="text-white" style="font-size: 16px; margin-bottom: 10px;">📰 실시간 뉴스</div>', unsafe_allow_html=True)
                    for news in news_list:
                        st.markdown(f"""
                        <div style="background-color: #1c1c24; border: 1px solid #2c2c35; padding: 12px; border-radius: 12px; margin-bottom: 8px;">
                            <a class="news-link" href="{news['link']}" target="_blank">🔗 {news['title']}</a><br>
                            <span style="color: #a1a1a6; font-size: 11px;">발행: {news['date']}</span>
                        </div>
                        """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"데이터를 불러오는 중 오류가 발생했습니다.")

# ==========================================
# TAB 2: 100종목 스캐너 (종목 저장 기능)
# ==========================================
with tab2:
    WATCHLIST_FILE = "my_watchlist.txt"
    
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            saved_tickers = f.read()
    else:
        saved_tickers = "IREN, CRWV, NBIS, SMR, CIFR, CLSK, HUT, MARA, RIOT, WULF, BTBT, CORZ, OKLO, NNE, SOUN, BBAI, AI, RGTI, QBTS, QUBT, IONQ, ASTS, RKLB, LUNR, ARM, SMCI, MRVL, ALAB, TEM, PLTR, APP, UPST, AFRM, COIN, MSTR, HOOD, CVNA, SYM, SERV, AUR, LAZR, AEHR, POET, NVTS, WVE, CRSP, BEAM, NTLA, RXRX, ACHR, AG, HL, PAAS, CDE, FSM, EXK, GATO, KGC, IAG, NG, AU, SBSW, EQT, AR, BTU, ARCH, AMR, TPL, OXY, CHK, RRC, CRK, CCJ, UEC, NXE, DNN, UUUU, MP, LAC, FCX, ZIM, STNG, FRO, NAT, TRMD, INSW, GSL, HSHP, SBLK, TNP, RCAT, AVAV, KTOS, HEI, HII, BWX, CAE, MRCY, KAMN, AIR"

    st.markdown('<h3 class="text-white" style="margin-bottom: 5px;">🎯 4대 명인 종목 스캐너</h3>', unsafe_allow_html=True)
    st.caption("최대 100개의 종목을 한 번에 스캔하여, 지금 당장 매수 타점(BUY)인 종목만 찾아냅니다.")
    
    ticker_list_input = st.text_area("감시할 종목 코드 입력 (쉼표로 구분)", value=saved_tickers, height=150)
    
    col_btn1, col_btn2 = st.columns([1, 2])
    
    with col_btn1:
        if st.button("💾 리스트 저장", use_container_width=True):
            with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
                f.write(ticker_list_input)
            st.success("저장 완료!")
            
    with col_btn2:
        scan_btn = st.button("🔍 타점 스캔 시작", type="primary", use_container_width=True)
        
    if scan_btn:
        with st.spinner("100종목 로직 계산 중..."):
            signals = scan_watchlist(ticker_list_input)
            
            if signals:
                st.success(f"{len(signals)}개의 종목이 매수 타점입니다.")
                for sig in signals:
                    st.markdown(f"""
                    <div style="background-color: #1c1c24; border: 1px solid rgba(0, 230, 118, 0.5); padding: 15px; border-radius: 12px; margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h3 style="margin:0; color:white; font-size:18px;">{sig['ticker']}</h3>
                            <span class="text-green" style="font-weight:bold;">{sig['action']}</span>
                        </div>
                        <div class="text-gray" style="margin-top: 5px;">
                            • 현재가: ${sig['price']:,.2f} | • RSI: {sig['rsi']:.1f} | • 거래량: {sig['vol']:.1f}x
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("현재 매수 타점에 들어온 종목이 없습니다.")