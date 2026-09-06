from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from backend.extensions import db, redis_client
from datetime import datetime, timezone


main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def home():
    """Takes the user to the homepage.

    Returns:
        Response: returns the entry.html template.
    """
    return render_template("entry.html")

@main_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    """Takes an authenticated user to their dashboard.

    Returns:
        Response: if the user has already set their personal details, return the dashboard.html
        template, otherwise redirect to the customize page.

    """
    if not current_user.customized:
        return redirect(url_for("main.customize"))
    current_user.update_login_streak()
    return render_template("dashboard.html")

@main_bp.route("/customize", methods=["GET", "POST"])
@login_required
def customize():
    """Displays the customize.html template or updates the user's User record with their updated 
    fields.

    Returns:
        JSON Object: if successful return a success message with error code 200, otherwise return
        an error message with error code 500.
    """
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
                val = val.strip() if val else None
                setattr(current_user, field, cast_func(val) if val else None)
        current_user.customized = True
        db.session.commit()
        return jsonify({"success": "Profile updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to save your changes: {str(e)}"}), 500

@main_bp.route("/get-rank/<int:user_id>")
def get_global_distance_rank(user_id):
    """Returns the specified user's global weekly km rank, weekly km, the total amount of
    runners, and their percentile for this week. 

    Returns:
        JSON Object: returns an object containing key-value pairs (their rank, weekly_km, and
        top_percentile) alongside an error code 200.
    """
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    redis_key = f"leaderboard:distance:{year}-W{week}"

    # Pipeline calls to fetch rank, score, and total count
    pipe = redis_client.pipeline()
    pipe.zrevrank(redis_key, str(user_id))
    pipe.zscore(redis_key, str(user_id))
    pipe.zcard(redis_key)
    raw_rank, score, total_runners = pipe.execute()
    # User hasn't logged any runs this week
    if raw_rank is None:
        return jsonify({"rank": None, "weekly_km": 0.0, "top_percentile": None,}), 200
    rank = raw_rank + 1
    if total_runners:
        percentile = round((rank / total_runners) * 100, 2)
    else:
        percentile = 100.0
    return jsonify({"rank": rank, "weekly_km": round(float(score), 2), "top_percentile": percentile,}), 200