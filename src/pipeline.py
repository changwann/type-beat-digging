import yt_dlp
import os

class YoutubeDataPipeline:
    def __init__(self, db_manager, extractor):
        self.db_manager = db_manager
        self.extractor = extractor
        self.current_state = {"status": "idle", "current": 0, "total": 0, "message": ""}
        self.is_cancelled = False 

    def cancel_process(self):
        self.is_cancelled = True
        
    def process_youtube_url(self, url: str):
        self.is_cancelled = False 
        self.current_state = {"status": "fetching", "current": 0, "total": 0, "message": "플레이리스트 정보를 가져오는 중..."}
        
        try:
            # 1. 영상+플레이리스트 혼합 링크에서도 플레이리스트를 강제로 추출합니다.
            ydl_opts_info = {
                'extract_flat': 'in_playlist',
                'quiet': True,
                'noplaylist': False 
            }
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                
            if 'entries' in info:
                entries = list(info['entries'])
            else:
                entries = [info]
                
            total = len(entries)
            self.current_state["total"] = total
            
            os.makedirs('downloaded_beats', exist_ok=True)
            for f in os.listdir('downloaded_beats'):
                file_path = os.path.join('downloaded_beats', f)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            
            # 2. 곡을 다운받을 때는 플레이리스트 다운로드를 막고 단일 곡만 받습니다.
            ydl_opts_download = {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
                'outtmpl': 'downloaded_beats/%(id)s.%(ext)s',
                'quiet': True,
                'noplaylist': True, 
            }
            
            with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                for i, entry in enumerate(entries, 1):
                    if self.is_cancelled:
                        self.current_state = {"status": "cancelled", "current": i-1, "total": total, "message": "사용자에 의해 작업이 취소되었습니다."}
                        return
                        
                    title = entry.get('title', 'Unknown')
                    video_id = entry.get('id')
                    
                    self.current_state.update({
                        "status": "processing",
                        "current": i - 1,
                        "message": f"작업 중: {title}"
                    })
                    
                    try:
                        if not video_id:
                            continue
                            
                        # 꼬리표를 떼고 순수한 곡 고유 ID 주소만 넣어서 에러를 차단합니다.
                        clean_url = f"https://www.youtube.com/watch?v={video_id}"
                        info_dict = ydl.extract_info(clean_url, download=True)
                        
                        file_path = f"downloaded_beats/{video_id}.wav"
                        
                        if os.path.exists(file_path):
                            vector = self.extractor.extract_features(file_path, remove_vocals=False)
                            meta = {"title": info_dict.get('title'), "url": clean_url}
                            self.db_manager.add_vector(vector, meta)
                            os.remove(file_path)
                        else:
                            print(f"다운로드 실패 또는 파일을 찾을 수 없음: {title}")
                            
                    except Exception as e:
                        print(f"다운로드/인덱싱 오류 ({title}): {e}")
                        
                    self.current_state["current"] = i
                        
            if not self.is_cancelled:
                self.current_state = {"status": "completed", "current": total, "total": total, "message": "모든 인덱싱이 완료되었습니다."}
            
        except Exception as e:
            self.current_state = {"status": "error", "current": 0, "total": 0, "message": f"에러 발생: {str(e)}"}