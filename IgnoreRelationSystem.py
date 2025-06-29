import time
import redis
import os
class IgnoreRelationSystemRedisOptimized:
    def __init__(self):
        self.IGNORE_TYPES = {
            'SEEKER_TO_JOB': 0,
            'JOB_TO_SEEKER': 1,
            'BOTH_WAYS': 3
        }

        redis_host = os.getenv('REDIS_HOST', 'redis')  # default 'redis' Docker container adı
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', '5iAruK60df4d')

        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=3,
            password=redis_password,
            decode_responses=True
        )

    def _relation_key(self, seeker_id, job_id):
        return f"ignore:relation:{seeker_id}:{job_id}"

    def _seeker_index_key(self, seeker_id):
        return f"ignore:seeker:{seeker_id}"

    def _job_index_key(self, job_id):
        return f"ignore:job:{job_id}"

    def add_ignore_relation(self, seeker_id: int, job_id: int, is_seeker_initiated: bool):
        current_time = int(time.time())
        new_direction = self.IGNORE_TYPES['SEEKER_TO_JOB'] if is_seeker_initiated else self.IGNORE_TYPES[
            'JOB_TO_SEEKER']

        key = self._relation_key(seeker_id, job_id)
        existing = self.redis.hgetall(key)

        if existing:
            current_dir = int(existing.get('direction', -1))
            created_at = int(existing.get('created_at', current_time))

            if current_dir == self.IGNORE_TYPES['BOTH_WAYS']:
                return False  # Zaten çift yönlü

            if current_dir == new_direction:
                return False  # Aynı yön zaten kayıtlı

            # Çift yönlü yap
            self.redis.hmset(key, {
                'direction': self.IGNORE_TYPES['BOTH_WAYS'],
                'created_at': created_at,
                'updated_at': current_time
            })

            # NOT: Yön çift oldu diye iki tarafı da indexleme!
            if current_dir == self.IGNORE_TYPES['SEEKER_TO_JOB']:
                self.redis.sadd(self._job_index_key(job_id), seeker_id)
            elif current_dir == self.IGNORE_TYPES['JOB_TO_SEEKER']:
                self.redis.sadd(self._seeker_index_key(seeker_id), job_id)

        else:
            # Yeni kayıt
            self.redis.hmset(key, {
                'direction': new_direction,
                'created_at': current_time,
                'updated_at': current_time
            })

            if is_seeker_initiated:
                self.redis.sadd(self._seeker_index_key(seeker_id), job_id)
            else:
                self.redis.sadd(self._job_index_key(job_id), seeker_id)

        return True

    def get_ignored_jobs_for_seeker(self, seeker_id: int) -> list:
        job_ids = self.redis.smembers(self._seeker_index_key(seeker_id))
        return list(map(int, job_ids))

    def get_ignored_seekers_for_job(self, job_id: int) -> list:
        seeker_ids = self.redis.smembers(self._job_index_key(job_id))
        return list(map(int, seeker_ids))
