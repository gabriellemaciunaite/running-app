import os 
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    FERNET_KEY = os.getenv("FERNET_ENCRYPTION_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

    CELERY = {
        "broker_url": CELERY_BROKER_URL,
        "result_backend": CELERY_RESULT_BACKEND,
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "timezone": "UTC",
        "enable_utc": True,
        "imports": ("tasks",),
        "beat_schedule": {
            "sync-google-fit": {
                "task": "tasks.sync_all_users_google_fit",
                "schedule": crontab(minute=0, hour="*/4"),
            }
        },
    }