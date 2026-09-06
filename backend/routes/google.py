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
    """Allows a user to connect their Google Fit account by taking them to the OAuth 2.0 link,
    which after redirects to google_callback().

    Returns:
        Response: After authorizing via OAuth, the user is redirected to google_callback upon success.

    """
    redirect_uri = url_for("google.google_callback", _external=True)
    return oauth.google.authorize_redirect(
        redirect_uri, access_type="offline", prompt="consent"
    )

@google_bp.route("/google-callback")
@login_required
def google_callback():
    """Encrypts the plaintext OAuth token pair and stores them in the database.
    
    Upon redirection, the user's access and refresh token are encrypted via Fernet and stored in
    the database alongside their expiration time. Upon success, the user is redirected to their
    dashboard, otherwise, the database is rolled back and an error message with error code 500 is
    printed to the console. 

    Returns:
        Response: if successful, return the user to main.dashboard.
        JSON object: if an error occurs, return error code 500 and append the error message.

    """
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
        return jsonify({"error": f"Failed to retrieve OAuth token pair: {str(e)}"}), 500

@google_bp.route("/fetch-runs")
@login_required
def fetch_runs():
    """Fetch the user's running statistics from Google Fit via sync_user_runs and return
    a JSON object containing the total number of runs and the data associated with each
    run (name, description, calories burned, distance, steps, and more).

    Returns:
        List: if successful, return a success response containing each run object and the
        total amount with error code 200, otherwise return an error response with a 500 error code.

    """
    if not current_user.google_connected or not current_user.google_access_token:
        return redirect(url_for("google.connect_google"))
    try:
        runs = sync_user_runs(current_user)
        return jsonify({"total_runs": len(runs), "runs": [r.to_dict() for r in runs]}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to sync runs: {str(e)}"}), 500

def sync_user_runs(user):
    """Updates the user's run statistics in the database.

    Fetches running sessions from the Google Fit REST API by decrypting the specified user's
    OAuth token pair, filtering by running activities, inserting new Run records, and returning
    a list of Run objects that are specific to the user.

    Returns:
        List: if successful, return a list of Run objects.
        JSON object: if an error occurs, return an appropriate error message with error code 500.

    """
    if not user or not user.google_connected or not user.google_access_token:
        return []
    try:
        decrypted_token = fernet.decrypt(user.google_access_token.encode()).decode()
    except Exception as e:
        return jsonify({"error": f"Failed to decrypt access token: {str(e)}"}), 500
    url = "https://www.googleapis.com/fitness/v1/users/me/sessions"
    headers = {"Authorization": f"Bearer {decrypted_token}"}
    response = requests.get(url, headers=headers, timeout=10)
    # Update refresh token on 401 error code
    if response.status_code == 401:
        new_token = refresh_google_token(user, db)
        if not new_token:
            return jsonify({"error": f"Failed to refresh token"}), 500
        headers = {"Authorization": f"Bearer {new_token}"}
        response = requests.get(url, headers=headers, timeout=10)
    if not response.ok:
        return jsonify({"error": f"Error occurred when retrieving Google Fit data: {str(e)}"}), 500

    # Process sessions
    sessions = response.json().get("session", [])
    processed_runs = []
    # Only stores sessions that have an activity type that relate to running
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
            db.select(Run).where(Run.google_session_id == session_id, Run.user_id == user.id)
        ).scalars().first()
        # New run - does not exist inside the database
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
            processed_runs.append(run_obj)
            if distance_meters > 0:
                add_run_distance_to_redis(user.id, distance_meters, start_ms)
        # Run already exists within the db
        else:
            processed_runs.append(existing_run)
    db.session.commit()
    return processed_runs