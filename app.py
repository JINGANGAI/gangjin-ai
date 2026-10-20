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

st.set_page_config(page_title="GANGJIN AI TRADER", layout="centered", page_icon="📈", initial_sidebar_state="collapsed")

st.markdown("""
<meta name="google" content="notranslate">
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 600px; } 
    .stApp { background-color: #0b0f19; }
    
    div[data-baseweb="input"], div[data-baseweb="textarea"] { background-color: #121620 !important; border: 1px solid #1e2433 !important; border-radius: 10px !important; color: white !important; }
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { color: white !important; font-size: 14px !important; font-weight: bold !important; }
    div[data-baseweb="select"] > div { background-color: #121620 !important; border-color: #1e2433 !important; color: white !important; }
    
    .main-card { background: linear-gradient(145deg, #101c16, #0c1410); border: 1px solid #1f3b2a; padding: 15px; border-radius: 15px; margin-bottom: 15px; margin-top: 10px; }
    .index-wrapper { display: flex; justify-content: space-between; gap: 4px; margin-bottom: 15px; }
    .index-card { flex: 1; background-color: #121620; border: 1px solid #1e2433; padding: 8px 2px; border-radius: 8px; text-align: center; min-width: 0; }
    .index-name { color: #ffffff; font-size: 10px; font-weight: 700; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .index-price { font-size: 11px; font-weight: bold; margin-bottom: 2px;}
    .index-change { font-size: 9px; font-weight: bold;}
    
    .detail-card { background-color: #121620; border: 1px solid #1e2433; padding: 15px; border-radius: 12px; }
    .text-white { color: #ffffff; font-weight: 700; }
    .text-gray { color: #8b949e; font-size: 13px; line-height: 1.6; }
    .text-green { color: #2ea043; font-weight: 700; }
    .text-red { color: #f85149; font-weight: 700; }
    .text-yellow { color: #d29922; font-weight: 700; }
    .price-large { font-size: 28px; font-weight: 800; color: white; margin: 5px 0; letter-spacing: -0.5px;}
    
    .badge-green { background-color: #132a1c; color: #3fb950; border: 1px solid #2ea043; padding: 4px 8px; border-radius: 20px; font-size: 11px; font-weight: bold; white-space: nowrap; display: inline-block; }
    .badge-red { background-color: #2d1214; color: #f85149; border: 1px solid #da3633; padding: 4px 8px; border-radius: 20px; font-size: 11px; font-weight: bold; white-space: nowrap; display: inline-block; }
    hr { border: 0.5px solid #1e2433; margin: 12px 0; }
    
    a.news-link { color: #58a6ff !important; text-decoration: none; font-size: 13px; font-weight: bold; }
    a.news-link:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

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
        xml_data = response.read()
        root = ET.fromstring(xml_data)
        for item in root.findall('.//item')[:3]:
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text[:16]
            news_items.append({"title": title, "link": link, "date": pub_date})
        return news_items
    except Exception:
        return []

@st.cache_data(ttl=3600) 
def get_gamma_wall(ticker, exp_date):
    try:
        stock = yf.Ticker(ticker)
        opt_chain = stock.option_chain(exp_date)
        calls = opt_chain.calls.groupby('strike')['openInterest'].sum()
        puts = opt_chain.puts.groupby('strike')['openInterest'].sum()
        top_call_strike = calls.idxmax() if not calls.empty and calls.max() > 0 else None
        top_put_strike = puts.idxmax() if not puts.empty and puts.max() > 0 else None
        return top_call_strike, top_put_strike
    except Exception:
        return None, None

# ⭐️ 100종목 스캐너 함수 (병렬 다운로드)
@st.cache_data(ttl=180) # 3분 캐시
def scan_watchlist(ticker_string):
    tickers = [t.strip().upper() for t in ticker_string.replace(',', ' ').split() if t.strip()]
    if not tickers:
        return []
    
    # 한 번에 여러 종목 데이터 다운로드 (속도 향상)
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
                
            close = df['Close']
            high = df['High']
            low = df['Low']
            vol = df['Volume']
            
            ema10 = close.ewm(span=10, adjust=False).mean().iloc[-1]
            ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
            box_high = high.rolling(window=20).max().iloc[-1]
            box_low = low.rolling(window=20).min().iloc[-1]
            
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            current_price = close.iloc[-1]
            avg_vol = vol.rolling(window=20).mean().iloc[-1]
            vol_ratio = vol.iloc[-1] / avg_vol if avg_vol else 1.0
            
            # 4대 명인 로직 적용
            action = "WAIT"
            if current_price >= box_high and vol_ratio >= 1.5:
                action = "🔥 STRONG BUY"
            elif current_price >= box_high:
                action = "📈 BUY"
            elif current_price < ema20 and rsi <= 25.0:
                action = "🟢 PANIC BUY"
                
            if "BUY" in action:
                signals.append({
                    "ticker": t, 
                    "price": current_price, 
                    "action": action, 
                    "rsi": rsi,
                    "vol": vol_ratio
                })
        except Exception:
            pass
            
    # 신호가 강한 순서대로 정렬 (PANIC BUY -> STRONG BUY -> BUY)
    signals.sort(key=lambda x: 0 if "PANIC" in x["action"] else (1 if "STRONG" in x["action"] else 2))
    return signals

# --- 메인 화면 시작 ---
st.markdown(f"""
<div style="display:flex; justify-content:space-between; color:#8b949e; font-size:13px; margin-bottom: 10px; padding-left: 5px;">
    <span>📈 LIVE MARKET | {time.strftime('%H:%M:%S')} | BTC $81,402</span>
</div>
""", unsafe_allow_html=True)

# ⭐️ 탭 UI 생성 (개별 종목 분석 / 100종목 스캐너)
tab1, tab2 = st.tabs(["📊 개별 종목 분석", "🎯 100종목 스캐너"])

# ==========================================
# TAB 1: 개별 종목 분석 (기존 기능)
# ==========================================
with tab1:
    st.markdown('<h2 class="text-white" style="margin-bottom: 15px; padding-left: 5px;">GANGJIN AI TRADER</h2>', unsafe_allow_html=True)
    ticker_input = st.text_input("종목 코드 입력", value="IREN", label_visibility="collapsed", placeholder="종목 코드를 입력하세요")
    ticker = ticker_input.upper().strip()

    if ticker:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2]
                change = current_price - prev_close
                change_pct = (change / prev_close) * 100
                
                ema10 = hist['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
                ema20 = hist['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
                box_high = hist['High'].rolling(window=20).max().iloc[-1]
                box_low = hist['Low'].rolling(window=20).min().iloc[-1]
                
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = (100 - (100 / (1 + rs))).iloc[-1]
                
                avg_vol = hist['Volume'].rolling(window=20).mean().iloc[-1]
                vol_ratio = hist['Volume'].iloc[-1] / avg_vol if avg_vol else 1.0

                hist['MA20'] = hist['Close'].rolling(window=20).mean()
                hist['BB_Mid'] = hist['Close'].rolling(window=20).mean()
                hist['BB_Std'] = hist['Close'].rolling(window=20).std()
                hist['BB_Upper'] = hist['BB_Mid'] + 2 * hist['BB_Std']
                hist['BB_Lower'] = hist['BB_Mid'] - 2 * hist['BB_Std']
                hist['Typical'] = (hist['High'] + hist['Low'] + hist['Close']) / 3
                hist['VWAP_Year'] = (hist['Typical'] * hist['Volume']).cumsum() / hist['Volume'].cumsum()
                hist['VWAP_Week'] = (hist['Typical'] * hist['Volume']).rolling(window=5).sum() / hist['Volume'].rolling(window=5).sum()
                day_vwap = (hist['Typical'].iloc[-1] * hist['Volume'].iloc[-1]) / hist['Volume'].iloc[-1] 
                
                color = "text-red" if change < 0 else "text-green"
                arrow = "▼" if change < 0 else "▲"
                
                if current_price >= box_high and vol_ratio >= 1.5:
                    action, css_class, reason = "🔥 STRONG BUY", "text-green", "박스권 돌파 + 거래량 폭발"
                    stop_loss = current_price * 0.95
                    target_1, target_2 = current_price * 1.10, current_price * 1.20
                elif current_price >= box_high:
                    action, css_class, reason = "📈 BUY", "text-green", "박스권 상단 돌파"
                    stop_loss = current_price * 0.96
                    target_1, target_2 = current_price * 1.07, current_price * 1.15
                elif current_price < ema20:
                    support_level = box_low if box_low < current_price else current_price * 0.97
                    stop_loss = support_level * 0.98
                    target_1, target_2 = current_price * 1.03, current_price * 1.05
                    if rsi <= 25.0:
                        action, css_class, reason = "🟢 PANIC BUY", "text-green", f"투매 과매도 반등 타점 (RSI {rsi:.1f})"
                    else:
                        action, css_class, reason = "⚠️ EXIT", "text-red", f"EMA20 이탈 (${ema20:.2f})"
                elif current_price > ema10:
                    action, css_class, reason = "✅ HOLD", "text-yellow", "10일선 상회 (추세 유지)"
                    stop_loss = ema10 * 0.98
                    target_1, target_2 = current_price * 1.05, current_price * 1.10
                else:
                    action, css_class, reason = "WAIT", "text-gray", "관망 구간"
                    stop_loss = current_price * 0.955
                    target_1, target_2 = current_price * 1.05, current_price * 1.08

                st.markdown(f"""
                <div class="main-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <div class="text-white" style="font-size: 20px;">{ticker}</div>
                            <div class="text-gray">LIVE: ${current_price:,.2f}</div>
                            <div class="price-large {color}">{arrow} {change:,.2f} ({change_pct:.2f}%)</div>
                        </div>
                        <div style="text-align:right; margin-top: 5px;">
                            <div class="badge-green" style="margin-bottom: 8px;">RSI: {rsi:.2f}</div><br>
                            <div class="badge-red">📉 변동성 주의</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                indices_data = get_market_indices()
                html_indices = '<div class="index-wrapper">'
                for idx in indices_data:
                    idx_color = "text-green" if idx['change'] >= 0 else "text-red"
                    sign = "+" if idx['change'] >= 0 else ""
                    
                    if idx['name'] == "10년물 금리":
                        price_str = f"{idx['price']:.2f}%"
                    else:
                        price_str = f"{idx['price']:,.0f}" if idx['price'] > 1000 else f"{idx['price']:,.2f}"
                        
                    html_indices += f'<div class="index-card"><div class="index-name">{idx["name"]}</div><div class="index-price {idx_color}">{price_str}</div><div class="index-change {idx_color}">{sign}{idx["change"]:.1f}%</div></div>'
                html_indices += '</div>'
                st.markdown(html_indices, unsafe_allow_html=True)

                st.markdown(f"""
                <div class="detail-card">
                    <div class="text-white" style="margin-bottom: 8px;">🧠 4대 명인 종합 분석 (아이렌봇 로직)</div>
                    <div class="text-gray" style="margin-bottom: 10px;">
                        • 20일 박스 상단: <b>${box_high:,.2f}</b> | 하단: <b>${box_low:,.2f}</b><br>
                        • EMA10: <b>${ema10:,.2f}</b> | EMA20: <b>${ema20:,.2f}</b><br>
                        • 거래량 비율: <b>{vol_ratio:.1f}x</b>
                    </div>
                    <hr>
                    <div class="text-white" style="margin-bottom: 8px;">🤖 AI 펀드매니저 액션</div>
                    <div class="text-gray">
                        • 판단: <span class="{css_class}" style="font-weight:bold; font-size:16px;">{action}</span><br>
                        • 사유: {reason}
                    </div>
                    <hr>
                    <div class="text-white" style="margin-bottom: 8px;">🎯 매매 가이드 (아이렌봇 기준)</div>
                    <div class="text-gray">
                        • <b>지지선:</b> <span class="text-green">${box_low:,.2f}</span> (20일 박스 하단)<br>
                        • <b>손절선:</b> <span class="text-red">${stop_loss:,.2f}</span><br>
                        • <b>1차 익절:</b> <span class="text-green">${target_1:,.2f}</span><br>
                        • <b>2차 익절:</b> <span class="text-green">${target_2:,.2f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                auto_refresh = st.checkbox("🔄 1분마다 자동 새로고침 (실시간 감시)", value=False)
                if auto_refresh:
                    st_autorefresh(interval=60000, key="auto_refresh") 

                st.markdown("##### 📊 보조지표 설정")
                col1, col2, col3 = st.columns(3)
                with col1:
                    show_vwap_year = st.checkbox("1년 누적 VWAP", value=True)
                with col2:
                    show_vwap_week = st.checkbox("1주(5일) VWAP", value=False)
                with col3:
                    show_vwap_day = st.checkbox("당일 VWAP", value=False)
                    
                show_gamma = st.checkbox("🎯 옵션 감마벽(Gamma Wall) 표시 (대형주만 지원)", value=False)
                
                selected_exp = None
                call_wall, put_wall = None, None
                
                if show_gamma:
                    try:
                        options_list = stock.options
                        if options_list:
                            selected_exp = st.selectbox("📅 옵션 만기일 선택", options_list)
                            call_wall, put_wall = get_gamma_wall(ticker, selected_exp)
                            if call_wall or put_wall:
                                st.caption(f"👉 **{selected_exp} 만기 기준** OI(미결제약정) 최대 지점")
                            else:
                                st.warning("⚠️ 선택한 만기일의 옵션 미결제약정 데이터가 없습니다.")
                        else:
                            st.warning("⚠️ 이 종목은 옵션 시장 데이터가 없습니다. (대형주만 지원)")
                    except Exception as e:
                        st.warning(f"⚠️ 옵션 데이터를 불러올 수 없습니다.")

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

                fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], increasing_line_color='red', decreasing_line_color='blue', name='주가'), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_Upper'], line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'), name='BB 상한'), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=hist['BB_Lower'], line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'), name='BB 하한'), row=1, col=1)
                fig.add_trace(go.Scatter(x=hist.index, y=hist['MA20'], line=dict(color='#FFA500', width=1.5), name='MA20'), row=1, col=1)

                if show_vwap_year:
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Year'], line=dict(color='yellow', width=1.5, dash='dash'), name='1년 VWAP'), row=1, col=1)
                    fig.add_annotation(x=1.01, xref="paper", y=0.95, yref="paper", text=f"<b>1Y: {hist['VWAP_Year'].iloc[-1]:,.2f}</b>", showarrow=False, xanchor="left", yanchor="middle", bgcolor="yellow", font=dict(color="black", size=11), bordercolor="yellow", borderwidth=1)
                if show_vwap_week:
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Week'], line=dict(color='#00FF00', width=1.5), name='1주 VWAP'), row=1, col=1)
                    fig.add_annotation(x=1.01, xref="paper", y=0.90, yref="paper", text=f"<b>1W: {hist['VWAP_Week'].iloc[-1]:,.2f}</b>", showarrow=False, xanchor="left", yanchor="middle", bgcolor="#00FF00", font=dict(color="black", size=11), bordercolor="#00FF00", borderwidth=1)
                if show_vwap_day:
                    fig.add_hline(y=day_vwap, line_dash="solid", line_color="white", line_width=1.5, row=1, col=1)
                    fig.add_annotation(x=1.01, xref="paper", y=0.85, yref="paper", text=f"<b>Day: {day_vwap:,.2f}</b>", showarrow=False, xanchor="left", yanchor="middle", bgcolor="white", font=dict(color="black", size=11), bordercolor="white", borderwidth=1)

                if show_gamma:
                    if call_wall:
                        fig.add_hline(y=call_wall, line_dash="dash", line_color="#FF00FF", line_width=2, row=1, col=1)
                        fig.add_annotation(x=1.01, xref="paper", y=0.75, yref="paper", text=f"<b>🔴 Call Wall: {call_wall}</b>", showarrow=False, xanchor="left", yanchor="middle", bgcolor="#FF00FF", font=dict(color="white", size=10), bordercolor="#FF00FF", borderwidth=1)
                    if put_wall:
                        fig.add_hline(y=put_wall, line_dash="dash", line_color="#00FFFF", line_width=2, row=1, col=1)
                        fig.add_annotation(x=1.01, xref="paper", y=0.70, yref="paper", text=f"<b>🟢 Put Wall: {put_wall}</b>", showarrow=False, xanchor="left", yanchor="middle", bgcolor="#00FFFF", font=dict(color="black", size=10), bordercolor="#00FFFF", borderwidth=1)

                fig.add_hline(y=current_price, line_dash="solid", line_color="#0055ff", line_width=1, row=1, col=1)
                fig.add_annotation(x=1.01, xref="paper", y=0.80, yref="paper", text=f"<b>Cur: {current_price:,.2f}</b>", showarrow=False, xanchor="left", yanchor="middle", bgcolor="#0055ff", font=dict(color="white", size=11), bordercolor="#0055ff", borderwidth=1)

                colors = ['red' if row['Close'] >= row['Open'] else 'blue' for index, row in hist.iterrows()]
                fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

                fig.add_hline(y=box_high, line_dash="dot", line_color="red", line_width=1, annotation_text=f"최고 {box_high:,.2f}", annotation_position="top left", annotation_font_color="red", row=1, col=1)
                fig.add_hline(y=box_low, line_dash="dot", line_color="#00ff00", line_width=1, annotation_text=f"최저 {box_low:,.2f}", annotation_position="bottom left", annotation_font_color="#00ff00", row=1, col=1)

                fig.update_layout(
                    template='plotly_dark', paper_bgcolor='#0b0f19', plot_bgcolor='#0b0f19', height=550, margin=dict(l=10, r=85, t=30, b=10), xaxis_rangeslider_visible=False, showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
                    xaxis=dict(showgrid=False, rangebreaks=[dict(bounds=["sat", "mon"])]),
                    yaxis=dict(showgrid=True, gridcolor='#1e2433', tickfont=dict(color='white'), tickformat=",.2f"),
                    yaxis2=dict(showgrid=False, tickfont=dict(color='white'), tickformat="~s")
                )

                st.plotly_chart(fig, use_container_width=True)

                st.markdown("<br><br>", unsafe_allow_html=True)
                st.markdown(f"##### 📰 {ticker} 실시간 뉴스 (Google)")
                news_list = get_google_news(ticker)
                if news_list:
                    for news in news_list:
                        st.markdown(f"""
                        <div style="background-color: #121620; border: 1px solid #1e2433; padding: 10px; border-radius: 8px; margin-bottom: 8px;">
                            <a class="news-link" href="{news['link']}" target="_blank">🔗 {news['title']}</a><br>
                            <span style="color: #8b949e; font-size: 11px;">발행: {news['date']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info(f"'{ticker}' 종목의 뉴스를 구글에서 찾을 수 없습니다.")

            else:
                st.error("데이터를 불러올 수 없습니다. 종목 코드를 확인해 주세요.")
        except Exception as e:
            st.error(f"오류 발생: {e}")

# ==========================================
# TAB 2: 100종목 스캐너
# ==========================================
with tab2:
    st.markdown('<h3 class="text-white" style="margin-bottom: 5px;">🎯 4대 명인 종목 스캐너</h3>', unsafe_allow_html=True)
    st.caption("최대 100개의 종목을 한 번에 스캔하여, 지금 당장 매수 타점(BUY)인 종목만 찾아냅니다.")
    
    default_tickers = "AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, META, AMD, NFLX, AVAV, IREN, PLTR, COIN, MSTR, SOFI"
    ticker_list_input = st.text_area("감시할 종목 코드 입력 (쉼표로 구분)", value=default_tickers, height=100)
    
    if st.button("🔍 4대 명인 타점 스캔 시작", type="primary", use_container_width=True):
        with st.spinner("야후 파이낸스에서 데이터를 불러와 4대 명인 로직을 계산 중입니다..."):
            signals = scan_watchlist(ticker_list_input)
            
            if signals:
                st.success(f"총 {len(signals)}개의 종목이 매수 타점에 진입했습니다!")
                for sig in signals:
                    st.markdown(f"""
                    <div style="background-color: #121620; border: 1px solid #2ea043; padding: 15px; border-radius: 12px; margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h3 style="margin:0; color:white;">{sig['ticker']}</h3>
                            <span class="text-green" style="font-weight:bold;">{sig['action']}</span>
                        </div>
                        <div class="text-gray" style="margin-top: 5px;">
                            • 현재가: ${sig['price']:,.2f} | • RSI: {sig['rsi']:.1f} | • 거래량: {sig['vol']:.1f}x
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("현재 입력하신 종목 중 4대 명인의 매수 타점(BUY)에 들어온 종목이 없습니다.")