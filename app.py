import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정 및 디자인
st.set_page_config(page_title="Hysteresis Stock Intelligence", layout="wide")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; color: white; }
    .stButton>button:hover { background-color: #ff4b4b; border: 1px solid #ff4b4b; }
    .status-box { padding: 20px; border-radius: 10px; margin: 10px 0; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏛️ 시장 종합 전광판 및 인텔리전스 분석")

# 2. 시장별 상위 종목 리스트 정의 (시총 상위 주요 종목)
market_data = {
    "KOSPI (한국)": {
        "index": "^KS11",
        "tickers": ["005930.KS", "000660.KS", "373220.KS", "207940.KS", "005380.KS", "005490.KS", "068270.KS", "035420.KS"]
    },
    "NASDAQ (미국)": {
        "index": "^IXIC",
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "AVGO"]
    }
}

# 3. 상단 시장 선택 및 실시간 시세판
selected_market = st.radio("시장을 선택하세요", list(market_data.keys()), horizontal=True)
market_info = market_data[selected_market]

st.subheader(f"📍 {selected_market} 주요 종목 시세")

# 종목 리스트 데이터 가져오기 (간단한 시세표)
@st.cache_data(ttl=600) # 10분간 데이터 캐싱
def get_market_summary(tickers):
    summary = []
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            info = stock.fast_info
            price = info['last_price']
            change = ((price - info['previous_close']) / info['previous_close']) * 100
            summary.append({"종목명": t, "현재가": round(price, 2), "등락율": round(change, 2)})
        except:
            continue
    return pd.DataFrame(summary)

summary_df = get_market_summary(market_info["tickers"])

# 4. 증권사 스타일의 종목 리스트 출력 (클릭 기능 포함)
cols = st.columns(len(summary_df))
selected_ticker = ""

for i, row in summary_df.iterrows():
    with cols[i]:
        color = "#ff4b4b" if row['등락율'] > 0 else "#31333f" if row['등락율'] == 0 else "#1c83e1"
        if st.button(f"{row['종목명']}\n{row['현재가']}\n({row['등락율']}%)"):
            selected_ticker = row['종목명']

st.write("---")

# 5. 검색창 (직접 입력도 가능)
search_ticker = st.text_input("🔍 직접 종목 검색 (티커 입력 후 엔터)", value=selected_ticker if selected_ticker else "005930.KS")

# 6. 분석 엔진 (앞선 로직 통합)
if search_ticker:
    with st.spinner(f'{search_ticker} 데이터를 정밀 분석 중...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        stock_df = yf.download(search_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_info["index"], start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            
            combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
            
            # 지표 연산
            delta = combined_df['Close_stock'].diff()
            up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=13, adjust=False).mean()
            ema_down = down.ewm(com=13, adjust=False).mean()
            combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
            
            combined_df['Target_Return'] = combined_df['Close_stock'].shift(-5) / combined_df['Close_stock'] - 1
            current_rsi = combined_df['RSI'].iloc[-1]
            similar_patterns = combined_df[(combined_df['RSI'] >= current_rsi - 3) & (combined_df['RSI'] <= current_rsi + 3)].dropna()
            
            win_rate = (similar_patterns['Target_Return'] > 0).mean() if not similar_patterns.empty else 0.5
            stock_score = (win_rate - 0.5) * 160
            
            combined_df['MA20_market'] = combined_df['Close_market'].rolling(window=20).mean()
            market_strength = (combined_df['Close_market'].iloc[-1] / combined_df['MA20_market'].iloc[-1] - 1) * 100
            final_score = np.clip(stock_score + (np.clip(market_strength * 5, -20, 20)), -100, 100)

            # 결과 리포트 디자인
            score_color = "green" if final_score > 30 else "red" if final_score < -30 else "orange"
            st.markdown(f"### 🚀 {search_ticker} 투자 매력도: <span style='color:{score_color}'>{final_score:.1f} pt</span>", unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("통계적 승률(5y)", f"{win_rate*100:.1f}%")
            col2.metric("현재 RSI", f"{current_rsi:.1f}")
            col3.metric("시장 강도(KOSPI/NAS)", f"{market_strength:.1f}%")

            # 차트
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Close_stock'], name="Price", line=dict(color='#ff4b4b')))
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            # 분석 요약
            if final_score > 50: st.success("✅ 강력 매수 신호: 통계적으로 매우 유리한 위치입니다.")
            elif final_score < -50: st.error("⚠️ 매도 주의 신호: 하락 압력이 강하며 시장 상황이 좋지 않습니다.")
            else: st.info("⚖️ 중립 신호: 추세 확인이 필요한 구간입니다.")
