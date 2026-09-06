import os
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from dotenv import load_dotenv
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import check_password_hash, generate_password_hash
from google import genai
from datetime import datetime, timedelta, timezone
from email_validator import validate_email

from extensions import db
from models import (
    User,
    RunningPlan,
    WorkoutDay,
    Exercise,
    GeminiPlanSchema,
    Friendship,
    Run,
)

from authlib.integrations.flask_client import OAuth
from utils import refresh_google_token, check_update, run_stats

import redis
from celery import Celery
from celery.signals import worker_process_init
from celery.schedules import crontab
from flask_wtf.csrf import CSRFProtect
from cryptography.fernet import Fernet


load_dotenv()
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
celery = Celery("running_app", broker=celery_broker_url, backend=celery_result_backend)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
celery.conf.imports = ("tasks",)
celery.conf.beat_schedule = {
    "sync-google-fit-every-minute-test": {
        "task": "tasks.sync_all_users_google_fit",
        "schedule": crontab(minute=0, hour="*/4"),
    },
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

with app.app_context():
    db.create_all()

gemini_client = genai.Client()

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    access_token_url="https://oauth2.googleapis.com/token",
    api_base_url="https://www.googleapis.com/oauth2/v1/",
    jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/fitness.activity.read https://www.googleapis.com/auth/fitness.location.read"
    },
)

@worker_process_init.connect
def reset_db_connection_pool(**kwargs):
    with app.app_context():
        db.engine.dispose()

