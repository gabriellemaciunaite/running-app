from celery import shared_task
import requests
from datetime import datetime

# Import models, db, app, and helper functions
from backend.models import User, Run, Friendship
from backend.extensions import db, fernet
from backend.services.redis_service import add_run_distance_to_redis
from backend.utils import run_stats, check_update, refresh_google_token
from backend import create_app
from backend.routes.google import sync_user_runs

app = create_app()

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_google_fit_data(self, user_id):
    """Syncs a user's runs via Google Fit if they are connected and returns their user id along
    with the number of their runs, otherwise return a invalid status along with their user id.

    """
    with app.app_context():
        try:
            user = db.session.execute(
                db.select(User).filter_by(id=user_id)
            ).scalar_one_or_none()
            if not user or not user.google_connected:
                return {"status": "invalid", "user_id": user_id, "reason": "User not connected"}
            runs = sync_user_runs(user)
            return {"status": "success", "user_id": user_id, "synced_runs": len(runs)}
        except Exception as e:
            db.session.rollback()
            raise self.retry(e=e)
        finally:
            db.session.remove()


@shared_task
def sync_all_users_google_fit():
    """Runs via Celery workers, updating every user in the database's runs every given period
    of time.

    """
    with app.app_context():
        try:
            connected_users = (
                db.session.execute(db.select(User).filter_by(google_connected=True))
                .scalars()
                .all()
            )
            for user in connected_users:
                sync_google_fit_data.delay(user.id)
        finally:
            db.session.remove()
    
