from flask import Flask
from celery.signals import worker_process_init
from backend.config import Config
from backend.extensions import db, login_manager, csrf, oauth, celery
from backend.models import User

# Signal handler registered at module level
@worker_process_init.connect
def reset_db_connection_pool(**kwargs):
    app = create_app()
    with app.app_context():
        db.engine.dispose()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Configure Celery directly using the CELERY dict from config
    celery_config = app.config.get("CELERY", {})
    if celery_config:
        celery.conf.update(celery_config)
    else:
        # Fallback if flat config keys are used
        celery.conf.update(
            broker_url=app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/1"),
            result_backend=app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            beat_schedule=app.config.get("CELERY_BEAT_SCHEDULE", {}),
            imports=("tasks",),
        )

    # Configure OAuth
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        access_token_url="https://oauth2.googleapis.com/token",
        api_base_url="https://www.googleapis.com/oauth2/v1/",
        jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
        client_kwargs={
            "scope": "openid email profile https://www.googleapis.com/auth/fitness.activity.read https://www.googleapis.com/auth/fitness.location.read"
        },
    )

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.execute(db.select(User).filter_by(id=int(user_id))).scalar_one_or_none()

    # Register Blueprints
    from backend.routes.auth import auth_bp
    from backend.routes.main import main_bp
    from backend.routes.workouts import workouts_bp
    from backend.routes.google import google_bp
    from backend.routes.friends import friends_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(workouts_bp)
    app.register_blueprint(google_bp)
    app.register_blueprint(friends_bp)

    return app