import yt_dlp
import uuid
from pydantic import BaseModel

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import shutil
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
import uvicorn
from pydantic import BaseModel

from src.feature_extractor import AudioFeatureExtractor
from src.vector_db import VectorDBManager
from src.pipeline import YoutubeDataPipeline

from fastapi import BackgroundTasks

app = FastAPI(title="Type Beat Digging API")

from fastapi.staticfiles import StaticFiles
# 임시 오디오 파일을 서빙할 수 있도록 static 마운트
os.makedirs("temp_audio", exist_ok=True)
app.mount("/audio", StaticFiles(directory="temp_audio"), name="audio")

# 서버 시작 시 메모리에 모델과 DB 로드
extractor = AudioFeatureExtractor()
db_manager = VectorDBManager()
pipeline = YoutubeDataPipeline(db_manager, extractor)

class IndexRequest(BaseModel):
    url: str

@app.post("/index")
async def index_youtube_url(request: IndexRequest, background_tasks: BackgroundTasks):
    # 백그라운드에서 유튜브 다운로드 및 DB 인덱싱 실행 (서버 블로킹 방지)
    background_tasks.add_task(pipeline.process_youtube_url, request.url)
    return {"message": "유튜브 비트 인덱싱이 백그라운드에서 시작되었습니다."}

@app.post("/search")
async def search_similar(file: UploadFile = File(...)):
    temp_file_path = f"temp_audio/{file.filename}"
    
    # 클라이언트가 업로드한 파일 임시 저장
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # 1. 특징 추출 (1x2048 형태의 벡터) - 쿼리 곡에만 보컬 분리 적용
        query_vector = extractor.extract_features(temp_file_path, remove_vocals=True)
        
        # 2. ChromaDB 검색 (기존 FAISS 주석도 상황에 맞게 수정)
        results = db_manager.search_similar(query_vector.astype('float32'), k=10)
        
        return {"status": "success", "results": results}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    finally:
        # 처리 완료 후 임시 파일 삭제 (리소스 최적화)
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# 분석 진행 상태를 추적할 전역 변수를 선언합니다.
search_state = {"status": "idle", "progress": 0.0, "message": "", "results": None, "error": ""}

class YoutubeUrlRequest(BaseModel):
    url: str

@app.get("/youtube_search")
async def youtube_search(q: str):
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'default_search': 'ytsearch50',
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(q, download=False)
            entries = info.get('entries', [])
            
            results = []
            for entry in entries:
                results.append({
                    "title": entry.get('title'),
                    "url": entry.get('url'),
                    "channel": entry.get('uploader', '알 수 없음'),
                    "thumbnail": entry.get('thumbnails', [{}])[0].get('url', '') if entry.get('thumbnails') else ''
                })
            return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def process_url_search(url: str):
    global search_state
    search_state = {"status": "processing", "progress": 0.1, "message": "1/3: 유튜브에서 음원을 다운로드하는 중입니다...", "results": None, "error": ""}
    
    temp_id = uuid.uuid4().hex[:8]
    temp_file_base = f"temp_audio/ref_{temp_id}"
    temp_file_path = f"{temp_file_base}.wav"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
        'outtmpl': temp_file_base + '.%(ext)s',
        'quiet': True,
        'noplaylist': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if os.path.exists(temp_file_path):
            search_state["progress"] = 0.4
            search_state["message"] = "2/3: 보컬을 제거하고 순수 비트를 추출 중입니다... (1~2분 소요)"
            
            # Demucs 보컬 분리 및 PANNs 특징 추출 진행
            query_vector = extractor.extract_features(temp_file_path, remove_vocals=True)
            
            search_state["progress"] = 0.8
            search_state["message"] = "3/3: 데이터베이스에서 유사도를 계산하는 중입니다..."
            
            results = db_manager.search_similar(query_vector.astype('float32'), k=10)
            
            search_state["progress"] = 1.0
            search_state["message"] = "분석 완료!"
            search_state["results"] = results
            search_state["status"] = "completed"
        else:
            search_state["status"] = "error"
            search_state["error"] = "음원 다운로드에 실패했습니다."
            
    except Exception as e:
        search_state["status"] = "error"
        search_state["error"] = str(e)
        
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.post("/search_url")
async def search_similar_by_url(request: YoutubeUrlRequest, background_tasks: BackgroundTasks):
    # 무거운 작업을 백그라운드로 넘겨서 프론트엔드가 멈추지 않게 합니다.
    background_tasks.add_task(process_url_search, request.url)
    return {"status": "started"}

@app.get("/search_status")
async def get_search_status():
    # 프론트엔드가 1초마다 이 주소로 진행률을 물어봅니다.
    return search_state

@app.get("/progress")
async def get_progress():
    # 파이프라인 클래스가 기록하고 있는 현재 진행 상태를 반환
    return pipeline.current_state

@app.get("/items")
async def get_items():
    try:
        # DB 매니저를 통해 모든 저장 목록을 가져와서 반환
        items = db_manager.get_all_items()
        return {"status": "success", "items": items, "total_count": len(items)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
@app.post("/cancel")
async def cancel_indexing():
    # 파이프라인의 취소 스위치를 켭니다.
    pipeline.cancel_process()
    return {"message": "인덱싱 취소 요청이 접수되었습니다."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)