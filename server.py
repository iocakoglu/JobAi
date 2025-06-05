from flask import Flask, request, jsonify
import redis
import json
from jobsearch import JobSearchSystem

app = Flask(__name__)

# Redis bağlantısı (default localhost:6379)
redis_url = "redis://:5iAruK60df4d@redis:6379"
redis_client = redis.from_url(redis_url, decode_responses=True)

# JobSearchSystem örneği
jss = JobSearchSystem()

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
    
    # Redis'e kaydet
    candidate_id = candidate_data.get("id", "unknown")
    redis_key = f"candidate_search_results:{candidate_id}"
    redis_client.set(redis_key, json.dumps(results, ensure_ascii=False))
    
    return jsonify(results)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8181)
