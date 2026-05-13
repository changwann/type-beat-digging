import streamlit as st
import requests
import time
import pandas as pd

API_URL = "http://localhost:8000"

st.title("Type Beat Digging Program v2")
st.write("서버 연동형: FastAPI 백엔드를 통해 사운드 질감을 분석합니다.")

# 변수들이 초기화되지 않도록 세션에 저장해 둡니다.
if 'is_indexing' not in st.session_state:
    st.session_state.is_indexing = False
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'show_top_10' not in st.session_state:
    st.session_state.show_top_10 = False
if 'analyzing_url' not in st.session_state:
    st.session_state.analyzing_url = None

with st.sidebar:
    st.header("1. 유튜브 비트 인덱싱")
    youtube_url = st.text_input("유튜브 플레이리스트/영상 URL")
    
    if not st.session_state.is_indexing:
        if st.button("데이터베이스에 추가"):
            res = requests.post(f"{API_URL}/index", json={"url": youtube_url})
            if res.status_code == 200:
                st.session_state.is_indexing = True
                st.rerun() 
    
    if st.session_state.is_indexing:
        st.warning("데이터베이스 인덱싱이 진행 중입니다...")
        if st.button("작업 취소 🛑"):
            requests.post(f"{API_URL}/cancel")
            st.session_state.is_indexing = False
            st.rerun()
        
        progress_bar = st.progress(0.0)
        status_text = st.empty()
        
        try:
            prog_res = requests.get(f"{API_URL}/progress")
            if prog_res.status_code == 200:
                state = prog_res.json()
                status = state.get("status")
                current = state.get("current", 0)
                total = state.get("total", 0)
                msg = state.get("message", "")
                
                if status == "fetching":
                    status_text.info(msg)
                    time.sleep(1)
                    st.rerun()
                    
                elif status == "processing":
                    if total > 0:
                        ratio = current / total
                        progress_bar.progress(ratio)
                        status_text.info(f"진행 상황: {current} / {total} 완료\n\n{msg}")
                    time.sleep(1)
                    st.rerun()
                    
                elif status == "completed":
                    progress_bar.progress(1.0)
                    status_text.success(msg)
                    st.session_state.is_indexing = False
                    
                elif status == "cancelled":
                    if total > 0:
                        progress_bar.progress(current / total)
                    status_text.error(msg)
                    st.session_state.is_indexing = False
                    
                elif status == "error":
                    status_text.error(msg)
                    st.session_state.is_indexing = False
        except Exception as e:
            status_text.error("서버와 통신하는 중 문제가 발생했습니다.")
            st.session_state.is_indexing = False

tab1, tab2 = st.tabs(["🔍 유사 비트 검색", "🗄️ 데이터베이스 확인"])

