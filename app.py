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

st.title("🏛️ Hysteresis 통합 주식 분석 및 백테스트 대시보드")

# 2. 전 세계 리스트 로드 (이전과 동일)
@st.cache_data(ttl=86400)
def get_all_stock_list():
    try:
        df_kr = fdr.StockListing('KRX')
        df_kr['Ticker'] = df_kr.apply(lambda r: f"{r['Code']}.KS" if r['Market']=='KOSPI' else f"{r['Code']}.KQ", axis=1)
        master_dict = dict(zip(df_kr['Name'], df_kr['Ticker']))
        
        df_ndaq = fdr.StockListing('NASDAQ')
        df_ndaq['Name_US'] = df_ndaq['Name'] + " (NASDAQ)"
        master_dict.update(dict(zip(df_ndaq['Name_US'], df_ndaq['Symbol'])))
        
        custom_us_names = {
            "애플": "AAPL", "테슬라": "TSLA", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
            "알파벳(구글)": "GOOGL", "아마존": "AMZN", "메타": "META", "넷플릭스": "NFLX",
            "인텔": "INTC", "AMD": "AMD", "TSMC": "TSM", "팔란티어": "PLTR", "아이온큐": "IONQ"
        }
        master_dict.update(custom_us_names)
        return master_dict
    except:
        return {"삼성전자": "005930.KS", "테슬라": "TSLA"}

all_stocks_dict = get_all_stock_list()

# 3. 데이터 로드: 시가총액 상위 (이전과 동일)
KOSPI_TOP = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "LG에너지솔루션": "373220.KS", "삼성바이오로직스": "207940.KS", "현대차": "005380.KS", "기아": "000270.KS", "셀트리온": "068270.KS", "POSCO홀딩스": "005490.KS", "NAVER": "035420.KS", "KB금융": "105560.KS"}
NASDAQ_TOP = {"애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "알파벳(구글)": "GOOGL", "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "넷플릭스": "NFLX", "코스트코": "COST"}

@st.cache_data(ttl=300)
def get_market_ranking(market_dict):
    data = []
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

