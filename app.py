import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. 페이지 설정 및 CSS
st.set_page_config(page_title="Hysteresis Stock Intelligence", layout="wide")
st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #31333f; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏛️ Hysteresis 통합 주식 분석 대시보드")
st.caption("과거 5년치 빅데이터 기반 유사 구간 승률 및 시장 강도 분석 시스템")

# 2. 데이터 로드: 한국 종목 리스트 (이름 검색용, 출처: 한국거래소)
@st.cache_data(ttl=86400)
def get_kr_stock_list():
    url = 'https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
    try:
        df = pd.read_html(url, header=0)[0]
        df = df[['회사명', '종목코드']]
        df['종목코드'] = df['종목코드'].apply(lambda x: f"{x:06d}.KS")
        return dict(zip(df['회사명'], df['종목코드']))
    except:
        return {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "현대차": "005380.KS"}

kr_stocks_dict = get_kr_stock_list()

# 3. 데이터 로드: 시가총액 상위 리스트 실시간 갱신
KOSPI_TOP = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "LG에너지솔루션": "373220.KS", "삼성바이오로직스": "207940.KS", "현대차": "005380.KS", "기아": "000270.KS", "셀트리온": "068270.KS", "POSCO홀딩스": "005490.KS", "NAVER": "035420.KS", "KB금융": "105560.KS"}
NASDAQ_TOP = {"애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "알파벳(구글)": "GOOGL", "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "넷플릭스": "NFLX", "코스트코": "COST"}

@st.cache_data(ttl=300) # 5분마다 갱신
def get_market_ranking(market_dict):
    tickers = list(market_dict.values())
    hist = yf.download(tickers, period="5d", auto_adjust=True, progress=False)
    
    # MultiIndex 처리
    close_prices = hist['Close'] if isinstance(hist.columns, pd.MultiIndex) else hist
    
    data = []
    for name, ticker in market_dict.items():
        try:
            prices = close_prices[ticker].dropna()
            if len(prices) >= 2:
                current = float(prices.iloc[-1])
                prev = float(prices.iloc[-2])
                change_pct = ((current - prev) / prev) * 100
                data.append({
                    "종목명": name, "티커": ticker, 
                    "현재가": f"{current:,.2f}", "등락률(%)": round(change_pct, 2)
                })
        except:
            continue
    df = pd.DataFrame(data)
    # 등락률 기준으로 색상을 주기 위해 스타일 적용
    return df

# --- UI 섹션 1: 시가총액 상위 전광판 ---
st.subheader("🏆 시가총액 상위 TOP 10 실시간 시세")
tab1, tab2 = st.tabs(["🇰🇷 KOSPI 상위 10", "🇺🇸 NASDAQ 상위 10"])

with tab1:
    st.dataframe(get_market_ranking(KOSPI_TOP).style.format({"등락률(%)": "{:+.2f}%"}), use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(get_market_ranking(NASDAQ_TOP).style.format({"등락률(%)": "{:+.2f}%"}), use_container_width=True, hide_index=True)

st.write("---")

# --- UI 섹션 2: 자동 완성 검색창 ---
st.subheader("🔍 정밀 분석 검색창")
search_options = list(kr_stocks_dict.keys()) + list(NASDAQ_TOP.keys()) + list(NASDAQ_TOP.values())
search_name = st.selectbox(
    "분석할 종목명 또는 티커를 입력하세요 (예: 삼성전자, TSLA)",
    options=search_options,
    index=None,
    placeholder="종목명을 치면 자동완성 됩니다..."
)

# --- 분석 엔진 ---
if search_name:
    # 검색어로부터 티커 추출
    if search_name in kr_stocks_dict:
        final_ticker = kr_stocks_dict[search_name]
    elif search_name in NASDAQ_TOP:
        final_ticker = NASDAQ_TOP[search_name]
    else:
        final_ticker = search_name # 티커를 직접 입력한 경우
        
    with st.spinner(f'[{search_name}] 5년치 데이터를 수집 및 분석 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        market_index = "^KS11" if final_ticker.endswith(".KS") or final_ticker.endswith(".KQ") else "^IXIC"
        
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_index, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty and not market_df.empty:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            
            combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
            
            # 수치 연산 (RSI 및 승률)
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

            # --- 분석 결과 출력 ---
            st.markdown(f"## 🚀 {search_name} ({final_ticker}) 분석 리포트")
            score_color = "#00FF00" if final_score > 30 else "#FF4B4B" if final_score < -30 else "#FFA500"
            
            col_res1, col_res2, col_res3 = st.columns(3)
            col_res1.metric("최종 투자 점수", f"{final_score:.1f} pt")
            col_res2.metric("유사구간 승률 (5년)", f"{win_rate*100:.1f} %")
            col_res3.metric("현재 RSI", f"{current_rsi:.1f}")

            # Plotly 차트
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Close_stock'], name="Price", line=dict(color=score_color)))
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            if final_score > 30: st.success("✅ **통계적 매수 우위:** 5년 데이터 기준, 현재와 유사한 지표에서 주가가 상승한 확률이 높습니다.")
            elif final_score < -30: st.error("⚠️ **통계적 하락 주의:** 과거 패턴상 현재 위치는 단기 하락 위험이 큽니다.")
            else: st.info("⚖️ **중립/관망:** 뚜렷한 통계적 방향성이 나타나지 않습니다.")
        else:
            st.error("데이터 로드 실패: 티커를 확인하시거나 일시적인 네트워크 오류일 수 있습니다.")

# --- 데이터 출처 표기 ---
st.write("---")
st.caption("ℹ️ **데이터 출처:** 시세 데이터는 [Yahoo Finance API](https://finance.yahoo.com/)를 사용하며, 종목 코드는 [한국거래소(KRX) 기업공시채널 KIND](https://kind.krx.co.kr/)의 공개 데이터를 참조합니다.")
