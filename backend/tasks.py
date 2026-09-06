from celery import shared_task
import requests
from datetime import datetime

# Import models, db, app, and helper functions
from models import db, User, Run, Friendship
from app import app, add_run_distance_to_redis
from utils import run_stats, check_update, refresh_google_token


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_google_fit_data(self, user_id):
    from app import app  # Avoids circular import
    with app.app_context():
        try:
            user = db.session.execute(
                db.select(User).filter_by(id=user_id)
            ).scalar_one_or_none()
            if not user or not user.google_connected or not user.google_access_token:
                return {"status": "skipped", "reason": "User not connected"}

            url = "https://www.googleapis.com/fitness/v1/users/me/sessions"
            headers = {"Authorization": f"Bearer {user.google_access_token}"}

            response = requests.get(url, headers=headers)

            # Handle 401 Unauthorized token refresh cleanly
            if response.status_code == 401:
                new_token = refresh_google_token(user, db)
                if new_token:
                    headers = {"Authorization": f"Bearer {new_token}"}
                    response = requests.get(url, headers=headers)

            if not response.ok:
                raise Exception(f"Google Fit API Error: {response.text}")

            data = response.json()
            sessions = data.get("session", [])
            RUNNING_ACTIVITY_IDS = [8, 56, 57, 58]
            total_distance_delta = 0.0
            for session in sessions:
                if session.get("activityType") in RUNNING_ACTIVITY_IDS:
                    session_id = session.get("id")
                    start_ms = int(session.get("startTimeMillis", 0))
                    end_ms = int(session.get("endTimeMillis", 0))
                    duration_seconds = (end_ms - start_ms) / 1000.0

                    # Fetch run metrics
                    stats = run_stats(start_ms, end_ms, headers)
                    distance_meters = stats["distance_meters"]

                    # Update PRs
                    check_update(user, distance_meters, duration_seconds)

                    # Insert or Update Run record
                    existing_run = db.session.execute(
                        db.select(Run).filter_by(google_session_id=session_id)
                    ).scalar_one_or_none()
                    if not existing_run:
                        run_obj = Run(
                            google_session_id=session_id,
                            user_id=user.id,
                            name=session.get("name", "Untitled Run"),
                            description=session.get("description", ""),
                            distance_meters=distance_meters,
                            duration_seconds=duration_seconds,
                            calories_burned=stats["calories_burned"],
                            steps=stats["steps"],
                            start_time_ms=start_ms,
                            end_time_ms=end_ms,
                        )
                        db.session.add(run_obj)

                        if distance_meters > 0:
                            add_run_distance_to_redis(user_id, distance_meters, start_ms)
                    else:
                        # Calculate distance difference and update Redis if changed
                        dist_diff_meters = (
                            distance_meters - existing_run.distance_meters
                        )
                        if dist_diff_meters > 0:
                            add_run_distance_to_redis(user_id, dist_diff_meters, start_ms)

                        existing_run.distance_meters = distance_meters
                        existing_run.duration_seconds = duration_seconds
                        existing_run.calories_burned = stats["calories_burned"]
                        existing_run.steps = stats["steps"]
            db.session.commit()
            return {"status": "success", "user_id": user_id}
        except Exception as exc:
            db.session.rollback()
            # Retry the task via Celery
            raise self.retry(exc=exc)


@shared_task
def sync_all_users_google_fit():
    with app.app_context():
        connected_users = (
            db.session.execute(db.select(User).filter_by(google_connected=True))
            .scalars()
            .all()
        )
        for user in connected_users:
            sync_google_fit_data.delay(user.id)