# 5. 분석 및 백테스트 엔진
if final_ticker:
    with st.spinner(f'[{search_name}] 데이터를 수집하고 백테스트를 진행 중입니다...'):
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*5)
        
        market_index = "^KS11" if final_ticker.endswith(".KS") else "^KQ11" if final_ticker.endswith(".KQ") else "^IXIC"
        
        stock_df = yf.download(final_ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        market_df = yf.download(market_index, start=start_date, end=end_date, auto_adjust=True, progress=False)
        
        if not stock_df.empty and len(stock_df) > 100:
            if isinstance(stock_df.columns, pd.MultiIndex): stock_df.columns = stock_df.columns.get_level_values(0)
            if isinstance(market_df.columns, pd.MultiIndex): market_df.columns = market_df.columns.get_level_values(0)
            stock_df.index, market_df.index = stock_df.index.tz_localize(None), market_df.index.tz_localize(None)
            
            combined_df = pd.merge(stock_df[['Close']], market_df[['Close']], left_index=True, right_index=True, suffixes=('_stock', '_market'), how='inner')
            
            if not combined_df.empty:
                # 기본 지표 연산
                delta = combined_df['Close_stock'].diff()
                up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
                ema_up = up.ewm(com=13, adjust=False).mean()
                ema_down = down.ewm(com=13, adjust=False).mean()
                combined_df['RSI'] = 100 - (100 / (1 + (ema_up / ema_down)))
                
                combined_df['Daily_Return'] = combined_df['Close_stock'].pct_change()
                combined_df['Target_Return'] = combined_df['Close_stock'].shift(-5) / combined_df['Close_stock'] - 1
                
                # --- 현재 시점 점수 계산 ---
                current_rsi = combined_df['RSI'].iloc[-1]
                similar_patterns = combined_df[(combined_df['RSI'] >= current_rsi - 3) & (combined_df['RSI'] <= current_rsi + 3)].dropna()
                win_rate = (similar_patterns['Target_Return'] > 0).mean() if not similar_patterns.empty else 0.5
                stock_score = (win_rate - 0.5) * 160
                
                market_strength = (combined_df['Close_market'].iloc[-1] / combined_df['Close_market'].rolling(20).mean().iloc[-1] - 1) * 100
                final_score = np.clip(stock_score + (market_strength * 5), -100, 100)

                # --- 📈 백테스트 (과거 5년 시뮬레이션) ---
                # 과거 모든 날짜의 가상 점수 산출을 위해 RSI 반올림 그룹화
                combined_df['RSI_round'] = combined_df['RSI'].round()
                win_rate_map = combined_df.groupby('RSI_round')['Target_Return'].apply(lambda x: (x > 0).mean()).to_dict()
                
                combined_df['Hist_Win_Rate'] = combined_df['RSI_round'].map(win_rate_map).fillna(0.5)
                combined_df['Hist_Stock_Score'] = (combined_df['Hist_Win_Rate'] - 0.5) * 160
                combined_df['MA20_market'] = combined_df['Close_market'].rolling(20).mean()
                combined_df['Hist_Market_Score'] = np.clip((combined_df['Close_market'] / combined_df['MA20_market'] - 1) * 500, -20, 20)
                combined_df['Hist_Final_Score'] = np.clip(combined_df['Hist_Stock_Score'] + combined_df['Hist_Market_Score'], -100, 100)
                
                # 매매 로직: 전날 점수가 30점 이상이면 '보유(1)', 아니면 '현금(0)'
                combined_df['Position'] = np.where(combined_df['Hist_Final_Score'] > 30, 1, 0)
                combined_df['Position'] = combined_df['Position'].shift(1).fillna(0) # 오늘 수익률은 어제 내린 결정에 의함
                
                # 누적 수익률 계산 (시작 자산 = 100)
                combined_df['Strategy_Return'] = combined_df['Position'] * combined_df['Daily_Return']
                combined_df['Cum_BuyHold'] = (1 + combined_df['Daily_Return']).cumprod() * 100
                combined_df['Cum_Strategy'] = (1 + combined_df['Strategy_Return']).cumprod() * 100

                # --- 결과 출력 1: 현재 상태 리포트 ---
                st.markdown(f"## 🚀 {search_name} ({final_ticker}) 현재 분석 리포트")
                score_color = "#00FF00" if final_score > 30 else "#FF4B4B" if final_score < -30 else "#FFA500"
                
                col_res1, col_res2, col_res3 = st.columns(3)
                col_res1.metric("최종 투자 점수", f"{final_score:.1f} pt")
                col_res2.metric("유사구간 승률 (5년)", f"{win_rate*100:.1f} %")
                col_res3.metric("현재 RSI", f"{current_rsi:.1f}")

                # --- 결과 출력 2: 백테스트 시뮬레이션 ---
                st.markdown("---")
                st.markdown(f"## 📊 5년 시뮬레이션 (백테스트) 결과")
                st.caption("※ 룰: 매일 종가 기준 **점수가 30점 이상일 때만 주식을 보유**하고, 그 외에는 전량 매도하여 현금으로 관망했을 때의 수익률 비교")
                
                final_bh_return = combined_df['Cum_BuyHold'].iloc[-1] - 100
                final_st_return = combined_df['Cum_Strategy'].iloc[-1] - 100
                
                col_bt1, col_bt2 = st.columns(2)
                col_bt1.metric("단순 존버(Buy & Hold) 수익률", f"{final_bh_return:+.1f} %")
                col_bt2.metric("전략(Hysteresis) 적용 수익률", f"{final_st_return:+.1f} %", 
                               delta=f"{final_st_return - final_bh_return:.1f}%p 초과수익" if final_st_return > final_bh_return else f"{final_st_return - final_bh_return:.1f}%p 손실")

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_BuyHold'], name="단순 보유 (존버)", line=dict(color='gray', width=2)))
                fig.add_trace(go.Scatter(x=combined_df.index, y=combined_df['Cum_Strategy'], name="전략 수익률", line=dict(color='#00FF00', width=3)))
                fig.update_layout(template="plotly_dark", title="자산 성장 곡선 (초기 자본금 = 100 기준)", height=500, hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("종목과 시장 지수의 날짜를 매칭할 수 없습니다.")
        else:
            st.warning("데이터가 없거나 상장된 지 얼마 안 된 종목이라 통계 분석이 불가능합니다.")
