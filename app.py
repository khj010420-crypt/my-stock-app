import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 웹 페이지 제목 설정
st.set_page_config(page_title="나만의 주식 분석기", layout="wide")
st.title("5년 데이터 기반 주식 투자 점수 측정기")

# 사이드바 설정 (사용자 입력창)
with st.sidebar:
    st.header("설정")
    symbol = st.text_input("종목 티커 입력", value="005930.KS")
    market = st.selectbox("시장 지수 선택", ["^KS11 (코스피)", "^IXIC (나스닥)", "^GSPC (S&P500)"])
    market_ticker = market.split(" ")[0]

# 분석 버튼
if st.button("분석 시작"):
    with st.spinner('5년치 데이터를 분석 중입니다...'):
        # [데이터 수집 및 분석 로직 시작]
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        stock_df = yf.download(symbol, start=start_date, end=end_date, auto_adjust=True)
        market_df = yf.download(market_ticker, start=start_date, end=end_date, auto_adjust=True)
        
        if not stock_df.empty and not market_df.empty:
            # 데이터 통합 및 지표 계산 (앞서 만든 로직과 동일)
            combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
            
            # RSI 계산
            delta = combined_df['Close_stock'].diff()
            up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=13, adjust=False).mean()
            ema_down = down.ewm(com=13, adjust=False).mean()
            combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
            
            # 점수 계산
            combined_df['Target_Return'] = combined_df['Close_stock'].shift(-5) / combined_df['Close_stock'] - 1
            current_rsi = combined_df['RSI'].iloc[-1]
            similar_patterns = combined_df[(combined_df['RSI'] >= current_rsi - 3) & (combined_df['RSI'] <= current_rsi + 3)].dropna()
            
            win_rate = (similar_patterns['Target_Return'] > 0).mean() if not similar_patterns.empty else 0.5
            stock_score = (win_rate - 0.5) * 160
            
            combined_df['MA20_market'] = combined_df['Close_market'].rolling(window=20).mean()
            market_strength = (combined_df['Close_market'].iloc[-1] / combined_df['MA20_market'].iloc[-1] - 1) * 100
            market_score = np.clip(market_strength * 5, -20, 20)
            
            final_score = np.clip(stock_score + market_score, -100, 100)

            # 결과 화면 출력
            col1, col2 = st.columns(2)
            col1.metric("최종 투자 점수", f"{final_score:.1f} 점")
            col2.metric("과거 5년 유사패턴 승률", f"{win_rate*100:.1f} %")

            # 차트 그리기 (Plotly 사용 - 마우스 갖다대면 수치 나옴)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Close_stock'], name="주가"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("데이터를 가져오지 못했습니다. 티커를 확인하세요.")