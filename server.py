from flask import Flask, request, jsonify
from jobsearch import JobSearchSystem
from jobseeker import JobSeekerSearchSystem
import time
import json
app = Flask(__name__)

# Sistem örnekleri
jss = JobSearchSystem()
jseeker = JobSeekerSearchSystem()


# Güncellenmiş Eşleşme Endpoint'leri
@app.route("/matches/job_posts/<int:job_post_id>", methods=["GET"])
def get_job_post_matches(job_post_id):
    # 1. İş ilanını veritabanından al
    job_post = jss.get_job_by_id(job_post_id)
    if not job_post:
        return jsonify({"error": "JobPost not found"}), 404

    print("Job Post Details:", job_post)

    # 2. Aday araması yap
    search_results = jseeker.search_jobs({
        "skills": job_post.get("skills", []),
        "latitude": job_post.get("latitude"),
        "longitude": job_post.get("longitude"),
        "id": job_post_id
    })

    print("Raw Search Results:", search_results)

    # 3. Eşleşmeleri işle
    matches = []
    for match in search_results.get("results", []):
        # Orijinal yapıyı koruyarak eşleşme verisini oluştur
        match_data = {
            "job_seeker_id": match["job_id"],
            "score": match["score"],
            "milvus_score": match.get("milvus_score", 0),
            "radius_km": match.get("radius", 0),
            "userId": match.get("userId"),
            "is_ignored": match.get("is_ignored")
        }
        matches.append(match_data)

        # Eşleşmeyi veritabanına kaydet (orijinal parametrelerle)


    # 4. Sonuçları skora göre sırala
    sorted_matches = sorted(matches, key=lambda x: x["score"], reverse=True)

    # 5. Orijinal çıktı formatını koruyarak sonucu döndür
    return jsonify({
        "job_post_id": job_post_id,
        "matches": sorted_matches
    })

@app.route("/matches/job_seekers/<int:seeker_id>", methods=["GET"])
def get_job_seeker_matches(seeker_id):
    seeker = jseeker.get_seeker_by_id(seeker_id)
    if not seeker:
        return jsonify({"error": "JobSeeker not found"}), 404

    search_results = jss.search_jobs({
        "skills": seeker.get("skills", []),
        "latitude": seeker.get("latitude"),
        "longitude": seeker.get("longitude"),
        "id": seeker_id,  # Job seeker ID'sini de geçiyoruz
        "is_ignored": seeker.get("is_ignored")
    })

    print("Raw Search Results:", search_results)

    # 3. Eşleşmeleri işle
    matches = []
    for match in search_results.get("results", []):
        # Orijinal yapıyı koruyarak eşleşme verisini oluştur
        match_data = {
            "job_post_id": match["job_id"],
            "score": match["score"],
            "milvus_score": match.get("milvus_score", 0),
            "radius_km": match.get("radius", 0),
            "userId": match.get("userId"),
            "is_ignored": match.get("is_ignored")
        }
        matches.append(match_data)

        # Eşleşmeyi veritabanına kaydet (orijinal parametrelerle)

    # 4. Sonuçları skora göre sırala
    sorted_matches = sorted(matches, key=lambda x: x["score"], reverse=True)

    # 5. Orijinal çıktı formatını koruyarak sonucu döndür
    return jsonify({
        "job_seeker_id": seeker_id,
        "matches": sorted_matches
    })


# Diğer endpoint'ler

@app.route("/ignore/job_seeker/<int:seeker_id>", methods=["POST"])
def ignore_specific(seeker_id):
    try:
        # 1. İş arayanı bul
        res = jseeker.collection.query(
            expr=f"id == {seeker_id}",
            output_fields=["id", "embedding", "job_data", "is_deleted"]
        )

        if not res:
            return jsonify({"success": False, "message": "Job seeker not found"}), 404

        data = res[0]

        # 2. job_data'yı parse et
        job_data_raw = data["job_data"]
        job_data = json.loads(job_data_raw) if isinstance(job_data_raw, str) else job_data_raw

        # 3. is_ignored'ı True yap
        job_data["is_ignored"] = True

        # 4. Eski veriyi sil
        jseeker.collection.delete(expr=f"id in [{seeker_id}]")

        # 5. Yeni veriyi insert et
        jseeker.collection.insert([
            [data["id"]],
            [data["embedding"]],
            [json.dumps(job_data)],
            [data.get("is_deleted", False)]
        ])

        jseeker.collection.flush()

        return jsonify({"success": True, "message": "Job seeker marked as ignored"})

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error ignoring match: {str(e)}"
        }), 500

@app.route("/ignore/job_posts/<int:job_post_id>", methods=["POST"])
def ignore_specific_match(job_post_id):
    try:
        # 1. İş arayanı bul
        res = jss.collection.query(
            expr=f"id == {job_post_id}",
            output_fields=["id", "embedding", "job_data", "is_deleted"]
        )

        if not res:
            return jsonify({"success": False, "message": "Job seeker not found"}), 404

        data = res[0]

        # 2. job_data'yı parse et
        job_data_raw = data["job_data"]
        job_data = json.loads(job_data_raw) if isinstance(job_data_raw, str) else job_data_raw

        # 3. is_ignored'ı True yap
        job_data["is_ignored"] = True

        # 4. Eski veriyi sil
        jss.collection.delete(expr=f"id in [{job_post_id}]")

        # 5. Yeni veriyi insert et
        jss.collection.insert([
            [data["id"]],
            [data["embedding"]],
            [json.dumps(job_data)],
            [data.get("is_deleted", False)]
        ])

        jss.collection.flush()

        return jsonify({"success": True, "message": "Job seeker marked as ignored"})

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error ignoring match: {str(e)}"
        }), 500



@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/job_posts", methods=["POST"])
def add_job_posts():
    jobs = request.json
    if not jobs:
        return jsonify({"success": False, "message": "Job posts data missing"}), 400
    return jsonify({"success": jss.add_jobs(jobs)})

@app.route("/job_seekers", methods=["POST"])
def add_job_seekers():
    seekers = request.json
    if not seekers:
        return jsonify({"success": False, "message": "Seekers data missing"}), 400
    return jsonify({"success": jseeker.add_jobs(seekers)})



# Admin Endpoint'leri
@app.route("/admin/job_posts/reset", methods=["POST"])
def reset_job_posts():
    jss.safe_reset_collection()
    return jsonify({"success": True})

@app.route("/admin/job_seekers/reset", methods=["POST"])
def reset_job_seekers():
    jseeker.safe_reset_collection()
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8181)