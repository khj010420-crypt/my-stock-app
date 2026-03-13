import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import FinanceDataReader as fdr

# 1. 페이지 설정
st.set_page_config(page_title="Hysteresis Quant Terminal", layout="wide")
st.markdown("""<style>.stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #31333f; }</style>""", unsafe_allow_html=True)

st.title("🏛️ Hysteresis 프로 퀀트 터미널")

# 2. 전 세계 리스트 로드 (안전 수집)
@st.cache_data(ttl=86400)
def get_all_stock_list():
    master_dict = {}
    try:
        df_kr = fdr.StockListing('KRX')
        df_kr['Ticker'] = df_kr.apply(lambda r: f"{r['Code']}.KS" if r['Market']=='KOSPI' else f"{r['Code']}.KQ", axis=1)
        master_dict.update(dict(zip(df_kr['Name'], df_kr['Ticker'])))
    except: pass
    try:
        df_ndaq = fdr.StockListing('NASDAQ')
        master_dict.update(dict(zip(df_ndaq['Name'] + " (NASDAQ)", df_ndaq['Symbol'])))
    except: pass
    try:
        df_sp = fdr.StockListing('S&P500')
        master_dict.update(dict(zip(df_sp['Name'] + " (S&P500)", df_sp['Symbol'])))
    except: pass

    custom_us = {"삼성전자":"005930.KS", "SK하이닉스":"000660.KS", "애플":"AAPL", "테슬라":"TSLA", "엔비디아":"NVDA", "마이크로소프트":"MSFT", "알파벳(구글)":"GOOGL", "아마존":"AMZN", "메타":"META", "인텔":"INTC", "AMD":"AMD", "SOXL":"SOXL", "TQQQ":"TQQQ"}
    master_dict.update(custom_us)
    return master_dict

all_stocks_dict = get_all_stock_list()

# 3. 데이터 로드: 시가총액 상위
KOSPI_TOP = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "LG에너지솔루션": "373220.KS", "삼성바이오로직스": "207940.KS", "현대차": "005380.KS", "기아": "000270.KS", "셀트리온": "068270.KS", "POSCO홀딩스": "005490.KS", "NAVER": "035420.KS", "KB금융": "105560.KS"}
NASDAQ_TOP = {"애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "알파벳(구글)": "GOOGL", "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "넷플릭스": "NFLX", "코스트코": "COST"}

@st.cache_data(ttl=300)
def get_market_ranking(market_dict):
    data = []
    for name, ticker in market_dict.items():
        try:
            hist = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
            close_prices = hist['Close'] if isinstance(hist.columns, pd.MultiIndex) else hist
            prices = close_prices[ticker].dropna() if isinstance(close_prices, pd.DataFrame) else close_prices.dropna()
            if len(prices) >= 2:
                current = float(prices.iloc[-1])
                prev = float(prices.iloc[-2])
                change_pct = ((current - prev) / prev) * 100
                data.append({"종목명": name, "티커": ticker, "현재가": f"{current:,.2f}", "등락률(%)": round(change_pct, 2)})
        except: continue
    return pd.DataFrame(data)

st.subheader("🏆 시가총액 상위 TOP 10 실시간 시세")
tab1, tab2 = st.tabs(["🇰🇷 KOSPI 상위 10", "🇺🇸 NASDAQ 상위 10"])
with tab1: st.dataframe(get_market_ranking(KOSPI_TOP).style.format({"등락률(%)": "{:+.2f}%"}), use_container_width=True, hide_index=True)
with tab2: st.dataframe(get_market_ranking(NASDAQ_TOP).style.format({"등락률(%)": "{:+.2f}%"}), use_container_width=True, hide_index=True)
st.write("---")

# 4. 검색창
st.subheader("🔍 정밀 분석 및 백테스트 검색창")
search_mode = st.radio("검색 방식 선택", ["📝 회사 이름으로 검색", "⌨️ 티커(Ticker) 직접 입력"], horizontal=True)

search_name, final_ticker = None, None
if "이름" in search_mode:
    search_name = st.selectbox("종목명을 입력하세요 (한국어/영어 지원)", options=list(all_stocks_dict.keys()), index=None)
    if search_name: final_ticker = all_stocks_dict.get(search_name)
else:
    search_name = st.text_input("티커를 입력하세요 (예: TQQQ, 035720.KS)")
    if search_name: final_ticker = search_name.upper()

