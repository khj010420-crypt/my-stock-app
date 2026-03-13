import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="Hysteresis Stock Intelligence", layout="wide")

# 2. 한국 종목 리스트 가져오기 (이름으로 검색하기 위함)
@st.cache_data
def get_krx_tickers():
    # 한국거래소 종목 리스트를 가져오는 URL (최적화된 방식)
    # 직접 CSV를 긁어오거나 상위 종목 위주로 구성 가능
    # 여기서는 범용성을 위해 시총 상위 및 주요 종목 매핑 테이블을 생성합니다.
    url = 'https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
    df = pd.read_html(url, header=0)[0]
    df = df[['회사명', '종목코드']]
    df['종목코드'] = df['종목코드'].apply(lambda x: f"{x:06d}")
    # 코스피/코스닥 구분을 위해 yfinance 형식으로 변환 (.KS)
    # 실제로는 KRX 전체를 뒤져야 하지만 검색 편의를 위해 매핑함
    return df

try:
    kr_stocks = get_krx_tickers()
    stock_dict = dict(zip(kr_stocks['회사명'], kr_stocks['종목코드']))
    stock_names = list(stock_dict.keys())
except:
    # 예외 발생 시 기본 리스트 사용
    stock_dict = {"삼성전자": "005930", "SK하이닉스": "000660", "현대차": "005380"}
    stock_names = list(stock_dict.keys())

# 3. 디자인 CSS
st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; }
    .stButton>button { height: 4em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏛️ Hysteresis 인텔리전스 분석 (이름 검색 지원)")

# 4. 상단 종목 자동 완성 검색창 (구글 검색 느낌)
st.subheader("🔍 분석할 종목명을 입력하세요")
selected_name = st.selectbox(
    "종목명을 입력하면 아래에 목록이 나타납니다.",
    options=stock_names,
    index=None,
    placeholder="예: 삼성전자, 현대차, 카카오...",
)

# 5. 시장 전광판 (시총 상위 주요 종목)
st.write("---")
st.subheader("🔥 주요 종목 실시간 보드")
top_stocks = ["삼성전자", "SK하이닉스", "현대차", "NAVER", "카카오", "LG에너지솔루션", "기아", "셀트리온"]

cols = st.columns(len(top_stocks))
clicked_ticker = ""

for i, name in enumerate(top_stocks):
    with cols[i]:
        if st.button(name):
            selected_name = name

# 6. 메인 분석 로직
if selected_name:
    # 이름에서 티커 추출 (한국 주식은 .KS 기준)
    raw_code = stock_dict.get(selected_name)
    search_ticker = f"{raw_code}.KS" if raw_code else None
    
    if search_ticker:
        with st.spinner(f'[{selected_name}] 데이터를 분석 중입니다...'):
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=365*5)
            
            # 데이터 수집
            stock_df = yf.download(search_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
            market_df = yf.download("^KS11", start=start_date, end=end_date, auto_adjust=True, progress=False)
            
            if not stock_df.empty:
                # 데이터 가공 (MultiIndex 제거)
                if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
                if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
                
                combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
                
                # 기술적 지표 계산
                delta = combined_df['Close_stock'].diff()
                up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
                ema_up = up.ewm(com=13, adjust=False).mean()
                ema_down = down.ewm(com=13, adjust=False).mean()
                combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
                
                combined_df['Target_Return'] = combined_df['Close_stock'].shift(-5) / combined_df['Close_stock'] - 1
                current_rsi = combined_df['RSI'].iloc[-1]
                
                # 5년치 유사 패턴 분석
                similar_patterns = combined_df[(combined_df['RSI'] >= current_rsi - 3) & (combined_df['RSI'] <= current_rsi + 3)].dropna()
                win_rate = (similar_patterns['Target_Return'] > 0).mean() if not similar_patterns.empty else 0.5
                stock_score = (win_rate - 0.5) * 160
                
                market_strength = (combined_df['Close_market'].iloc[-1] / combined_df['Close_market'].rolling(20).mean().iloc[-1] - 1) * 100
                final_score = np.clip(stock_score + (market_strength * 5), -100, 100)

                # 결과 요약
                st.markdown(f"## {selected_name} ({search_ticker})")
                col1, col2, col3 = st.columns(3)
                col1.metric("투자 점수", f"{final_score:.1f} pt")
                col2.metric("5년 데이터 승률", f"{win_rate*100:.1f} %")
                col3.metric("현재 RSI", f"{current_rsi:.1f}")

                # 차트
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Close_stock'], name=selected_name, line=dict(color='#ff4b4b')))
                fig.update_layout(template="plotly_dark", height=450)
                st.plotly_chart(fig, use_container_width=True)

                if final_score > 30: st.success("🚀 통계적으로 반등 가능성이 높은 구간입니다.")
                elif final_score < -30: st.error("📉 하락 위험이 큰 구간이니 주의가 필요합니다.")
                else: st.info("⚖️ 중립 구간입니다. 시장 흐름을 더 관찰하세요.")
            else:
                st.error("주가 데이터를 가져오는 데 실패했습니다.")
