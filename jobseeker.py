import json, math
from sentence_transformers import SentenceTransformer
from pymilvus import connections, CollectionSchema, FieldSchema, DataType, Collection, utility
from typing import Dict, List, Any, Union
from tqdm import tqdm
import time
import os


class JobSeekerSearchSystem:
    def __init__(self, auto_init: bool = True):
        self.model = SentenceTransformer("all-MiniLM-L12-v2")
        self.collection_name = "job_seeker_new"
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

        self._load_collection_with_retry()

    def _load_collection_with_retry(self, retries=3, delay=1):
        for i in range(retries):
            try:
                self.collection.load()
                if self._check_collection_loaded():
                    print("Collection loaded successfully")
                    return True
            except Exception as e:
                print(f"Load error (attempt {i + 1}/{retries}): {str(e)}")
                time.sleep(delay)

        raise Exception("Failed to load collection")

    def _check_collection_loaded(self):
        try:
            self.collection.query(expr="id >= 0", output_fields=["id"], limit=1)
            return True
        except:
            return False

    def _create_collection(self):
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            FieldSchema(name="job_data", dtype=DataType.JSON),
            FieldSchema(name="is_deleted", dtype=DataType.BOOL)
        ]
        schema = CollectionSchema(fields, description="Simple Job Seeker Collection")
        self.collection = Collection(self.collection_name, schema)
        print(f"Collection created: {self.collection_name}")

    def _create_index(self):
        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 256}
        }
        self.collection.create_index("embedding", index_params)
        print("Vector index created")

    def add_jobs(self, jobs: Union[Dict[str, Any], List[Dict[str, Any]]], batch_size: int = 100) -> bool:
        """
        Add job postings to the collection
        Args:
            jobs: Single job dict or list of job dicts
            batch_size: Number of jobs to insert in each batch
        Returns:
            bool: True if successful, False otherwise
        """
        if not jobs:
            return False

        if isinstance(jobs, dict):
            jobs = [jobs]

        for i in tqdm(range(0, len(jobs), batch_size), desc="Adding jobs"):
            batch = jobs[i:i + batch_size]
            if not self._insert_batch(batch):
                print(f"Failed to add {len(batch)} records")

        self._load_collection_with_retry()
        return True

    def _insert_batch(self, batch: List[Dict[str, Any]]) -> bool:
        try:
            ids = []
            embeddings = []
            job_data = []
            is_deleted_flags = []

            for job in batch:
                if not job.get("skills"):
                    continue

                # Skill'lerden embedding oluştur
                skill_text = " ".join(job["skills"])
                embedding = self.model.encode(skill_text).tolist()  # numpy array'den listeye çevir

                ids.append(job["id"])
                embeddings.append(embedding)  # Bu artık doğru formattta float listesi

                job_data.append(json.dumps({
                    "skills": job["skills"],
                    "userId": job.get("userId"),
                    "latitude": job.get("latitude"),
                    "longitude": job.get("longitude"),
                    "is_ignored": False,
                }))

                is_deleted_flags.append(job.get("isDeleted", False))

            if ids:
                insert_data = [ids, embeddings, job_data, is_deleted_flags]
                self.collection.insert(insert_data)
                return True

        except Exception as e:
            print(f"Insert error: {str(e)}")
            if batch:
                print(f"Problematic record: {batch[0]}")
            return False

    def search_jobs(self, candidate_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self._check_collection_loaded():
            self._load_collection_with_retry()

        # Ensure skills is a list of strings
        skills = candidate_data["skills"]
        print(f"Skills: {skills}")
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            return {
                "id": candidate_data.get("id"),
                "results": [],
                "error": "Skills must be a list of strings"
            }

        query_vec = self.model.encode(skills).tolist()
        if isinstance(query_vec[0], list):
            query_vec = query_vec[0]  # İlk listeyi al
        print("",query_vec)
        # Ensure all vector elements are floats
        try:
            query_vec = [float(x) for x in query_vec]
        except (ValueError, TypeError) as e:
            return {
                "id": candidate_data.get("id"),
                "results": [],
                "error": f"Vector conversion error: {str(e)}"
            }

        search_params = {
            "data": [query_vec],  # Note the list of list format
            "anns_field": "embedding",
            "param": {"metric_type": "IP", "params": {"nprobe": 16}},
            "limit": 10,
            "expr": "is_deleted == false",
            "output_fields": ["job_data", "id"]
        }
        print(f"Search results: {candidate_data}")
        try:
            results = self.collection.search(**search_params)
            return {
                "id": candidate_data.get("id"),
                "results": self._process_results(results[0], candidate_data)
            }
        except Exception as e:
            print(f"Search error: {str(e)}")
            return {
                "id": candidate_data.get("id"),
                "results": [],
                "error": str(e)
            }

    def _process_results(self, hits: List[Any], candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
        processed = []

        candidate_lat = candidate.get("latitude")
        candidate_lon = candidate.get("longitude")

        for hit in hits:
            job = json.loads(hit.entity.get("job_data"))

            job_lat = job.get("latitude")
            job_lon = job.get("longitude")
            ignored = job.get("is_ignored")
            userId = job.get("userId")

            if candidate_lat and candidate_lon and job_lat and job_lon:
                radius = round(self._haversine_distance(candidate_lat, candidate_lon, job_lat, job_lon), 2)
            else:
                radius = 0

            milvus_score = round((hit.distance + 1) / 2 * 100, 1)

            processed.append({
                "job_id": hit.id,
                "score": milvus_score,
                "milvus_score": milvus_score,
                "is_ignored": ignored,
                "radius": radius,
                "userId": userId,
            })

        return processed

    def get_seeker_by_id(self, seeker_id: int) -> dict:
        """Milvus'tan ID'ye göre job seeker getirir"""
        try:
            results = self.collection.query(
                expr=f"id == {seeker_id}",
                output_fields=["job_data", "id"]
            )
            if results:
                seeker_data = json.loads(results[0]["job_data"])
                return {"id": results[0]["id"], **seeker_data}
            return None
        except Exception as e:
            print(f"Error getting job seeker: {str(e)}")
            return None

    # JobSeekerSearchSystem sınıfına bu metodu ekleyin
    def update_ignore_status(self, seeker_id: int, is_ignored: bool) -> bool:
        """Job seeker'ın is_ignored durumunu günceller"""
        try:
            # Önce mevcut veriyi al
            result = self.collection.query(
                expr=f"id == {seeker_id}",
                output_fields=["embedding", "job_data", "is_deleted"]
            )

            if not result:
                return False

            current_data = result[0]
            job_data = json.loads(current_data["job_data"])

            # Job_data içinde is_ignored alanını güncelle
            job_data["is_ignored"] = is_ignored

            # Güncellenmiş veriyi kaydet (TÜM alanları sağla)
            self.collection.upsert([
                [seeker_id],  # id
                [current_data["embedding"]],  # embedding
                [json.dumps(job_data)],  # job_data
                [current_data["is_deleted"]]  # is_deleted
            ])

            return True
        except Exception as e:
            print(f"Error updating ignore status: {str(e)}")
            return False



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

    def reset_collection(self):
        """Drops and recreates the collection with the current schema"""
        if utility.has_collection(self.collection_name):
            utility.drop_collection(self.collection_name)
        self._create_collection()
        self._create_index()
        print("Collection reset successfully")


