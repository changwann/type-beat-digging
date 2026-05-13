# Type Beat Digging Program v2

사운드 질감 분석 기반 힙합 타입비트 추천 시스템입니다. PANNs 모델을 활용하여 비트의 고유한 질감을 분석하고, 보컬 분리 기술을 통해 레퍼런스 곡과 가장 유사한 타입비트를 찾아줍니다.

## 주요 기능

1. 유튜브 비트 인덱싱: 플레이리스트 및 단일 영상 URL을 통해 유튜브 오디오를 데이터베이스에 저장합니다.
2. 보컬 분리(Demucs): 레퍼런스 곡에서 보컬을 제거하여 순수한 비트의 질감($2048\text{d}$ 의 벡터)만을 추출합니다.
3. 정밀 사운드 분석: 곡 전체를 10초 단위로 분석하여 평균적인 사운드 지문을 생성하며, L2 정규화를 통해 유사도 측정의 정확도를 높였습니다.
4. 다중 레퍼런스 입력: 로컬 파일 업로드, 앱 내 유튜브 검색, 유튜브 링크 직접 입력을 모두 지원합니다.
5. 미리보기 및 결과 확장: 검색 결과와 추천 비트를 앱 내부에서 바로 들어볼 수 있으며, 상위 10위까지 결과를 확인할 수 있습니다.

## 설치 및 실행 방법

### 1. 가상환경 및 라이브러리 설치

먼저 가상환경을 활성화한 후 필요한 패키지들을 설치합니다.

pip install -r requirements.txt
brew install ffmpeg  # Mac 환경에서 보컬 분리를 위해 필수 설치

### 2. 백엔드 서버 실행 (FastAPI)

uvicorn api:app --reload

### 3. 프론트엔드 실행 (Streamlit)

streamlit run app.py

## 프로젝트 구조

- api.py: 검색 및 분석 요청을 처리하는 FastAPI 백엔드
- app.py: 사용자 인터페이스를 제공하는 Streamlit 프론트엔드
- src/
  - feature_extractor.py: 오디오 전처리 및 PANNs 기반 특징 추출 로직
  - vector_db.py: ChromaDB를 활용한 벡터 데이터 저장 및 검색 매니저
  - pipeline.py: 유튜브 다운로드 및 인덱싱 자동화 파이프라인

## 기술 스택

- Language: Python 3.13+
- Model: PANNs (Pretrained Audio Neural Networks)
- Vocal Separation: Demucs v4
- Database: ChromaDB (Vector Database)
- Backend: FastAPI
- Frontend: Streamlit
- Audio Processing: librosa, torchaudio