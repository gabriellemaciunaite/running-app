import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User

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
        return render_template("customize.html")
    return render_template("dashboard.html")

@app.route("/logout")
@login_required
def logout():
    logout_user() 
    return redirect(url_for("login"))

@app.route('/')
def home():
    return render_template("test_form.html")

@app.route('/customize', methods=['POST'])
@login_required
def customize():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing form data"}), 400
    try:
        # --- Training Preferences ---
        if 'fitness_level' in data:
            current_user.fitness_level = data['fitness_level']
        if 'target_goal' in data:
            current_user.target_goal = data['target_goal']
        if 'weekly_days' in data:
            current_user.weekly_days = data['weekly_days']

        # --- Personal Details ---
        if 'age' in data:
            current_user.age = int(data['age']) if data['age'] else None
        if 'weight' in data:
            current_user.weight = float(data['weight']) if data['weight'] else None
        if 'height' in data:
            current_user.height = float(data['height']) if data['height'] else None
        if 'resting_hr' in data:
            current_user.resting_hr = int(data['resting_hr']) if data['resting_hr'] else None
        current_user.customized = True
        db.session.commit()
        return jsonify({"status": "success", "message": "Profile updated"}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Database error: {e}")
        return jsonify({"error": "Internal server error saving data"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)