from flask import Flask, request, jsonify
import redis
import json
from jobsearch import JobSearchSystem
from jobseeker import JobSeekerSearchSystem
import os

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
    print(results)
    # Redis'e kaydet
    redis_key = f"jobSeekerMatch:{results['id']}"
    redis_client.set(redis_key, json.dumps(results, ensure_ascii=False))
    
    return jsonify(results)



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
    
    results = jseeker.search_jobs(candidate_data)
    print(results)
    # Redis'e kaydet
    redis_key = f"jobPostMatch:{results['id']}"
    redis_client.set(redis_key, json.dumps(results, ensure_ascii=False))
    
    return jsonify(results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8181)
