import chromadb
import numpy as np
import uuid

class VectorDBManager:
    def __init__(self, db_path="./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        
        # 차원이 바뀌었으므로 기존 컬렉션과 충돌할 수 있습니다. 
        # 안전하게 'type_beats_v2'라는 새로운 컬렉션을 만듭니다.
        self.collection = self.client.get_or_create_collection(
            name="type_beats_v2",
            metadata={"hnsw:space": "cosine"} 
        )
        print(f"[DB 로드 완료] 현재 저장된 비트 수: {self.collection.count()}개")

    def add_vector(self, vector: np.ndarray, meta: dict):
        # 딥러닝 모델이 뽑아낸 벡터를 DB가 읽기 편한 1차원 리스트로 변환합니다.
        flat_vector = vector.flatten().tolist()
        
        # 각 곡마다 겹치지 않는 고유한 랜덤 ID를 부여합니다.
        doc_id = str(uuid.uuid4())
        
        # 벡터와 메타데이터를 한 번에 DB에 밀어 넣습니다. (자동 영구 저장)
        self.collection.add(
            embeddings=[flat_vector],
            metadatas=[meta],
            ids=[doc_id]
        )
        
    def search_similar(self, query_vector: np.ndarray, k=5):
        if self.collection.count() == 0:
            return []
            
        flat_query = query_vector.flatten().tolist()
        
        # DB에 쿼리를 던져서 가장 질감이 비슷한 상위 k개를 찾아옵니다.
        results = self.collection.query(
            query_embeddings=[flat_query],
            n_results=k
        )
        
        formatted_results = []
        if results['distances'] and results['metadatas']:
            for i in range(len(results['ids'][0])):
                # ChromaDB의 거리값(Distance)을 직관적인 유사도(%)로 변환합니다.
                distance = results['distances'][0][i]
                similarity = (1 - distance) * 100
                
                formatted_results.append({
                    "metadata": results['metadatas'][0][i],
                    "similarity": similarity
                })
                
        return formatted_results
    
    def get_all_items(self):
        # DB에서 벡터값은 제외하고 곡 정보(메타데이터)만 전체 조회합니다.
        results = self.collection.get(include=["metadatas"])
        
        # None 값이 섞여 있을 수 있으므로 리스트 컴프리헨션으로 안전하게 반환합니다.
        return [item for item in results["metadatas"] if item is not None]