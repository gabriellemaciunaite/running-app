from datetime import datetime, timezone
from backend.extensions import redis_client

def add_run_distance_to_redis(user_id: int, distance_meters: float, start_time_ms: int):
    run_date = datetime.fromtimestamp(start_time_ms / 1000.0, tz=timezone.utc)
    year, week, _ = run_date.isocalendar()
    redis_key = f"leaderboard:distance:{year}-W{week}"
    distance_km = distance_meters / 1000.0
    redis_client.zincrby(redis_key, distance_km, str(user_id))
    redis_client.expire(redis_key, 14 * 86400)