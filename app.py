import streamlit as st
import pandas as pd
import json
import re
from datetime import datetime
from google import genai
from google.genai import types
from supabase import create_client

# ----------------------------------------------------
# 1. 초기 설정 및 시크릿 불러오기
# ----------------------------------------------------
st.set_page_config(page_title="AI 최신 뉴스 수집기", page_icon="📰", layout="wide")

# API 및 DB 연결
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# 클라이언트 초기화
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------------------------------
# [추가] 방문자 로깅 함수
# ----------------------------------------------------
def log_visitor():
    """앱 접속 시 방문 정보를 DB에 저장합니다."""
    if 'visited' not in st.session_state:
        try:
            # Streamlit 1.30+ 버전에서 헤더 정보를 가져오는 방식
            headers = st.context.headers
            user_agent = headers.get("User-Agent", "Unknown")
            # 프록시(Streamlit Cloud) 환경에서는 실제 IP를 가져오기 어려울 수 있습니다.
            remote_addr = headers.get("X-Forwarded-For", "Unknown")
            
            supabase.table("visitor_logs").insert({
                "user_agent": user_agent,
                "remote_addr": remote_addr
            }).execute()
            
            st.session_state['visited'] = True
        except Exception as e:
            print(f"방문 기록 저장 실패: {e}")

# 방문 기록 실행
log_visitor()

st.title("📰 AI 최신 뉴스 검색 & 자동 저장기")
st.markdown("키워드를 검색하면 Gemini가 구글 검색을 통해 가장 최신 뉴스 2건을 요약하고 DB에 자동 저장합니다.")

# ----------------------------------------------------
# 화면 탭 구성 (방문자 기록 탭 추가)
# ----------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["🔍 검색하기", "💾 저장된 뉴스 보기", "📊 통계 분석", "👣 방문자 기록"])

# ==========================================
# Tab 1: 검색 및 저장 로직 (기존과 동일)
# ==========================================
with tab1:
    st.subheader("새로운 뉴스 검색")
    
    with st.form("search_form"):
        keyword = st.text_input("검색할 키워드를 입력하세요 (예: 인공지능, 테슬라, 한국경제 등)")
        submitted = st.form_submit_button("검색 및 요약하기 🚀")
        
    if submitted and keyword:
        with st.spinner(f"'{keyword}'에 대한 최신 뉴스를 검색하고 분석 중입니다..."):
            try:
                prompt = f"""
                '{keyword}'에 대한 가장 최신 뉴스 딱 2건만 구글에서 검색해 줘.
                검색된 결과를 바탕으로 반드시 아래 JSON 배열 형식으로만 응답해. 백틱(```)이나 추가 설명 없이 JSON만 출력해.[
                    {{
                        "title": "기사 제목",
                        "source": "언론사 이름",
                        "news_date": "기사 발행일 (예: 2023-10-25)",
                        "url": "기사 원본 URL",
                        "summary": "기사 내용 3줄 요약"
                    }}
                ]
                절대 URL을 지어내지(환각) 마.
                """
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        tools=[{"google_search": {}}]
                    )
                )
                
                response_text = response.text
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                
                if json_match:
                    news_data = json.loads(json_match.group())
                    
                    real_links = {}
                    if hasattr(response, 'candidates') and response.candidates:
                        grounding_metadata = response.candidates[0].grounding_metadata
                        if grounding_metadata and grounding_metadata.grounding_chunks:
                            for chunk in grounding_metadata.grounding_chunks:
                                if hasattr(chunk, 'web') and chunk.web:
                                    real_links[chunk.web.title] = chunk.web.uri
                    
                    for item in news_data:
                        for real_title, real_url in real_links.items():
                            if item['title'].lower() in real_title.lower() or real_title.lower() in item['title'].lower():
                                if real_url.startswith("http") and "grounding-api-redirect" not in real_url:
                                    item['url'] = real_url
                                break
                    
                    saved_count = 0
                    skipped_count = 0
                    st.success("✨ 검색이 완료되었습니다!")
                    
                    for idx, item in enumerate(news_data):
                        with st.container():
                            st.markdown(f"### {idx+1}. [{item['title']}]({item['url']})")
                            st.caption(f"출처: {item['source']} | 날짜: {item['news_date']}")
                            st.write(f"**요약:** {item['summary']}")
                            st.divider()
                        
                        try:
                            db_data = {
                                "keyword": keyword, "title": item['title'], "source": item['source'],
                                "news_date": item['news_date'], "url": item['url'], "summary": item['summary']
                            }
                            supabase.table("news_history").insert(db_data).execute()
                            saved_count += 1
                        except Exception as e:
                            if '23505' in str(e) or 'duplicate key' in str(e).lower():
                                skipped_count += 1
                            else:
                                st.error(f"DB 저장 중 오류 발생: {e}")
                    st.toast(f"✅ 새 뉴스 {saved_count}건 저장완료!", icon="🎉")
                else:
                    st.error("데이터를 파싱하는 데 실패했습니다.")
            except Exception as e:
                st.error(f"오류가 발생했습니다: {str(e)}")

# ==========================================
# Tab 2: 저장된 뉴스 보기 (기존과 동일)
# ==========================================
with tab2:
    st.subheader("💾 DB에 저장된 뉴스 히스토리")
    news_res = supabase.table("news_history").select("*").order("created_at", desc=True).execute()
    news_data_list = news_res.data
    
    if news_data_list:
        df = pd.DataFrame(news_data_list)
        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        filter_text = st.text_input("🔍 제목 또는 키워드로 검색")
        if filter_text:
            df = df[df['title'].str.contains(filter_text, case=False, na=False) | 
                    df['keyword'].str.contains(filter_text, case=False, na=False)]
        
        st.dataframe(df[['keyword', 'title', 'source', 'news_date', 'url', 'created_at']], use_container_width=True, hide_index=True)
    else:
        st.info("저장된 뉴스가 없습니다.")

# ==========================================
# Tab 3: 통계 대시보드 (기존과 동일)
# ==========================================
with tab3:
    st.subheader("📊 뉴스 수집 통계")
    if news_data_list:
        stat_df = pd.DataFrame(news_data_list)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 📌 키워드별 누적 수집 건수")
            st.bar_chart(stat_df['keyword'].value_counts())
        with col2:
            st.markdown("##### 📅 일자별 뉴스 저장 건수")
            stat_df['date_only'] = pd.to_datetime(stat_df['created_at']).dt.strftime('%Y-%m-%d')
            st.line_chart(stat_df['date_only'].value_counts().sort_index())
    else:
        st.info("데이터가 부족합니다.")

# ==========================================
# [추가] Tab 4: 방문자 기록 보기
# ==========================================
with tab4:
    st.subheader("👣 실시간 방문자 접속 로그")
    
    # DB에서 방문 기록 가져오기
    v_response = supabase.table("visitor_logs").select("*").order("created_at", desc=True).limit(100).execute()
    v_data = v_response.data
    
    if v_data:
        v_df = pd.DataFrame(v_data)
        
        # 가독성을 위한 전처리
        v_df['created_at'] = pd.to_datetime(v_df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # 주요 지표 출력
        total_visits = len(v_df)
        unique_ips = v_df['remote_addr'].nunique()
        
        m1, m2 = st.columns(2)
        m1.metric("총 페이지뷰(최근 100건 중)", f"{total_visits}회")
        m2.metric("고유 접속 IP 수", f"{unique_ips}개")
        
        st.markdown("---")
        st.dataframe(
            v_df[['created_at', 'remote_addr', 'user_agent']],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("아직 방문 기록이 없습니다.")