import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import FinanceDataReader as fdr

# 1. 페이지 설정
st.set_page_config(page_title="Hysteresis Stock Intelligence", layout="wide")
st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #31333f; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏛️ Hysteresis 통합 주식 분석 대시보드")

# 2. 전 세계 모든 주식 리스트 통합 로드 (KRX + NASDAQ + S&P500)
@st.cache_data(ttl=86400)
def get_all_stock_list():
    try:
        # 1. 한국 주식 (코스피, 코스닥)
        df_kr = fdr.StockListing('KRX')
        df_kr['Ticker'] = df_kr.apply(lambda r: f"{r['Code']}.KS" if r['Market']=='KOSPI' else f"{r['Code']}.KQ", axis=1)
        master_dict = dict(zip(df_kr['Name'], df_kr['Ticker']))
        
        # 2. 미국 주식 (나스닥 전 종목)
        df_ndaq = fdr.StockListing('NASDAQ')
        # 미국 주식은 회사명이 영어이므로 헷갈리지 않게 뒤에 (US)를 붙임
        df_ndaq['Name_US'] = df_ndaq['Name'] + " (NASDAQ)"
        master_dict.update(dict(zip(df_ndaq['Name_US'], df_ndaq['Symbol'])))
        
        # 3. 미국 주식 (S&P 500 전 종목 - 뉴욕거래소 포함)
        df_sp = fdr.StockListing('S&P500')
        df_sp['Name_US'] = df_sp['Name'] + " (S&P500)"
        master_dict.update(dict(zip(df_sp['Name_US'], df_sp['Symbol'])))

        # 4. 편의를 위한 미국 대표 주식 '한글 이름' 수동 추가
        custom_us_names = {
            "애플": "AAPL", "테슬라": "TSLA", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
            "알파벳(구글)": "GOOGL", "아마존": "AMZN", "메타": "META", "넷플릭스": "NFLX",
            "스타벅스": "SBUX", "코카콜라": "KO", "인텔": "INTC", "AMD": "AMD",
            "TSMC": "TSM", "팔란티어": "PLTR", "아이온큐": "IONQ"
        }
        master_dict.update(custom_us_names)
        
        return master_dict
    except Exception as e:
        return {"삼성전자": "005930.KS", "테슬라": "TSLA"} # 실패 시 기본값

all_stocks_dict = get_all_stock_list()

# 3. 데이터 로드: 시가총액 상위 (멀티인덱스 에러 원천 차단 방식 적용)
KOSPI_TOP = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "LG에너지솔루션": "373220.KS", "삼성바이오로직스": "207940.KS", "현대차": "005380.KS", "기아": "000270.KS", "셀트리온": "068270.KS", "POSCO홀딩스": "005490.KS", "NAVER": "035420.KS", "KB금융": "105560.KS"}
NASDAQ_TOP = {"애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "알파벳(구글)": "GOOGL", "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "넷플릭스": "NFLX", "코스트코": "COST"}

@st.cache_data(ttl=300)
def get_market_ranking(market_dict):
    data = []
    # yfinance 일괄 다운로드 에러를 피하기 위해 개별 다운로드 처리 (훨씬 안정적임)
    for name, ticker in market_dict.items():
        try:
            hist = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
            if not hist.empty and len(hist) >= 2:
                current = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                change_pct = ((current - prev) / prev) * 100
                data.append({"종목명": name, "티커": ticker, "현재가": f"{current:,.2f}", "등락률(%)": round(change_pct, 2)})
        except:
            continue
    return pd.DataFrame(data)

# --- UI 섹션 1: 시가총액 상위 전광판 ---
st.subheader("🏆 시가총액 상위 TOP 10 실시간 시세")
tab1, tab2 = st.tabs(["🇰🇷 KOSPI 상위 10", "🇺🇸 NASDAQ 상위 10"])

with tab1:
    st.dataframe(get_market_ranking(KOSPI_TOP).style.format({"등락률(%)": "{:+.2f}%"}), use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(get_market_ranking(NASDAQ_TOP).style.format({"등락률(%)": "{:+.2f}%"}), use_container_width=True, hide_index=True)

st.write("---")

# --- UI 섹션 2: 만능 통합 검색창 ---
st.subheader("🔍 정밀 분석 검색창")
search_mode = st.radio("검색 방식 선택", ["📝 회사 이름으로 검색 (한국 전 종목 + 미국 전 종목 지원)", "⌨️ 티커(Ticker) 직접 입력"], horizontal=True)

search_name = None
final_ticker = None

if "이름" in search_mode:
    search_name = st.selectbox(
        "한국 주식은 한글로, 미국 주식은 영어(예: Intel)로 검색해보세요. (유명 미국 주식은 한글 지원)", 
        options=list(all_stocks_dict.keys()), 
        index=None, 
        placeholder="검색어를 입력하세요..."
    )
    if search_name:
        final_ticker = all_stocks_dict.get(search_name)
else:
    search_name = st.text_input("분석할 티커를 입력하세요 (예: SOXL, TQQQ, 035720.KS)")
    if search_name:
        final_ticker = search_name.upper()

# --- 분석 엔진 ---
if final_ticker:
    with st.spinner(f'[{search_name}] 데이터를 수집 및 분석 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        # 지수 판별 (한국은 코스피/코스닥, 미국은 나스닥 기준)
        if final_ticker.endswith(".KS"): market_index = "^KS11"
        elif final_ticker.endswith(".KQ"): market_index = "^KQ11"
        else: market_index = "^IXIC"
        
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_index, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty and len(stock_df) > 50:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            stock_df.index = stock_df.index.tz_localize(None)
            market_df.index = market_df.index.tz_localize(None)
            
            combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
            
            if not combined_df.empty:
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

                # --- 결과 출력 ---
                st.markdown(f"## 🚀 {search_name} ({final_ticker}) 리포트")
                score_color = "#00FF00" if final_score > 30 else "#FF4B4B" if final_score < -30 else "#FFA500"
                
                col_res1, col_res2, col_res3 = st.columns(3)
                col_res1.metric("최종 투자 점수", f"{final_score:.1f} pt")
                col_res2.metric("유사구간 승률 (5년)", f"{win_rate*100:.1f} %")
                col_res3.metric("현재 RSI", f"{current_rsi:.1f}")

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Close_stock'], name="Price", line=dict(color=score_color)))
                fig.update_layout(template="plotly_dark", height=450, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("종목과 시장 지수의 날짜를 매칭할 수 없습니다.")
        else:
            st.warning("데이터가 없거나 상장된 지 얼마 안 된 종목이라 통계 분석이 불가능합니다.")
