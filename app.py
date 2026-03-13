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
st.caption("다중 팩터, 거래 비용, ATR 비중 조절, OOS 검증이 모두 적용된 실무형 백테스트 엔진")

# 2. 리스트 로드 (이전과 동일)
@st.cache_data(ttl=86400)
def get_all_stock_list():
    try:
        df_kr = fdr.StockListing('KRX')
        df_kr['Ticker'] = df_kr.apply(lambda r: f"{r['Code']}.KS" if r['Market']=='KOSPI' else f"{r['Code']}.KQ", axis=1)
        master_dict = dict(zip(df_kr['Name'], df_kr['Ticker']))
        df_ndaq = fdr.StockListing('NASDAQ')
        master_dict.update(dict(zip(df_ndaq['Name'] + " (NASDAQ)", df_ndaq['Symbol'])))
        custom_us = {"애플":"AAPL", "테슬라":"TSLA", "엔비디아":"NVDA", "마이크로소프트":"MSFT", "알파벳(구글)":"GOOGL", "인텔":"INTC", "AMD":"AMD", "SOXL":"SOXL", "TQQQ":"TQQQ"}
        master_dict.update(custom_us)
        return master_dict
    except:
        return {"삼성전자": "005930.KS"}

all_stocks_dict = get_all_stock_list()

# 3. 검색창
st.write("---")
search_mode = st.radio("검색 방식", ["📝 회사명 검색 (자동완성)", "⌨️ 티커 직접 입력"], horizontal=True)
search_name, final_ticker = None, None

if "이름" in search_mode:
    search_name = st.selectbox("분석할 종목을 입력하세요", options=list(all_stocks_dict.keys()), index=None)
    if search_name: final_ticker = all_stocks_dict.get(search_name)
else:
    search_name = st.text_input("티커를 입력하세요 (예: TQQQ, SOXL, 005930.KS)")
    if search_name: final_ticker = search_name.upper()

