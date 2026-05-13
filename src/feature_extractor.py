import torch
import numpy as np
import librosa
from panns_inference import AudioTagging
import subprocess
import os
import shutil
import uuid

class AudioFeatureExtractor:
    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        try:
            self.model = AudioTagging(checkpoint_path=None, device=self.device)
            print("PANNs 모델 로드 성공 (4마디 루프 기반 + L2 정규화 적용)")
        except Exception as e:
            print(f"모델 로드 중 오류 발생: {e}")

    def _remove_vocals(self, audio_path: str):
        print(f"\n[보컬 분리 시작] 레퍼런스 곡의 순수 비트를 추출합니다: {os.path.basename(audio_path)}")
        temp_dir = f"./temp_demucs_{uuid.uuid4().hex[:8]}"
        os.makedirs(temp_dir, exist_ok=True)
        
        command = [
            "demucs",
            "-d", "cpu",
            "--two-stems=vocals",
            "--out", temp_dir,
            audio_path
        ]
        
        try:
            # 기존의 DEVNULL(숨김 처리)을 지우고, 에러를 텍스트로 캡처하도록 변경합니다.
            subprocess.run(command, check=True, capture_output=True, text=True)
            
            filename = os.path.splitext(os.path.basename(audio_path))[0]
            instrumental_path = os.path.join(temp_dir, "htdemucs", filename, "no_vocals.wav")
            
            if os.path.exists(instrumental_path):
                print("[보컬 분리 완료] 보컬이 제거되었습니다.")
                return instrumental_path, temp_dir
            else:
                print("보컬 분리 파일 생성 실패, 원본을 사용합니다.")
                return audio_path, temp_dir
                
        except subprocess.CalledProcessError as e:
            # 이제 Demucs가 토해내는 '진짜 에러 메시지'가 터미널에 빨간 글씨로 찍힙니다!
            print("\n================ [Demucs 치명적 오류 발생] ================")
            print(e.stderr) 
            print("===========================================================\n")
            return audio_path, temp_dir

    def _get_4bar_loop(self, y, sr):
        # 1. 곡의 BPM(템포) 추출
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = tempo[0] if isinstance(tempo, np.ndarray) else tempo
        
        # 2. 4마디(16비트)의 길이를 초 단위로 계산
        # 1분(60초)을 BPM으로 나누면 1비트의 길이, 곱하기 16
        loop_duration = (60.0 / bpm) * 16
        
        if len(y) <= sr * loop_duration:
            return y
            
        hop_length = 512
        rmse = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
        window_size = int(sr * loop_duration / hop_length)
        
        # 3. 에너지가 가장 높은 정확한 4마디 구간 찾기
        max_energy = 0
        best_start = 0
        for i in range(len(rmse) - window_size):
            current_energy = np.sum(rmse[i:i+window_size])
            if current_energy > max_energy:
                max_energy = current_energy
                best_start = i
                
        start_sample = best_start * hop_length
        return y[start_sample : start_sample + int(sr * loop_duration)]

    def extract_features(self, audio_path: str, remove_vocals: bool = False) -> np.ndarray:
        temp_out_dir = None
        target_path = audio_path
        
        try:
            if remove_vocals:
                target_path, temp_out_dir = self._remove_vocals(audio_path)
            
            y, sr = librosa.load(target_path, sr=32000) 
            y = librosa.util.normalize(y)
            
            # --- 변경된 핵심 로직: 곡 전체를 10초 단위로 썰어서 분석 ---
            chunk_length = sr * 10  # 10초
            embeddings = []
            
            # 곡 처음부터 끝까지 10초씩 이동하며 훑습니다.
            for i in range(0, len(y), chunk_length):
                chunk = y[i : i + chunk_length]
                
                # 마지막 남은 자투리가 너무 짧으면(3초 미만) 버림
                if len(chunk) < sr * 3:
                    continue
                    
                # PANNs 규격에 맞게 모자란 길이는 무음(0)으로 패딩
                if len(chunk) < chunk_length:
                    chunk = np.pad(chunk, (0, chunk_length - len(chunk)))
                    
                chunk = chunk[None, :]
                _, embedding = self.model.inference(chunk)
                embeddings.append(embedding[0])
                
            # 에러 방지
            if not embeddings:
                return np.zeros((1, 2048))
                
            # 여러 개의 10초짜리 조각들을 평균 내어 곡 전체를 대표하는 '하나의 질감'으로 압축합니다.
            final_embedding = np.mean(embeddings, axis=0)
            
            # L2 정규화: 크기에 따른 노이즈를 지우고 순수한 방향(유사도)만 남깁니다.
            norm = np.linalg.norm(final_embedding)
            if norm > 0:
                final_embedding = final_embedding / norm
                
            return np.expand_dims(final_embedding, axis=0) 
            
        except Exception as e:
            print(f"특성 추출 에러: {e}")
            return np.zeros((1, 2048))
            
        finally:
            if temp_out_dir and os.path.exists(temp_out_dir):
                shutil.rmtree(temp_out_dir, ignore_errors=True)