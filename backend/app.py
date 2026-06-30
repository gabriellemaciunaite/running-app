import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from google import genai

from extensions import db
from models import User, RunningPlan, WorkoutDay, Exercise, OpenAIPlanSchema

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

with app.app_context():
    db.create_all()

gemini_client = genai.Client()

@login_manager.user_loader
def load_user(user_id):
    return db.session.execute(db.select(User).filter_by(id=int(user_id))).scalar_one_or_none()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password or not email:
            return "Username, password, and email are required", 400
        existing_user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
        existing_user2 = db.session.execute(db.select(User).filter_by(email=email)).scalar_one_or_none()
        if existing_user or existing_user2:
            return "Username or email already exists", 400
        new_user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user:
        logout_user()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        return "Invalid username or password", 401
    return render_template("login.html")

@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    if not current_user.customized:
        return redirect(url_for("customize"))
    return render_template("dashboard.html")

@app.route("/logout")
@login_required
def logout():
    logout_user() 
    return redirect(url_for("login"))

@app.route('/')
def home():
    return render_template("test_form.html")

@app.route('/customize', methods=['POST', 'GET'])
@login_required
def customize():
    if request.method == 'GET':
        return render_template("customize.html")
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing form data"}), 400
    try:
        fields_to_update = {
            'fitness_level': str,
            'target_goal': str,
            'weekly_days': str,
            'age': int,
            'weight': float,
            'height': float,
        }
        for field, cast_func in fields_to_update.items():
            if field in data:
                val = data[field]
                if cast_func in (int, float):
                    setattr(current_user, field, cast_func(val) if val else None)
                else:
                    setattr(current_user, field, val)
        current_user.customized = True
        db.session.commit()
        return jsonify({"status": "success", "message": "Profile updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/generate_workout', methods=['POST'])
@login_required
def generate_workout():
    instruction = (
        "You are a professional personal trainer. Generate a tailored training plan for a runner.",
        f"User age: {current_user.age}, weight: {current_user.weight}kg, height: {current_user.height}cm.",
        f"Fitness level: {current_user.fitness_level}. Schedule: {current_user.weekly_days} days per week.",
        f"Primary target goal: {current_user.target_goal}.",
        "Adhere to these parameters when selecting exercises, sets, reps, time, workout type, and day counts.",
        "Remember that this is primarily for a running app. Strength training should have non-zero values for reps and sets. Cardio should have non-zero time."
    )
    try:
        old_plan = db.session.execute(db.select(RunningPlan).filter_by(user_id=current_user.id)).scalar_one_or_none()
        if old_plan:
            db.session.delete(old_plan)
            db.session.flush()
        completion = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Generate my training routine based entirely on my constraints.",
            config={
                "system_instruction": instruction,
                "response_mime_type": "application/json",
                "response_schema": OpenAIPlanSchema
            }
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
                db_exercise = Exercise(name=ex_data.name, sets=ex_data.sets, reps=ex_data.reps, workout_type=ex_data.workout_type, workout_day=db_day, time=ex_data.time)
                db.session.add(db_exercise)
        db.session.commit()
        return jsonify({"status": "success", "plan_id": plan.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/toggle_exercise/<int:exercise_id>', methods=['POST'])
@login_required
def toggle_exercise(exercise_id):
    data = request.get_json()
    if not data or 'completed' not in data:
        return jsonify({"error": "Missing 'completed' state in payload"}), 400
    try:
        exercise = db.session.execute(db.select(Exercise).filter_by(id=exercise_id)).scalar_one_or_none()
        if not exercise:
            return jsonify({"error": "This exercise is not found"}), 404
        if exercise.workout_day.plan.user_id != current_user.id:
            return jsonify({"error": "Unauthorized action"}), 403
        exercise.completed = False if exercise.completed else True
        db.session.commit()
        return jsonify({"status": "success", "exercise_id": exercise_id, "completed": exercise.completed}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    

if __name__ == '__main__':
    app.run(debug=True, port=5000)