# 4. 퀀트 엔진 시작
if final_ticker:
    with st.spinner(f'[{search_name}] 전문가 수준의 퀀트 연산을 수행 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        market_index = "^KS11" if final_ticker.endswith(".KS") else "^KQ11" if final_ticker.endswith(".KQ") else "^IXIC"
        
        # High, Low, Volume 데이터까지 모두 로드
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_index, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty and len(stock_df) > 200:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            stock_df.index, market_df.index = stock_df.index.tz_localize(None), market_df.index.tz_localize(None)
            
            combined_df = stock_df.join(market_df['Close'].rename('Close_market'), how='inner').dropna()
            
            # --- [퀀트 고도화 1] 다중 팩터: RSI + 거래량 폭증 ---
            delta = combined_df['Close'].diff()
            up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
            ema_up, ema_down = up.ewm(com=13, adjust=False).mean(), down.ewm(com=13, adjust=False).mean()
            combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
            
            combined_df['Vol_MA20'] = combined_df['Volume'].rolling(20).mean()
            combined_df['Volume_Surge'] = combined_df['Volume'] > (combined_df['Vol_MA20'] * 1.5) # 거래량 1.5배 급증 필터
            
            # --- [퀀트 고도화 2] ATR 기반 리스크 변동성 계산 ---
            combined_df['H-L'] = combined_df['High'] - combined_df['Low']
            combined_df['H-C'] = np.abs(combined_df['High'] - combined_df['Close'].shift())
            combined_df['L-C'] = np.abs(combined_df['Low'] - combined_df['Close'].shift())
            combined_df['TR'] = combined_df[['H-L', 'H-C', 'L-C']].max(axis=1)
            combined_df['ATR'] = combined_df['TR'].rolling(14).mean()
            combined_df['ATR_pct'] = combined_df['ATR'] / combined_df['Close']
            
            # 포지션 사이즈: 1회 매매당 자산의 2%만 리스크로 노출 (최대 100%)
            combined_df['Target_Weight'] = np.clip(0.02 / combined_df['ATR_pct'], 0, 1).fillna(0)

            # --- [퀀트 고도화 3] 전진 분석 (Train / Test Split) ---
            split_idx = int(len(combined_df) * 0.7) # 70% 훈련, 30% 검증
            train_df = combined_df.iloc[:split_idx]
            test_df = combined_df.iloc[split_idx:]
            
            combined_df['Target_Return'] = combined_df['Close'].shift(-5) / combined_df['Close'] - 1
            combined_df['RSI_round'] = combined_df['RSI'].round()
            
            # 훈련 데이터에서만 승률 패턴을 학습 (미래 데이터 참조 금지)
            train_win_map = train_df.groupby('RSI_round')['Target_Return'].apply(lambda x: (x > 0).mean()).to_dict()
            combined_df['Hist_Win_Rate'] = combined_df['RSI_round'].map(train_win_map).fillna(0.5)
            
            combined_df['MA20_market'] = combined_df['Close_market'].rolling(20).mean()
            combined_df['Market_Score'] = np.clip((combined_df['Close_market'] / combined_df['MA20_market'] - 1) * 500, -20, 20)
            combined_df['Final_Score'] = np.clip(((combined_df['Hist_Win_Rate'] - 0.5) * 160) + combined_df['Market_Score'], -100, 100)

            # --- 매매 로직 & [퀀트 고도화 4] 거래 비용 차감 ---
            # 조건: 점수 30 이상 AND 거래량 폭증 시 -> ATR 기반 비중만큼 매수
            combined_df['Target_Position'] = np.where((combined_df['Final_Score'] > 30) & combined_df['Volume_Surge'], combined_df['Target_Weight'], 0)
            combined_df['Position'] = combined_df['Target_Position'].shift(1).fillna(0) # 다음날 시가/종가로 대응
            
            combined_df['Daily_Return'] = combined_df['Close'].pct_change()
            
            # 턴오버(회전율) 계산 및 비용 차감: 매매 회당 0.2% (수수료+세금+슬리피지)
            combined_df['Turnover'] = np.abs(combined_df['Position'] - combined_df['Position'].shift(1).fillna(0))
            trading_cost = 0.002 
            
            combined_df['Strategy_Return'] = (combined_df['Position'] * combined_df['Daily_Return']) - (combined_df['Turnover'] * trading_cost)
            
            combined_df['Cum_BuyHold'] = (1 + combined_df['Daily_Return']).cumprod() * 100
            combined_df['Cum_Strategy'] = (1 + combined_df['Strategy_Return']).cumprod() * 100

            # --- 결과 출력 ---
            st.markdown(f"## 📊 {search_name} 퀀트 시뮬레이션 결과")
            st.caption("✔️ 다중 팩터(거래량 필터) 적용 / ✔️ 매매 회당 0.2% 비용 차감 / ✔️ ATR 기반 리스크 통제")
            
            oos_start_date = test_df.index[0].strftime('%Y-%m-%d')
            
            final_bh = combined_df['Cum_BuyHold'].iloc[-1] - 100
            final_st = combined_df['Cum_Strategy'].iloc[-1] - 100
            
            col1, col2, col3 = st.columns(3)
            col1.metric("5년 누적 벤치마크 (존버)", f"{final_bh:+.1f} %")
            col2.metric("5년 누적 퀀트 전략", f"{final_st:+.1f} %", delta=f"{final_st - final_bh:.1f}%p (알파 수익)")
            
            # 테스트 구간 (Out-of-Sample) 승률 검증
            oos_df = combined_df.iloc[split_idx:]
            oos_strategy_return = (oos_df['Cum_Strategy'].iloc[-1] / oos_df['Cum_Strategy'].iloc[0] - 1) * 100
            col3.metric("최근 1.5년 (OOS 검증) 수익", f"{oos_strategy_return:+.1f} %")

            # 차트 (전진 분석 구분선 포함)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_BuyHold'], name="존버 전략 (비교군)", line=dict(color='gray', width=1.5)))
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_Strategy'], name="퀀트 전략 (실제 계좌)", line=dict(color='#00FF00', width=2.5)))
            
            # OOS (Out-of-Sample) 시작선 긋기
            fig.add_vline(x=test_df.index[0], line_width=2, line_dash="dash", line_color="red")
            fig.add_annotation(x=test_df.index[len(test_df)//2], y=150, text="미검증 데이터 테스트 구간 (Out-of-Sample)", showarrow=False, font=dict(color="red"))
            
            fig.update_layout(template="plotly_dark", title=f"자본 성장 곡선 (초기 자본 = 100) | {oos_start_date} 기준 데이터 분리", height=550)
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("데이터가 부족합니다. 최소 200일 이상 상장된 종목이어야 퀀트 분석이 가능합니다.")
