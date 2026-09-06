from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from backend.extensions import db
from backend.models import User
from email_validator import validate_email

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password or not email:
            flash("Username, password, and email are required")
            return redirect(url_for("auth.register"))
        existing_user = db.session.execute(
            db.select(User).where((User.username==username) | (User.email==email))
        ).scalar_one_or_none()
        if existing_user:
            flash("Username or email already exists")
            return redirect(url_for("auth.register"))
        if len(password) < 8 or password.islower() or password.isupper() or password.isalnum():
            flash("Password must be greater than 8 characters long, contain a mix of upper and lowercase characters, and at least one non-alphanumeric character.")
            return(redirect(url_for("auth.register")))
        try:
            validate_email(email)
        except Exception as e:
            flash("Invalid email provided")
            return(redirect(url_for("auth.register")))
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("main.dashboard"))
    return render_template("register.html")

@auth_bp.route("/login", methods=["GET", "POST"])
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
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password")
        return redirect(url_for("auth.login"))
    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))