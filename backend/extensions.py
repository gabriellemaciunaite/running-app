import os
import redis
from celery import Celery
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
from google import genai
from backend.config import Config
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
oauth = OAuth()
redis_client = redis.Redis.from_url(Config.REDIS_URL, decode_responses=True)
celery = Celery("running_app")
fernet = Fernet(Config.FERNET_KEY) if Config.FERNET_KEY else None
gemini_client = genai.Client()