# 5. 퀀트 엔진 및 백테스트 (스윙 최적화)
if final_ticker:
    with st.spinner(f'[{search_name}] 퀀트 연산을 수행 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5 + 100) # MA60 계산을 위한 여유분
        
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty and len(stock_df) > 100:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            stock_df.index = stock_df.index.tz_localize(None)
            
            combined_df = stock_df.copy()
            
            # 1. 기술적 지표 연산
            combined_df['MA60'] = combined_df['Close'].rolling(60).mean()   # 중기 수급선
            
            delta = combined_df['Close'].diff()
            up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
            ema_up, ema_down = up.ewm(com=13, adjust=False).mean(), down.ewm(com=13, adjust=False).mean()
            combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
            
            # 최근 5년치 데이터만 필터링 (초기 60일 MA 더미 제거)
            combined_df = combined_df.iloc[60:].copy()

            # 2. 거래 로직 (중기 스윙 트레이딩)
            # 매수: 60일선 위(상승세) AND RSI 45 미만(가벼운 눌림목)
            buy_signal = (combined_df['Close'] > combined_df['MA60']) & (combined_df['RSI'] < 45)
            # 매도: RSI 65 초과(단기 과열 익절) OR 60일선 하향 이탈(추세 깨짐 손절)
            sell_signal = (combined_df['RSI'] > 65) | (combined_df['Close'] < combined_df['MA60'])
            
            position = np.zeros(len(combined_df))
            current_pos = 0
            
            for i in range(len(combined_df)):
                if buy_signal.iloc[i]:
                    current_pos = 1 # 매수
                elif sell_signal.iloc[i]:
                    current_pos = 0 # 매도
                position[i] = current_pos
                
            combined_df['Target_Position'] = position
            combined_df['Position'] = combined_df['Target_Position'].shift(1).fillna(0)
            
            # 3. 수익률 및 수수료 차감 (왕복 0.3% 현실적용)
            combined_df['Daily_Return'] = combined_df['Close'].pct_change()
            combined_df['Turnover'] = np.abs(combined_df['Position'] - combined_df['Position'].shift(1).fillna(0))
            trading_cost = 0.0015 # 1회 거래당 수수료+세금 0.15% (매수+매도 왕복 0.3%)
            
            combined_df['Strategy_Return'] = (combined_df['Position'] * combined_df['Daily_Return']) - (combined_df['Turnover'] * trading_cost)
            
            combined_df['Cum_BuyHold'] = (1 + combined_df['Daily_Return']).cumprod() * 100
            combined_df['Cum_Strategy'] = (1 + combined_df['Strategy_Return']).cumprod() * 100

            # --- 결과 시각화 ---
            total_trades = combined_df['Turnover'].sum() / 2
            trend_status = "상승 추세" if combined_df['Close'].iloc[-1] > combined_df['MA60'].iloc[-1] else "하락/조정"
            
            st.markdown("---")
            st.markdown(f"## 📊 5년 시뮬레이션: 중기 스윙(Swing) 전략")
            st.caption(f"✔️ 진입: 60일선 위 & RSI 45 이하 | ✔️ 청산: RSI 65 돌파 또는 60일선 이탈 | ✔️ 1회 매매당 0.15% 제세금 차감")
            
            final_bh = combined_df['Cum_BuyHold'].iloc[-1] - 100
            final_st = combined_df['Cum_Strategy'].iloc[-1] - 100
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("5년 존버 수익률", f"{final_bh:+.1f} %")
            col2.metric("전략 수익률 (비용차감)", f"{final_st:+.1f} %", delta=f"{final_st - final_bh:.1f}%p (초과 수익)")
            col3.metric("5년간 총 매매 횟수", f"{int(total_trades)} 회")
            col4.metric("현재 기술적 추세", f"{trend_status}")

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_BuyHold'], name="단순 보유 (존버)", line=dict(color='gray', width=1.5)))
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_Strategy'], name="스윙 전략 수익률", line=dict(color='#00FF00', width=2.5)))
            
            fig.update_layout(template="plotly_dark", title=f"자산 성장 곡선 (초기 자본금 = 100 기준)", height=550)
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("데이터가 부족합니다. 최소 100일 이상 상장된 종목이어야 분석이 가능합니다.")
