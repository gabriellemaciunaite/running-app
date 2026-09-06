import requests
from flask import Blueprint, jsonify, redirect, url_for
from flask_login import login_required, current_user
from backend.extensions import db, oauth, fernet
from backend.services.redis_service import add_run_distance_to_redis
from backend.models import Run
from backend.utils import refresh_google_token, check_update, run_stats

google_bp = Blueprint("google", __name__)

@google_bp.route("/connect-google")
@login_required
def connect_google():
    redirect_uri = url_for("google.google_callback", _external=True)
    return oauth.google.authorize_redirect(
        redirect_uri, access_type="offline", prompt="consent"
    )

@google_bp.route("/google-callback")
@login_required
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        current_user.google_connected = True
        current_user.google_access_token = fernet.encrypt(token.get("access_token").encode()).decode()
        if token.get("refresh_token"):
            current_user.google_refresh_token = fernet.encrypt(token.get("refresh_token").encode()).decode()
        if token.get("expires_at"):
            current_user.google_token_expires_at = token.get("expires_at")
        db.session.commit()
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@google_bp.route("/fetch-runs")
@login_required
def fetch_runs():
    if not current_user.google_connected or not current_user.google_access_token:
        return redirect(url_for("google.connect_google"))
    try:
        runs = sync_user_runs(current_user)
        return jsonify({"total_runs": len(runs), "runs": runs}), 200
    except (ValueError, PermissionError):
        # Fernet decode failure or expired/revoked refresh token
        return redirect(url_for("google.connect_google"))
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to sync runs: {str(e)}"}), 502

def sync_user_runs(user):
    if not user or not user.google_connected or not user.google_access_token:
        return []
    try:
        decrypted_token = fernet.decrypt(user.google_access_token.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Token decryption failed: {exc}")

    url = "https://www.googleapis.com/fitness/v1/users/me/sessions"
    headers = {"Authorization": f"Bearer {decrypted_token}"}
    response = requests.get(url, headers=headers, timeout=10)

    # Refresh on 401
    if response.status_code == 401:
        new_token = refresh_google_token(user, db)
        if not new_token:
            raise PermissionError("Failed to refresh Google token; user re-auth required")
        headers = {"Authorization": f"Bearer {new_token}"}
        response = requests.get(url, headers=headers, timeout=10)

    if not response.ok:
        raise RuntimeError(f"Google Fit API error: {response.text}")

    # Process sessions
    sessions = response.json().get("session", [])
    processed_runs = []
    RUNNING_ACTIVITY_IDS = [8, 56, 57, 58]

    for session in sessions:
        if session.get("activityType") not in RUNNING_ACTIVITY_IDS:
            continue
        session_id = session.get("id")
        start_ms = int(session.get("startTimeMillis", 0))
        end_ms = int(session.get("endTimeMillis", 0))
        duration_seconds = (end_ms - start_ms) / 1000.0

        stats = run_stats(start_ms, end_ms, headers)
        distance_meters = stats["distance_meters"]

        check_update(user, distance_meters, duration_seconds)
        existing_run = db.session.execute(
            db.select(Run).where(
                Run.google_session_id == session_id,
                Run.user_id == user.id
            )
        ).scalars().first()

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
                add_run_distance_to_redis(user.id, distance_meters, start_ms)
        else:
            dist_diff = distance_meters - existing_run.distance_meters
            if dist_diff > 0:
                add_run_distance_to_redis(user.id, dist_diff, start_ms)

            existing_run.distance_meters = distance_meters
            existing_run.duration_seconds = duration_seconds
            existing_run.calories_burned = stats["calories_burned"]
            existing_run.steps = stats["steps"]

        processed_runs.append({
            "id": session_id,
            "name": session.get("name", "Untitled Run"),
            "duration_seconds": duration_seconds,
            "distance_meters": distance_meters,
            "distance_km": distance_meters / 1000.0,
            "calories_burned": stats["calories_burned"],
            "steps": stats["steps"],
            "start_time_ms": start_ms,
            "end_time_ms": end_ms,
        })

    db.session.commit()
    return processed_runs