with tab1:
    # 레퍼런스 입력 방식에 '유튜브 링크 직접 입력' 옵션 추가
    search_mode = st.radio("레퍼런스 입력 방식 선택", ["파일 직접 업로드", "유튜브에서 검색", "유튜브 링크 직접 입력"], horizontal=True)

    if search_mode == "파일 직접 업로드":
        uploaded_file = st.file_uploader("레퍼런스 오디오 업로드 (WAV/MP3)", type=['wav', 'mp3'])

        if uploaded_file is not None:
            st.subheader("🎧 원본 레퍼런스 곡")
            st.audio(uploaded_file, format='audio/wav')
            
            if st.button("이 파일로 유사 비트 찾기"):
                with st.spinner("보컬을 분리하고 사운드 특징을 분석 중입니다..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "audio/wav")}
                    try:
                        response = requests.post(f"{API_URL}/search", files=files)
                        if response.status_code == 200:
                            data = response.json()
                            if data["status"] == "success":
                                st.session_state.search_results = data["results"]
                                st.session_state.show_top_10 = False
                            else:
                                st.error(f"서버 내부 에러: {data.get('message')}")
                        else:
                            st.error("요청 처리에 실패했습니다.")
                    except requests.exceptions.ConnectionError:
                        st.error("서버와 통신할 수 없습니다. FastAPI 백엔드가 켜져 있는지 확인해주세요.")

    elif search_mode == "유튜브에서 검색":
        st.write("📺 유튜브에서 레퍼런스 곡 찾기")
        search_query = st.text_input("곡 제목이나 아티스트를 입력하세요 (예: Playboi Carti type beat)")
        
        if st.button("유튜브 검색"):
            if search_query:
                with st.spinner("유튜브를 검색 중입니다..."):
                    res = requests.get(f"{API_URL}/youtube_search", params={"q": search_query})
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state.yt_search_results = data.get("results", [])
                        st.session_state.yt_display_count = 5 
                    else:
                        st.error("검색에 실패했습니다.")
                        
        if 'yt_search_results' in st.session_state and st.session_state.yt_search_results:
            st.write("---")
            display_results = st.session_state.yt_search_results[:st.session_state.yt_display_count]
            
            for yt_res in display_results:
                col1, col2 = st.columns([1, 3])
                with col1:
                    if yt_res['thumbnail']:
                        st.image(yt_res['thumbnail'], use_container_width=True)
                with col2:
                    st.write(f"{yt_res['title']}")
                    st.caption(f"👤 {yt_res['channel']}")
                    
                    with st.expander("🎵 클릭하여 미리듣기 및 분석하기"):
                        st.video(yt_res['url'])
                        
                        if st.session_state.analyzing_url == yt_res['url']:
                            prog_bar = st.progress(0.0)
                            stat_text = st.empty()
                            
                            while True:
                                time.sleep(1)
                                try:
                                    poll_res = requests.get(f"{API_URL}/search_status").json()
                                    status = poll_res['status']
                                    prog = float(poll_res['progress'])
                                    msg = poll_res['message']
                                    
                                    prog_bar.progress(prog)
                                    stat_text.info(msg)
                                    
                                    if status == "completed":
                                        st.session_state.search_results = poll_res['results']
                                        st.session_state.show_top_10 = False
                                        st.session_state.analyzing_url = None
                                        st.rerun()
                                    elif status == "error":
                                        stat_text.error(poll_res.get('error', '알 수 없는 오류'))
                                        break
                                except Exception:
                                    stat_text.error("서버와 통신 오류가 발생했습니다.")
                                    break
                        else:
                            is_disabled = st.session_state.analyzing_url is not None
                            if st.button("이 곡으로 유사 비트 찾기", key=f"btn_{yt_res['url']}", disabled=is_disabled):
                                requests.post(f"{API_URL}/search_url", json={"url": yt_res['url']})
                                st.session_state.analyzing_url = yt_res['url']
                                st.rerun()
                                
            if st.session_state.yt_display_count < len(st.session_state.yt_search_results):
                if st.button("검색 결과 더 보기 ➕"):
                    st.session_state.yt_display_count += 5
                    st.rerun()
            st.write("---")

    else:
        # 유튜브 링크 직접 입력 UI
        st.write("🔗 유튜브 링크 직접 입력")
        direct_url = st.text_input("분석하고 싶은 유튜브 영상의 URL 주소를 넣어주세요")
        
        if direct_url:
            # 주소가 입력되면 미리 들어볼 수 있도록 임베드 플레이어를 띄워줍니다
            st.video(direct_url)
            
            # 분석 상태 추적 및 진행바 출력 로직
            if st.session_state.analyzing_url == direct_url:
                prog_bar = st.progress(0.0)
                stat_text = st.empty()
                
                while True:
                    time.sleep(1)
                    try:
                        poll_res = requests.get(f"{API_URL}/search_status").json()
                        status = poll_res['status']
                        prog = float(poll_res['progress'])
                        msg = poll_res['message']
                        
                        prog_bar.progress(prog)
                        stat_text.info(msg)
                        
                        if status == "completed":
                            st.session_state.search_results = poll_res['results']
                            st.session_state.show_top_10 = False
                            st.session_state.analyzing_url = None
                            st.rerun()
                        elif status == "error":
                            stat_text.error(poll_res.get('error', '알 수 없는 오류'))
                            st.session_state.analyzing_url = None
                            break
                    except Exception:
                        stat_text.error("서버와 통신 오류가 발생했습니다.")
                        st.session_state.analyzing_url = None
                        break
            else:
                is_disabled = st.session_state.analyzing_url is not None
                if st.button("이 링크의 곡으로 유사 비트 찾기", disabled=is_disabled):
                    requests.post(f"{API_URL}/search_url", json={"url": direct_url})
                    st.session_state.analyzing_url = direct_url
                    st.rerun()

    # 저장된 검색 결과 화면에 표시 (공통 출력)
    if st.session_state.search_results is not None:
        results = st.session_state.search_results
        st.subheader("🔥 유사한 타입비트 추천")
        
        if len(results) == 0:
            st.write("유사한 비트를 찾을 수 없습니다. 사이드바에서 유튜브 비트를 먼저 DB에 추가해주세요.")
        else:
            display_count = 10 if st.session_state.show_top_10 else 5
            
            for idx, res in enumerate(results[:display_count]):
                title = res['metadata']['title']
                url = res['metadata']['url']
                sim = res['similarity']
                
                with st.expander(f"#{idx+1} | {title} (유사도: {sim:.1f}%)"):
                    st.progress(sim / 100.0)
                    st.markdown(f"🔗 [유튜브 새 창에서 열기]({url})")
                    st.video(url)
                    
            if len(results) > 5 and not st.session_state.show_top_10:
                if st.button("10위까지 더 보기 ➕"):
                    st.session_state.show_top_10 = True
                    st.rerun()
with tab2:
    st.subheader("현재 저장된 타입비트 목록")
    if st.button("목록 새로고침"):
        try:
            res = requests.get(f"{API_URL}/items")
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                if items:
                    st.success(f"총 {data['total_count']}개의 비트가 안전하게 보관되어 있습니다.")
                    df = pd.DataFrame(items)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("현재 데이터베이스가 비어 있습니다. 사이드바에서 유튜브 링크를 인덱싱해주세요.")
            else:
                st.error("서버에서 데이터를 불러오지 못했습니다.")
        except requests.exceptions.ConnectionError:
            st.error("서버와 통신할 수 없습니다.")