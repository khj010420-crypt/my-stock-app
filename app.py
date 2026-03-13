import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="Hysteresis Stock Intelligence", layout="wide")

# 2. 데이터 로드: 한국 종목 리스트 (이름 검색용)
@st.cache_data
def get_kr_stock_list():
    url = 'https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
    try:
        df = pd.read_html(url, header=0)[0]
        df = df[['회사명', '종목코드']]
        df['종목코드'] = df['종목코드'].apply(lambda x: f"{x:06d}.KS") # 코스피 기준
        return df
    except:
        return pd.DataFrame({"회사명": ["삼성전자", "SK하이닉스"], "종목코드": ["005930.KS", "000660.KS"]})

kr_stocks = get_kr_stock_list()
stock_dict = dict(zip(kr_stocks['회사명'], kr_stocks['종목코드']))

# 3. 디자인 및 스타일
st.markdown("""
    <style>
    .stButton>button { width: 100%; height: 4.5em; border-radius: 8px; font-weight: bold; margin-bottom: 5px; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #31333f; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏛️ Hysteresis 통합 분석 대시보드")

# 4. 섹션 1: 주요 종목 실시간 전광판 (기존 기능 부활)
st.subheader("🔥 시장 핫 종목 (클릭 시 즉시 분석)")
# 주요 종목 리스트 (티커와 이름 매핑)
top_display = {
    "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "현대차": "005380.KS", 
    "NAVER": "035420.KS", "테슬라": "TSLA", "엔비디아": "NVDA", "애플": "AAPL", "비트코인": "BTC-USD"
}

cols = st.columns(len(top_display))
selected_ticker = None
selected_display_name = ""

for i, (name, ticker) in enumerate(top_display.items()):
    with cols[i]:
        if st.button(f"{name}\n{ticker}"):
            selected_ticker = ticker
            selected_display_name = name

st.write("---")

# 5. 섹션 2: 정밀 이름 검색 (구글 스타일 자동 완성)
col_search, _ = st.columns([1, 1])
with col_search:
    search_name = st.selectbox(
        "🔍 검색창: 종목명 또는 티커를 입력하세요",
        options=list(stock_dict.keys()) + list(top_display.keys()),
        index=None,
        placeholder="삼성전자, TSLA 등을 입력..."
    )

# 우선순위 결정: 클릭한 종목이 있으면 클릭 종목을, 아니면 검색창 종목을 사용
if selected_ticker:
    final_ticker = selected_ticker
    final_name = selected_display_name
elif search_name:
    final_ticker = stock_dict.get(search_name) if search_name in stock_dict else top_display.get(search_name)
    final_name = search_name
else:
    final_ticker = None

# 6. 섹션 3: 분석 엔진 실행
if final_ticker:
    with st.spinner(f'[{final_name}] 5년치 데이터를 분석 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        # 지수 선택 (미국/한국 자동 판단)
        market_index = "^IXIC" if not final_ticker.endswith(".KS") and not final_ticker.endswith(".KQ") else "^KS11"
        
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_index, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty:
            # MultiIndex 처리
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            
            combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
            
            # 지표 계산 로직 (RSI, 점수 등)
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
            market_strength = (combined_df['Close_market'].iloc[-1] / combined_df['Close_market'].rolling(20).mean().iloc[-1] - 1) * 100
            final_score = np.clip(stock_score + (market_strength * 5), -100, 100)

            # 결과 리포트
            st.markdown(f"## 🚀 {final_name} ({final_ticker}) 분석 결과")
            score_color = "#00FF00" if final_score > 30 else "#FF4B4B" if final_score < -30 else "#FFA500"
            
            col_res1, col_res2, col_res3 = st.columns(3)
            col_res1.metric("최종 점수", f"{final_score:.1f} pt")
            col_res2.metric("5년 승률(유사구간)", f"{win_rate*100:.1f} %")
            col_res3.metric("RSI 지표", f"{current_rsi:.1f}")

            # 차트 시각화
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Close_stock'], name="Price", line=dict(color=score_color)))
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # 하단 가이드
            if final_score > 50: st.success(f"현재 {final_name}은(는) 매수 우위 구간입니다.")
            elif final_score < -50: st.error(f"현재 {final_name}은(는) 매도 압력이 강한 구간입니다.")
            else: st.info(f"{final_name}은(는) 현재 중립적인 흐름을 보이고 있습니다.")
        else:
            st.error("데이터를 로드할 수 없습니다. 티커를 확인하세요.")
