from flask import Flask, request, jsonify

from IgnoreRelationSystem import IgnoreRelationSystemRedisOptimized
from jobsearch import JobSearchSystem
from jobseeker import JobSeekerSearchSystem
import time
import json
app = Flask(__name__)

# Sistem örnekleri
jss = JobSearchSystem()
jseeker = JobSeekerSearchSystem()
ignore_system = IgnoreRelationSystemRedisOptimized()



# Güncellenmiş Eşleşme Endpoint'leri
@app.route("/matches/job_posts/<int:job_post_id>", methods=["GET"])
def get_job_post_matches(job_post_id):
    job_post = jss.get_job_by_id(job_post_id)
    if not job_post:
        return jsonify({"error": "JobPost not found"}), 404

    # Sadece job_post'un ignore ettiği seekerları al
    ignored_seekers_for_job = set(ignore_system.get_ignored_seekers_for_job(job_post_id))

    search_results = jseeker.search_jobs({
        "skills": job_post.get("skills", []),
        "latitude": job_post.get("latitude"),
        "longitude": job_post.get("longitude"),
        "id": job_post_id
    })

    matches = []
    for match in search_results.get("results", []):
        seeker_id = match["job_id"]  # Burada job_id seeker_id

        # Eğer job_post bu seeker'ı ignore etmişse atla
        if seeker_id in ignored_seekers_for_job:
            continue

        matches.append({
            "job_seeker_id": seeker_id,
            "score": match["score"],
            "milvus_score": match.get("milvus_score", 0),
            "radius_km": match.get("radius", 0),
            "userId": match.get("userId"),
            "is_ignored": match.get("is_ignored")
        })

    sorted_matches = sorted(matches, key=lambda x: x["score"], reverse=True)

    return jsonify({
        "job_post_id": job_post_id,
        "matches": sorted_matches
    })


@app.route("/matches/job_seekers/<int:seeker_id>", methods=["GET"])
def get_job_seeker_matches(seeker_id):
    seeker = jseeker.get_seeker_by_id(seeker_id)
    if not seeker:
        return jsonify({"error": "JobSeeker not found"}), 404

    # Sadece seeker'ın ignore ettiği jobları al
    ignored_jobs_for_seeker = set(ignore_system.get_ignored_jobs_for_seeker(seeker_id))

    search_results = jss.search_jobs({
        "skills": seeker.get("skills", []),
        "latitude": seeker.get("latitude"),
        "longitude": seeker.get("longitude"),
        "id": seeker_id,
        "is_ignored": seeker.get("is_ignored")
    })

    matches = []
    for match in search_results.get("results", []):
        job_id = match["job_id"]

        # Eğer seeker bu job'u ignore etmişse atla
        if job_id in ignored_jobs_for_seeker:
            continue

        matches.append({
            "job_post_id": job_id,
            "score": match["score"],
            "milvus_score": match.get("milvus_score", 0),
            "radius_km": match.get("radius", 0),
            "userId": match.get("userId"),
            "is_ignored": match.get("is_ignored")
        })

    sorted_matches = sorted(matches, key=lambda x: x["score"], reverse=True)

    return jsonify({
        "job_seeker_id": seeker_id,
        "matches": sorted_matches
    })



# Diğer endpoint'ler

@app.route("/delete/job_seeker/<int:seeker_id>", methods=["POST"])
def delete_job_seeker(seeker_id):
    try:
        res = jseeker.collection.query(
            filter=f"id == {seeker_id}",
            output_fields=["id"]
        )

        if not res:
            return jsonify({"success": False, "message": "Job seeker not found"}), 404

        seeker_id_to_delete = res[0]["id"]
        jseeker.collection.delete([seeker_id_to_delete])
        jseeker.collection.flush()

        return jsonify({
            "success": True,
            "message": "Job seeker deleted",
            "seeker_id": seeker_id
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error deleting job seeker: {str(e)}",
            "seeker_id": seeker_id
        }), 500


@app.route("/delete/job_posts/<int:job_post_id>", methods=["POST"])
def delete_job_post(job_post_id):
    try:
        res = jss.collection.query(
            filter=f"id == {job_post_id}",
            output_fields=["id"]
        )

        if not res:
            return jsonify({"success": False, "message": "Job post not found"}), 404

        job_post_id_to_delete = res[0]["id"]
        jss.collection.delete([job_post_id_to_delete])
        jss.collection.flush()

        return jsonify({
            "success": True,
            "message": "Job post deleted",
            "job_post_id": job_post_id
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error deleting job post: {str(e)}",
            "job_post_id": job_post_id
        }), 500


@app.route('/ignore', methods=['POST'])
def add_ignore():
    data = request.json
    seeker_id = data.get('seeker_id')
    job_id = data.get('job_id')
    is_seeker_initiated = data.get('is_seeker_initiated', True)

    if seeker_id is None or job_id is None:
        return jsonify({"error": "seeker_id and job_id are required"}), 400

    try:
        seeker_id = int(seeker_id)
        job_id = int(job_id)
    except ValueError:
        return jsonify({"error": "seeker_id and job_id must be integers"}), 400

    updated = ignore_system.add_ignore_relation(seeker_id, job_id, is_seeker_initiated)
    return jsonify({"success": updated})


@app.route('/seeker/<int:seeker_id>/ignored-jobs', methods=['GET'])
def get_jobs_for_seeker(seeker_id):
    jobs = ignore_system.get_ignored_jobs_for_seeker(seeker_id)
    return jsonify({"seeker_id": seeker_id, "ignored_jobs": jobs})


@app.route('/job/<int:job_id>/ignored-seekers', methods=['GET'])
def get_seekers_for_job(job_id):
    seekers = ignore_system.get_ignored_seekers_for_job(job_id)
    return jsonify({"job_id": job_id, "ignored_seekers": seekers})



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