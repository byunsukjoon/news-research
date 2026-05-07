import streamlit as st
from supabase import create_client, Client
import google.generativeai as genai
import feedparser
from datetime import datetime

# --- 1. 환경 설정 및 클라이언트 초기화 ---
# Streamlit Secrets에 저장된 정보를 불러옵니다.
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError as e:
    st.error(f"Secrets 설정이 누락되었습니다: {e}")
    st.stop()

# 클라이언트 생성
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# --- 2. UI 레이아웃 ---
st.set_page_config(page_title="AI 뉴스 매니저", layout="wide")
st.title("🤖 AI 최신 뉴스 검색 & 자동 저장기")

st.sidebar.header("🔍 검색 설정")
keyword = st.sidebar.text_input("검색 키워드", "인공지능 보안")
news_count = st.sidebar.slider("가져올 뉴스 개수", 1, 10, 5)

# --- 3. 주요 기능 함수 ---

def fetch_and_summarize(search_term):
    """Google 뉴스 RSS를 검색하고 Gemini로 요약합니다."""
    rss_url = f"https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)
    
    if not feed.entries:
        st.warning("검색 결과가 없습니다.")
        return

    st.subheader(f"'{search_term}' 관련 최신 뉴스")
    
    for entry in feed.entries[:news_count]:
        with st.container():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"#### [{entry.title}]({entry.link})")
                st.caption(f"출처: {entry.get('source', {}).get('title', '알 수 없음')} | 게시일: {entry.published}")
            
            # Gemini 요약 생성
            try:
                prompt = f"뉴스 제목 '{entry.title}'을 바탕으로 이 뉴스의 핵심 내용을 한 문장으로 한국어로 요약해줘."
                response = model.generate_content(prompt)
                summary_text = response.text
            except Exception:
                summary_text = "요약을 생성할 수 없습니다."
            
            st.info(f"✨ AI 요약: {summary_text}")
            
            with col2:
                # DB 저장 버튼 (중복 저장 방지를 위해 URL을 키로 사용)
                if st.button("DB에 저장", key=entry.link):
                    data = {
                        "keyword": search_term,
                        "title": entry.title,
                        "source": entry.get('source', {}).get('title', '알 수 없음'),
                        "news_date": entry.published,
                        "url": entry.link,
                        "summary": summary_text
                    }
                    
                    try:
                        # Supabase news_history 테이블에 데이터 삽입
                        res = supabase.table("news_history").insert(data).execute()
                        st.success("저장 완료!")
                    except Exception as e:
                        if "duplicate key" in str(e):
                            st.warning("이미 저장된 뉴스입니다.")
                        else:
                            st.error(f"저장 실패: {e}")
            st.divider()

def show_history():
    """Supabase news_history 테이블에서 데이터를 가져와 보여줍니다."""
    st.subheader("📁 저장된 뉴스 히스토리 (Supabase)")
    
    try:
        # 에러가 났던 부분: 테이블 이름을 news_history로 정확히 지정
        response = supabase.table("news_history") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()
        
        if response.data:
            for item in response.data:
                with st.expander(f"{item['title']} ({item['keyword']})"):
                    st.write(f"**출처:** {item['source']}")
                    st.write(f"**날짜:** {item['news_date']}")
                    st.write(f"**요약:** {item['summary']}")
                    st.write(f"[뉴스 바로가기]({item['url']})")
                    st.caption(f"저장 일시: {item['created_at']}")
        else:
            st.write("저장된 데이터가 없습니다.")
    except Exception as e:
        st.error(f"데이터를 불러오는 중 에러 발생: {e}")

# --- 4. 메인 탭 구성 ---
tab1, tab2 = st.tabs(["🔎 뉴스 검색 및 요약", "📜 저장된 기록 보기"])

with tab1:
    if st.button("뉴스 검색 시작"):
        fetch_and_summarize(keyword)

with tab2:
    if st.button("데이터 새로고침"):
        st.rerun()
    show_history()