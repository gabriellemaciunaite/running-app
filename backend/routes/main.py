from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from backend.extensions import db

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def home():
    return render_template("entry.html")

@main_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    if not current_user.customized:
        return redirect(url_for("main.customize"))
    current_user.update_login_streak()
    return render_template("dashboard.html")

@main_bp.route("/customize", methods=["GET", "POST"])
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