from flask import Flask, request, jsonify
import redis
import json
from jobsearch import JobSearchSystem
from jobseeker import JobSeekerSearchSystem
import os
import requests


app = Flask(__name__)

# Redis bağlantısı (default localhost:6379)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(redis_url)

# JobSearchSystem örneği
jss = JobSearchSystem()
jseeker = JobSeekerSearchSystem()

@app.route("/health")
def health():
    return jsonify({"success": "Ok"})

@app.route("/add_jobs", methods=["POST"])
def add_jobs():
    jobs = request.json
    if not jobs:
        return jsonify({"success": False, "message": "İş ilanları verisi yok"}), 400
    
    result = jss.add_jobs(jobs)
    return jsonify({"success": result})

@app.route("/create_or_update_jobs", methods=["POST"])
def create_or_update_jobs():
    jobs = request.json
    if not jobs:
        return jsonify({"success": False, "message": "İş ilanları verisi yok"}), 400
    
    result = jss.create_or_update_jobs(jobs)
    return jsonify({"success": result})


@app.route("/search_jobs", methods=["POST"])
def search_jobs():
    candidate_data = request.json
    if not candidate_data or "skills" not in candidate_data:
        return jsonify({"success": False, "message": "Arama için gerekli bilgiler eksik"}), 400

    results = jss.search_jobs(candidate_data)

    # Her bir iş için detay bilgilerini al
    for job in results["results"]:
        job_id = job["job_id"]
        user_id = job.get("userId", 0)  # userId yoksa 0 kullan

        try:
            # API isteği yap
            response = requests.get(
                f'https://api.swipingjobs.com/Redis/jobPost/{job_id}/{user_id}',
                headers={'accept': 'text/plain'}
            )

            if response.status_code == 200:
                response_data = response.json()
                # Gelen cevabın body kısmını details olarak kaydet
                if response_data.get("isSuccess", False) and "body" in response_data:
                    job["details"] = response_data["body"]
                else:
                    job["details"] = {}  # Hata durumunda boş bir dict ekle
            else:
                job["details"] = {}
        except Exception as e:
            print(f"API isteği sırasında hata oluştu (job_id: {job_id}): {str(e)}")
            job["details"] = {}  # Hata durumunda boş bir dict ekle

    # Redis'e kaydet
    redis_key = f"jobSeekerMatch:{results['id']}"
    redis_client.set(redis_key, json.dumps(results, ensure_ascii=False))

    return jsonify(results)

@app.route("/createPostIndex", methods=["POST"])
def createPostIndex():
    jss.safe_reset_collection();
    return jsonify({"success": "Ok"})

@app.route("/createseekerIndex", methods=["POST"])
def createseekerIndex():
    jseeker.safe_reset_collection();
    return jsonify({"success": "Ok"})

@app.route("/add_seeker", methods=["POST"])
def add_seeker():
    jobs = request.json
    if not jobs:
        return jsonify({"success": False, "message": "İş ilanları verisi yok"}), 400
    
    result = jseeker.add_jobs(jobs)
    return jsonify({"success": result})

@app.route("/create_or_update_seeker", methods=["POST"])
def create_or_update_seeker():
    jobs = request.json
    if not jobs:
        return jsonify({"success": False, "message": "İş ilanları verisi yok"}), 400
    
    result = jseeker.create_or_update_jobs(jobs)
    return jsonify({"success": result})

@app.route("/search_seeker", methods=["POST"])
def search_seeker():
    candidate_data = request.json
    if not candidate_data or "skills" not in candidate_data:
        return jsonify({"success": False, "message": "Arama için gerekli bilgiler eksik"}), 400

    results = jss.search_jobs(candidate_data)

    # Her bir iş için detay bilgilerini al
    for job in results["results"]:
        job_id = job["job_id"]
        user_id = job.get("userId", 0)  # userId yoksa 0 kullan

        try:
            # API isteği yap
            response = requests.get(
                f'https://api.swipingjobs.com/Redis/seeker/{job_id}/{user_id}',
                headers={'accept': 'text/plain'}
            )

            if response.status_code == 200:
                response_data = response.json()
                # Gelen cevabın body kısmını details olarak kaydet
                if response_data.get("isSuccess", False) and "body" in response_data:
                    job["details"] = response_data["body"]
                else:
                    job["details"] = {}  # Hata durumunda boş bir dict ekle
            else:
                job["details"] = {}
        except Exception as e:
            print(f"API isteği sırasında hata oluştu (job_id: {job_id}): {str(e)}")
            job["details"] = {}  # Hata durumunda boş bir dict ekle

    # Redis'e kaydet
    redis_key = f"jobPostMatch:{results['id']}"
    redis_client.set(redis_key, json.dumps(results, ensure_ascii=False))

    return jsonify(results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8181)
