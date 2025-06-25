import json,math
from sentence_transformers import SentenceTransformer
from pymilvus import connections, CollectionSchema, FieldSchema, DataType, Collection, utility
from typing import Dict, List, Any, Union
from tqdm import tqdm
import time
import os


class JobSeekerSearchSystem:
    def __init__(self, auto_init: bool = True):
        self.model = SentenceTransformer("all-MiniLM-L12-v2")
        self.collection_name = "job_seeker"
        self.embedding_dim = 384
        
        if auto_init:
            self._initialize()

    def _initialize(self):
        host = os.getenv("MILVUS_HOST", "localhost")
        port = os.getenv("MILVUS_PORT", "19530")
        connections.connect(host=host, port=port)
            
        if not utility.has_collection(self.collection_name):
            self._create_collection()
        
        self.collection = Collection(self.collection_name)
        
        if not self.collection.has_index():
            self._create_index()
        
        # Koleksiyon yükleme işlemi
        self._load_collection_with_retry()

    def _load_collection_with_retry(self, retries=3, delay=1):
        for i in range(retries):
            try:
                # Eski sürümler için alternatif yükleme kontrolü
                self.collection.load()
                
                # Yüklemenin başarılı olduğunu kontrol etmek için basit bir sorgu deneyelim
                if self._check_collection_loaded():
                    print("Koleksiyon başarıyla yüklendi")
                    return True
                
            except Exception as e:
                print(f"Yükleme hatası (deneme {i+1}/{retries}): {str(e)}")
                time.sleep(delay)
        
        raise Exception("Koleksiyon yüklenemedi")

    def _check_collection_loaded(self):
        try:
            # Basit bir sorgu ile koleksiyonun yüklü olduğunu kontrol et
            self.collection.query(expr="id >= 0", output_fields=["id"], limit=1)
            return True
        except:
            return False

    def reset_collection(self):
        """Drops and recreates the collection with the current schema"""
        if utility.has_collection(self.collection_name):
            utility.drop_collection(self.collection_name)
        self._create_collection()
        self._create_index()
        print("Koleksiyon başarıyla sıfırlandı")

    def _create_collection(self):
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            FieldSchema(name="job_data", dtype=DataType.JSON),
            FieldSchema(name="sector_id", dtype=DataType.INT64),
            FieldSchema(name="location_id", dtype=DataType.INT64),
            FieldSchema(name="experience_level", dtype=DataType.INT64),
            FieldSchema(name="is_deleted", dtype=DataType.BOOL)
        ]
        schema = CollectionSchema(fields, description="Job Seeker Collection")
        self.collection = Collection(self.collection_name, schema)
        print(f"Koleksiyon oluşturuldu: {self.collection_name}")

    def _create_index(self):
        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 256}
        }
        self.collection.create_index("embedding", index_params)
        print("Vektör indeksi oluşturuldu")

    def add_jobs(self, jobs: Union[Dict[str, Any], List[Dict[str, Any]]], batch_size: int = 100) -> bool:
        if not jobs:
            return False

        if isinstance(jobs, dict):
            jobs = [jobs]

        for i in tqdm(range(0, len(jobs), batch_size), desc="İş ilanları ekleniyor"):
            batch = jobs[i:i + batch_size]
            if not self._insert_batch(batch):
                print(f"{len(batch)} kayıt eklenemedi")
        
        # Veri eklendikten sonra koleksiyonu yeniden yükle
        self._load_collection_with_retry()
        return True

    def _insert_batch(self, batch: List[Dict[str, Any]]) -> bool:
        try:
            ids = []
            embeddings = []
            job_data = []
            sector_ids = []
            location_ids = []
            experience_levels = []
            is_deleted_flags = []

            for job in batch:
                if not job.get("skills"):
                    continue
                    
                ids.append(job["id"])
                embeddings.append(self.model.encode(job["skills"]).tolist())
                
                job_data.append(json.dumps({
                    "skills": job["skills"],
                    "language": job.get("language", ""),
                    "job_type": job.get("jobType", ""),
                    "work_location": job.get("workLocation", ""),
                    "salary_range": [job.get("salaryMin", 0), job.get("salaryMax", 0)],
                    "education_level": job.get("educationLevel", ""),
                    "dates": {
                        "created": job.get("createdDate", ""),
                        "modified": job.get("modifiedDate", "")
                    },
                    "latitude": job.get("latitude"),  
                    "longitude": job.get("longitude"),   
                    "images": job.get("images", []),
                    "isVerifiedProfile": job.get("isVerifiedProfile", "false"),
                    "cityName" : job.get("cityName",""),
                    "userId": job.get("userId", 0),
                    "jobTitle": job.get("jobTitle", ""),
                    "name": job.get("name", ""),
                    "age": job.get("age", 0),
                }))
                
                sector_ids.append(job.get("sectorId", 0))
                location_ids.append(job.get("locationId", 0))
                experience_levels.append(job.get("experienceLevel", 0))
                is_deleted_flags.append(job.get("isDeleted", False))

            if ids:
                insert_data = [
                    ids,
                    embeddings,
                    job_data,
                    sector_ids,
                    location_ids,
                    experience_levels,
                    is_deleted_flags
                ]
                self.collection.insert(insert_data)
                return True
                
        except Exception as e:
            print(f"\nEkleme hatası: {str(e)}")
            if batch:
                print(f"Hatalı kayıt örneği: {batch[0]}")
            return False
        
        return False

    def search_jobs(self, candidate_data: Dict[str, Any]) -> Dict[str, Any]:
        # Koleksiyonun yüklü olduğundan emin ol
        if not self._check_collection_loaded():
            self._load_collection_with_retry()

        query_vec = self.model.encode(candidate_data["skills"]).tolist()

        search_params = {
            "data": [query_vec],
            "anns_field": "embedding",
            "param": {"metric_type": "IP", "params": {"nprobe": 16}},
            "limit": 50,
            "expr": "is_deleted == false",
            "output_fields": ["job_data", "sector_id", "location_id", "experience_level"]
        }

        if "filters" in candidate_data:
            filter_expr = self._build_filter_expression(candidate_data["filters"])
            if filter_expr:
                search_params["expr"] = f"{search_params['expr']} and {filter_expr}"

        try:
            results = self.collection.search(**search_params)
            return {
                "id": candidate_data.get("id"),
                "results": self._process_results(results[0], candidate_data)
            }
        except Exception as e:
            print(f"Arama hatası: {str(e)}")
            return {
                "id": candidate_data.get("id"),
                "results": [],
                "error": str(e)
            }

    def _build_filter_expression(self, filters: Dict[str, Any]) -> str:
        conditions = []
        
        if "sector_ids" in filters:
            ids = ",".join(str(id) for id in filters["sector_ids"])
            conditions.append(f"sector_id in [{ids}]")
            
        if "location_ids" in filters:
            ids = ",".join(str(id) for id in filters["location_ids"])
            conditions.append(f"location_id in [{ids}]")
            
        if "min_experience" in filters:
            conditions.append(f"experience_level >= {filters['min_experience']}")
            
        if "max_experience" in filters:
            conditions.append(f"experience_level <= {filters['max_experience']}")
            
        return " and ".join(conditions) if conditions else ""

    def _process_results(self, hits: List[Any], candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        processed = []
        
        candidate_lat = candidate.get("latitude")
        candidate_lon = candidate.get("longitude")
       
        for hit in hits:
            job = json.loads(hit.entity.get("job_data"))
            
            job_lat = job.get("latitude")
            job_lon = job.get("longitude")
            
            if candidate_lat is not None and candidate_lon is not None and job_lat is not None and job_lon is not None:
               radius = round(self._haversine_distance(candidate_lat, candidate_lon, job_lat, job_lon), 2)
            else:
                radius = 0
                
            milvus_score = round((hit.distance + 1) / 2 * 100, 1)
            final_score = self._calculate_score(job, milvus_score, candidate, hit.entity)
            
            processed.append({
                "jobPostId": hit.id,
                "score": final_score,
                "milvus_score": milvus_score,
                "is_ignored": False,
            })
        
        return sorted(processed, key=lambda x: x["score"], reverse=True)[:10]

    def _calculate_score(self, job: Dict[str, Any], milvus_score: float, 
                        candidate: Dict[str, Any], entity: Any) -> float:
        scores = {
            "skills": milvus_score * 0.5,
            "language": 100 * 0.1 if job.get("language") == candidate.get("language") else 0,
            "experience": self._experience_score(entity.get("experience_level", 0), 
                                              candidate.get("experience_level", 0)) * 0.2,
            "salary": self._salary_score(job.get("salary_range", [0, 0]), 
                                       candidate.get("salary_expectation", 0)) * 0.1,
            "location": 100 * 0.05 if entity.get("location_id") == candidate.get("preferred_location_id") else 0,
            "sector": 100 * 0.05 if entity.get("sector_id") == candidate.get("preferred_sector_id") else 0
        }
        
        return round(sum(scores.values()), 1)

    def create_or_update_jobs(self, jobs: Union[Dict[str, Any], List[Dict[str, Any]]], batch_size: int = 100) -> bool:
        if not jobs:
            return False

        if isinstance(jobs, dict):
            jobs = [jobs]

        for i in tqdm(range(0, len(jobs), batch_size), desc="İş ilanları ekleniyor (CreateOrUpdate)"):
            batch = jobs[i:i + batch_size]
            ids_to_delete = [job["id"] for job in batch if "id" in job]

            # Milvus'tan aynı ID'ye sahip kayıtları sil
            expr = f"id in [{', '.join(map(str, ids_to_delete))}]"
            try:
                self.collection.delete(expr)
            except Exception as e:
                print(f"Silme hatası (ID'ler: {ids_to_delete}): {str(e)}")

            # Ardından ekle
            if not self._insert_batch(batch):
                print(f"{len(batch)} kayıt eklenemedi")
        
        # Veri güncellendikten sonra koleksiyonu yeniden yükle
        self._load_collection_with_retry()
        return True
    
    def safe_reset_collection(self):
        """Güvenli koleksiyon sıfırlama ve otomatik yeniden oluşturma"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"\n--- Sıfırlama denemesi {attempt + 1}/{max_retries} ---")
                
                # 1. Eski koleksiyonu kontrollü silme
                if utility.has_collection(self.collection_name):
                    print("Eski koleksiyon siliniyor...")
                    utility.drop_collection(self.collection_name)
                    time.sleep(5)  # Milvus'un iç temizliği için kritik bekleme
                
                # 2. Yeni koleksiyon oluşturma
                print("Yeni koleksiyon oluşturuluyor...")
                self._create_collection()
                time.sleep(2)  # Şema stabilizasyonu için
                
                # 3. Index oluşturma
                print("Indexler hazırlanıyor...")
                self._create_index()
                time.sleep(3)  # Indexleme için bekleme
                
                # 4. Yükleme ve sağlık kontrolü
                print("Koleksiyon yükleniyor...")
                self._load_collection_with_retry()

                return True
                
            except Exception as e:
                print(f"❌ Hata (Deneme {attempt + 1}): {str(e)}")
                if attempt == max_retries - 1:
                    print("⛔ Maksimum deneme sayısı aşıldı")
                    raise
                time.sleep(5 * (attempt + 1))  # Artan bekleme süresi
 
    
    @staticmethod
    def _experience_score(job_exp: int, candidate_exp: int) -> float:
            diff = abs(job_exp - candidate_exp)
            return max(0, 100 - (diff * 15))

    @staticmethod
    def _salary_score(salary_range: List[int], expected: float) -> float:
        min_s, max_s = salary_range
        if min_s <= expected <= max_s:
            return 100
        return 50 if expected < min_s else 0

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        R = 6371
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

# if __name__ == "__main__":
    # Sistem başlatma
    # try:
    #     jss = JobSearchSystem()
        
        # Koleksiyonu sıfırla (sadece ilk çalıştırmada veya schema değişikliğinde)
        #jss.reset_collection()
        
        # Örnek veri ekleme
        # with open("jobposts.json", "r") as f:
        #     jobs_data = json.load(f)
        # jss.add_jobs(jobs_data)
        #burada veri geldiğinde jobs_dataya ekle

        #SearchJobs 
        
        #AddJobs
        #DeleteAndUpdate
        
        #Örnek aramağ
    #     results = jss.search_jobs({
    #     "id": 9990,
    #     "skills": "Python, SQL, Data Analysis",
    #     "language": "EN",
    #     "experience_level": 5,
    #     "salary_expectation": 10000,  # SalaryMin 5720, SalaryMax 14930 arası bir değer
    #     "preferred_sector_id": 1,
    #     "preferred_location_id": 6,
    #     "filters": {
    #         "min_experience": 5,
    #         "max_experience": 5,
    #         "sector_ids": [1],
    #         "location_ids": [6]
    #     }
    # })

        
    #     print(json.dumps(results, indent=2, ensure_ascii=False))
    # except Exception as e:
    #     print(f"Uygulama hatası: {str(e)}")