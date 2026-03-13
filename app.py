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

# 2. 전 세계 리스트 로드 (7,200개 종목)
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

# 3. 데이터 로드: 시가총액 상위 전광판
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

# 5. 퀀트 엔진 및 백테스트 (계수 튜닝 완료)
if final_ticker:
    with st.spinner(f'[{search_name}] 퀀트 연산을 수행 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        market_index = "^KS11" if final_ticker.endswith(".KS") else "^KQ11" if final_ticker.endswith(".KQ") else "^IXIC"
        
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_index, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty and len(stock_df) > 200:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            stock_df.index, market_df.index = stock_df.index.tz_localize(None), market_df.index.tz_localize(None)
            
            combined_df = stock_df.join(market_df['Close'].rename('Close_market'), how='inner').dropna()
            
            delta = combined_df['Close'].diff()
            up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
            ema_up, ema_down = up.ewm(com=13, adjust=False).mean(), down.ewm(com=13, adjust=False).mean()
            combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
            
            # ATR (변동성) 계산
            combined_df['H-L'] = combined_df['High'] - combined_df['Low']
            combined_df['H-C'] = np.abs(combined_df['High'] - combined_df['Close'].shift())
            combined_df['L-C'] = np.abs(combined_df['Low'] - combined_df['Close'].shift())
            combined_df['TR'] = combined_df[['H-L', 'H-C', 'L-C']].max(axis=1)
            combined_df['ATR'] = combined_df['TR'].rolling(14).mean()
            combined_df['ATR_pct'] = combined_df['ATR'] / combined_df['Close']
            
            # 목표 비중 조절 (변동성이 심할수록 투자금 축소)
            combined_df['Target_Weight'] = np.clip(0.02 / combined_df['ATR_pct'], 0, 1).fillna(0)
            
            combined_df['Target_Return'] = combined_df['Close'].shift(-5) / combined_df['Close'] - 1
            combined_df['RSI_round'] = combined_df['RSI'].round()

            # Train / Test 분리
            split_idx = int(len(combined_df) * 0.7)
            train_df = combined_df.iloc[:split_idx]
            test_df = combined_df.iloc[split_idx:]
            
            train_win_map = train_df.groupby('RSI_round')['Target_Return'].apply(lambda x: (x > 0).mean()).to_dict()
            combined_df['Hist_Win_Rate'] = combined_df['RSI_round'].map(train_win_map).fillna(0.5)
            
            combined_df['MA20_market'] = combined_df['Close_market'].rolling(20).mean()
            combined_df['Market_Score'] = np.clip((combined_df['Close_market'] / combined_df['MA20_market'] - 1) * 500, -20, 20)
            combined_df['Final_Score'] = np.clip(((combined_df['Hist_Win_Rate'] - 0.5) * 160) + combined_df['Market_Score'], -100, 100)

            # [핵심 수정: 계수 완화] 점수가 0보다 크면 추세를 타고 보유 (단타 방지)
            combined_df['Target_Position'] = np.where(combined_df['Final_Score'] > 0, combined_df['Target_Weight'], 0)
            combined_df['Position'] = combined_df['Target_Position'].shift(1).fillna(0)
            
            combined_df['Daily_Return'] = combined_df['Close'].pct_change()
            combined_df['Turnover'] = np.abs(combined_df['Position'] - combined_df['Position'].shift(1).fillna(0))
            trading_cost = 0.002 # 매매 수수료 및 슬리피지 0.2%
            
            combined_df['Strategy_Return'] = (combined_df['Position'] * combined_df['Daily_Return']) - (combined_df['Turnover'] * trading_cost)
            
            combined_df['Cum_BuyHold'] = (1 + combined_df['Daily_Return']).cumprod() * 100
            combined_df['Cum_Strategy'] = (1 + combined_df['Strategy_Return']).cumprod() * 100

            st.markdown("---")
            st.markdown(f"## 📊 5년 시뮬레이션 (백테스트) 결과")
            st.caption("✔️ 매매수수료 0.2% 차감 / ✔️ 변동성 기반 비중조절 / ✔️ Out-Of-Sample 검증 (계수 최적화 완료)")
            
            oos_start_date = test_df.index[0].strftime('%Y-%m-%d')
            final_bh = combined_df['Cum_BuyHold'].iloc[-1] - 100
            final_st = combined_df['Cum_Strategy'].iloc[-1] - 100
            
            col1, col2, col3 = st.columns(3)
            col1.metric("5년 누적 벤치마크 (단순 존버)", f"{final_bh:+.1f} %")
            col2.metric("5년 누적 퀀트 전략 (비용차감)", f"{final_st:+.1f} %", delta=f"{final_st - final_bh:.1f}%p (초과 수익)")
            
            oos_df = combined_df.iloc[split_idx:]
            oos_strategy_return = (oos_df['Cum_Strategy'].iloc[-1] / oos_df['Cum_Strategy'].iloc[0] - 1) * 100
            col3.metric("최근 1.5년 (OOS 검증) 수익", f"{oos_strategy_return:+.1f} %")

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_BuyHold'], name="단순 보유 (존버)", line=dict(color='gray', width=1.5)))
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_Strategy'], name="퀀트 전략 수익률", line=dict(color='#00FF00', width=2.5)))
            fig.add_vline(x=test_df.index[0], line_width=2, line_dash="dash", line_color="red")
            fig.add_annotation(x=test_df.index[len(test_df)//2], y=150, text="미검증 데이터 테스트 구간 (Out-of-Sample)", showarrow=False, font=dict(color="red"))
            
            fig.update_layout(template="plotly_dark", title=f"자산 성장 곡선 (초기 자본금 = 100 기준) | {oos_start_date} 데이터 분리", height=550)
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("데이터가 부족합니다. 최소 200일 이상 상장된 종목이어야 퀀트 분석이 가능합니다.")