csrf = CSRFProtect(app)
fernet = Fernet(os.getenv("FERNET_ENCRYPTION_KEY").encode())
@login_manager.user_loader
def load_user(user_id):
    return db.session.execute(
        db.select(User).filter_by(id=int(user_id))
    ).scalar_one_or_none()


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password or not email:
            flash("Username, password, and email are required")
            return redirect(url_for("register"))
        existing_user = db.session.execute(
            db.select(User).where((User.username==username) | (User.email==email))
        ).scalar_one_or_none()
        if existing_user:
            flash("Username or email already exists")
            return redirect(url_for("register"))
        if len(password) < 8 or password.islower() or password.isupper() or password.isalnum():
            flash("Password must be greater than 8 characters long, contain a mix of upper and lowercase characters, and at least one non-alphanumeric character.")
            return(redirect(url_for("register")))
        try:
            validate_email(email)
        except Exception as e:
            flash("Invalid email provided")
            return(redirect(url_for("register")))
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        logout_user()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = db.session.execute(
            db.select(User).filter_by(username=username)
        ).scalar_one_or_none()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid username or password")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    if not current_user.customized:
        return redirect(url_for("customize"))
    current_user.update_login_streak()
    return render_template("dashboard.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
def home():
    return render_template("entry.html")


@app.route("/customize", methods=["POST", "GET"])
@login_required
def customize():
    if request.method == "GET":
        return render_template("customize.html")
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing form data"}), 400
    try:
        fields_to_update = {
            "fitness_level": str,
            "target_goal": str,
            "weekly_days": str,
            "age": int,
            "weight": float,
            "height": float,
        }
        for field, cast_func in fields_to_update.items():
            if field in data:
                val = data[field]
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    setattr(current_user, field, None)
                else:
                    setattr(current_user, field, cast_func(val))
        current_user.customized = True
        db.session.commit()
        return jsonify({"status": "success", "message": "Profile updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/generate_workout", methods=["POST"])
@login_required
def generate_workout():
    instruction = (
        "You are a professional personal trainer. Generate a tailored training plan for a runner.",
        f"User age: {current_user.age}, weight: {current_user.weight}kg, height: {current_user.height}cm.",
        f"Fitness level: {current_user.fitness_level}. Schedule: {current_user.weekly_days} days per week.",
        f"Primary target goal: {current_user.target_goal}.",
        "Adhere to these parameters when selecting exercises, sets, reps, time, workout type, and day counts.",
        "Remember that this is primarily for a running app. Strength training should have non-zero values for reps and sets. Cardio should have non-zero time.",
    )
    try:
        old_plan = db.session.execute(
            db.select(RunningPlan).filter_by(user_id=current_user.id)
        ).scalar_one_or_none()
        if old_plan:
            db.session.delete(old_plan)
            db.session.flush()
        completion = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Generate my training routine based entirely on my constraints.",
            config={
                "system_instruction": instruction,
                "response_mime_type": "application/json",
                "response_schema": GeminiPlanSchema,
            },
        )
        data = completion.parsed
        if not data:
            return jsonify({"error": "failed to parse ai structure"}), 500
        plan = RunningPlan(name=data.name, user=current_user)
        db.session.add(plan)
        for day_data in data.days:
            db_day = WorkoutDay(day_name=day_data.day_name, plan=plan)
            db.session.add(db_day)
            for ex_data in day_data.exercises:
                db_exercise = Exercise(
                    name=ex_data.name,
                    sets=ex_data.sets,
                    reps=ex_data.reps,
                    workout_type=ex_data.workout_type,
                    workout_day=db_day,
                    time=ex_data.time,
                )
                db.session.add(db_exercise)
        db.session.commit()
        return jsonify({"status": "success", "plan_id": plan.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/toggle_exercise/<int:exercise_id>", methods=["POST"])
@login_required
def toggle_exercise(exercise_id):
    data = request.get_json()
    if not data or "completed" not in data:
        return jsonify({"error": "Missing 'completed' state in payload"}), 400
    try:
        exercise = db.session.execute(
            db.select(Exercise).filter_by(id=exercise_id)
        ).scalar_one_or_none()
        if not exercise:
            return jsonify({"error": "This exercise is not found"}), 404
        if exercise.workout_day.plan.user_id != current_user.id:
            return jsonify({"error": "Unauthorized action"}), 403
        exercise.completed = False if exercise.completed else True
        db.session.commit()
        return jsonify(
            {
                "status": "success",
                "exercise_id": exercise_id,
                "completed": exercise.completed,
            }
        ), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route("/connect-google")
@login_required
def connect_google():
    redirect_uri = url_for("google_callback", _external=True)
    return google.authorize_redirect(
        redirect_uri, access_type="offline", prompt="consent"
    )


@app.route("/google-callback")
@login_required
def google_callback():
    try:
        token = google.authorize_access_token()
        current_user.google_connected = True
        current_user.google_access_token = fernet.encrypt(token.get("access_token").encode()).decode()
        if token.get("refresh_token"):
            current_user.google_refresh_token = fernet.encrypt(token.get("refresh_token").encode()).decode()
        if token.get("expires_at"):
            current_user.google_token_expires_at = token.get("expires_at")
        db.session.commit()
        return redirect(url_for("dashboard"))
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/fetch-runs")
@login_required
def fetch_runs():
    if not current_user.google_connected or not current_user.google_access_token:
        return redirect(url_for("connect_google"))
    try:
        decrypted_token = fernet.decrypt(current_user.google_access_token.encode()).decode()
    except Exception:
        return redirect(url_for("connect_google"))
    headers = {"Authorization": f"Bearer {decrypted_token}"}
    url = "https://www.googleapis.com/fitness/v1/users/me/sessions"
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return jsonify({"error": f"Failed to contact Google Fit: {str(e)}"}), 502
    if response.status_code == 401:
        new_token = refresh_google_token(current_user, db)
        if not new_token:
            return redirect(url_for("connect_google"))
        headers = {"Authorization": f"Bearer {new_token}"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except requests.exceptions.RequestException as e:
            return jsonify({"error": f"Failed to contact Google Fit: {str(e)}"}), 502
    if not response.ok:
        return jsonify(
            {"error": f"Failed to fetch runs: {response.text}"}
        ), response.status_code
    data = response.json()
    sessions = data.get("session", [])
    RUNNING_ACTIVITY_IDS = [8, 56, 57, 58]
    runs = []
    try:
        for session in sessions:
            if session.get("activityType") in RUNNING_ACTIVITY_IDS:
                session_id = session.get("id")
                start_ms = int(session.get("startTimeMillis", 0))
                end_ms = int(session.get("endTimeMillis", 0))
                duration_seconds = (end_ms - start_ms) / 1000.0
                stats = run_stats(start_ms, end_ms, headers)
                distance_meters = stats["distance_meters"]
                distance_km = distance_meters / 1000.0
                check_update(current_user, distance_meters, duration_seconds)
                existing_run = db.session.execute(
                    db.select(Run).where(Run.google_session_id==session_id, Run.user_id==current_user.id)
                ).scalar_one_or_none()
                if not existing_run:
                    run_obj = Run(
                        google_session_id=session_id,
                        user_id=current_user.id,
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
                        add_run_distance_to_redis(current_user.id, distance_meters, start_ms)
                else:
                    # If distance changed on an existing run, update Redis with the difference
                    dist_diff_meters = distance_meters - existing_run.distance_meters
                    if dist_diff_meters > 0:
                        add_run_distance_to_redis(current_user.id, dist_diff_meters, start_ms)

                    existing_run.distance_meters = distance_meters
                    existing_run.duration_seconds = duration_seconds
                    existing_run.calories_burned = stats["calories_burned"]
                    existing_run.steps = stats["steps"]

                # Append to response list
                runs.append(
                    {
                        "id": session_id,
                        "name": session.get("name", "Untitled Run"),
                        "description": session.get("description", ""),
                        "duration_seconds": duration_seconds,
                        "distance_meters": distance_meters,
                        "distance_km": distance_km,
                        "calories_burned": stats["calories_burned"],
                        "steps": stats["steps"],
                        "start_time_ms": start_ms,
                        "end_time_ms": end_ms,
                    }
                )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database transaction failed: {str(e)}"}), 500
    return jsonify({"total_runs": len(runs), "runs": runs}), 200


def add_run_distance_to_redis(user_id: int, distance_meters: float, start_time_ms: int):
    run_date = datetime.fromtimestamp(start_time_ms / 1000.0, tz=timezone.utc)
    year, week, _ = run_date.isocalendar()
    redis_key = f"leaderboard:distance:{year}-W{week}"
    distance_km = distance_meters / 1000.0
    redis_client.zincrby(redis_key, distance_km, str(user_id))
    redis_client.expire(redis_key, 14 * 86400)


@app.route("/api/leaderboard-data")
@login_required
def get_leaderboard_data():
    accepted_friendships = db.session.execute(db.select(Friendship).where(
        (Friendship.sender_id == current_user.id) | (Friendship.receiver_id == current_user.id),
        Friendship.status == "accepted")
    ).scalars().all()
    friend_ids = {current_user.id}
    for f in accepted_friendships:
        friend_ids.add(f.receiver_id if f.sender_id == current_user.id else f.sender_id)
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    redis_key = f"leaderboard:distance:{year}-W{week}"
    user_pool = (
        db.session.execute(db.select(User).where(User.id.in_(friend_ids)))
        .scalars()
        .all()
    )
    pipe = redis_client.pipeline()
    for user in user_pool:
        pipe.zscore(redis_key, str(user.id))
    scores = pipe.execute()  # Returns list of scores in matching order
    friends_data = []
    for user, score in zip(user_pool, scores):
        weekly_km = float(score) if score is not None else 0.0
        friends_data.append(
            {
                "id": user.id,
                "username": user.username,
                "streak": user.login_streak or 0,
                "weekly_km": round(weekly_km, 2),
                "is_me": user.id == current_user.id,
                "pr_5k": user.pr_5k or 0.0,
                "pr_10k": user.pr_10k or 0.0,
                "pr_marathon": user.pr_marathon or 0.0,
            }
        )
    friends_data.sort(key=lambda x: x["weekly_km"], reverse=True)
    pending_requests = db.session.execute(db.select(Friendship).where(Friendship.receiver_id==current_user.id, Friendship.status=="pending")).scalars().all()
    incoming_requests_data = [
        {"request_id": req.id, "sender_username": req.sender.username}
        for req in pending_requests
    ]
    return jsonify(
        {"friends": friends_data, "incoming_requests": incoming_requests_data}
    ), 200


@app.route("/api/friends/request", methods=["POST"])
@login_required
def send_friend_request():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    target_user = db.session.execute(db.select(User).where(User.username==username)).scalar_one_or_none()
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    if target_user == current_user:
        return jsonify({"error": "You cannot add yourself"}), 400
    existing = db.session.execute(db.select(Friendship).where(
        ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == target_user.id))
        | ((Friendship.sender_id == target_user.id) & (Friendship.receiver_id == current_user.id))
    )).scalar_one_or_none()
    if existing:
        if existing.status == "accepted":
            return jsonify({"error": "You are already friends with this user"}), 400
        return jsonify({"error": "A pending friend request already exists"}), 400
    new_req = Friendship(
        sender_id=current_user.id, receiver_id=target_user.id, status="pending"
    )
    db.session.add(new_req)
    db.session.commit()
    return jsonify({"message": f"Friend request sent to {target_user.username}"}), 200


@app.route("/api/friends/respond/<int:request_id>", methods=["POST"])
@login_required
def respond_friend_request(request_id):
    data = request.get_json()
    action = data.get("action")
    friend_req = db.session.execute(db.select(Friendship).where(Friendship.id==request_id, Friendship.receiver_id==current_user.id)).scalar_one_or_none()
    if friend_req is None:
        return jsonify({"error": "Friend request not found"}), 404
    if action == "accept":
        friend_req.status = "accepted"
    elif action == "decline":
        db.session.delete(friend_req)
    else:
        return jsonify({"error": "Invalid action. Must be 'accept' or 'decline'"}), 400
    db.session.commit()
    return jsonify({"message": f"Request {action}ed successfully"}), 200


@app.route("/api/friends/remove/<int:friend_id>", methods=["DELETE"])
@login_required
def remove_friend(friend_id):
    friendship = db.session.execute(
        db.select(Friendship).where(
            (
                (Friendship.sender_id == current_user.id)
                & (Friendship.receiver_id == friend_id)
            )
            | (
                (Friendship.sender_id == friend_id)
                & (Friendship.receiver_id == current_user.id)
            )
        )
    ).scalar_one_or_none()
    if friendship is None:
        return jsonify({"error": "Friendship record not found"}), 404
    db.session.delete(friendship)
    db.session.commit()
    return jsonify({"message": "Friend removed"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
