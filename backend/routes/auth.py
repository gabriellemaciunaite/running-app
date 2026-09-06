from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from backend.extensions import db
from backend.models import User
from email_validator import validate_email

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a new account.
    
    Display registration form and on submit validate input credentials, hash the password, create
    a new User in the database, and redirect the user to their dashboard.

    Arguments:
        username (str): Unique identifier for the user (alphanumeric, 3-20 characters).
        email (str): Valid email address additionally used to identify the user.
        password (str): Plaintext password (non-alphanumeric, >8 characters, mixed case).

    Returns:
        Response: redirects to dashboard view upon success, otherwise render register.html template.

    """
    # Form submit
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password or not email:
            flash("Username, password, and email are required")
            return redirect(url_for("auth.register"))
        if not username.isalnum() or len(username) > 20 or len(username) < 3:
            flash("Username must be alphanumeric and be between 3-20 characters.")
            return redirect(url_for("auth.register"))
        if len(password) < 8 or password.islower() or password.isupper() or password.isalnum():
            flash("Password must be at least 8 characters long, contain a mix of upper and lowercase characters, and at least one non-alphanumeric character.")
            return(redirect(url_for("auth.register")))

        # Returns Exception if invalid email provided - if so flash error and return register.html template
        try:
            validate_email(email)
        except Exception as e:
            flash("Invalid email provided")
            return(redirect(url_for("auth.register")))

        # Check if account already exists inside database
        existing_user = db.session.execute( db.select(User).where((User.username==username) | (User.email==email))).scalar_one_or_none()
        if existing_user:
            flash("Username or email already exists")
            return redirect(url_for("auth.register"))
        new_user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("main.dashboard"))
    # Otherwise upon GET request (retrieve registration from)
    return render_template("register.html")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Log into an existing account inside the database.
    
    Display login form and on submit validate input credentials, compare to stored hashed password,
    and redirect the user to their dashboard.

    Arguments:
        username (str): Unique identifier for the user (alphanumeric, 3-20 characters).
        password (str): Plaintext password (non-alphanumeric, >8 characters, mixed case).

    Returns:
        Response: redirects to dashboard view upon success, otherwise render login.html template.

    """
    # Log out users who attempt to access this page while authenticated
    if current_user.is_authenticated:
        logout_user()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password")
        return redirect(url_for("auth.login"))
    # Otherwise upon GET request (retrieve login from)
    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    """Log out the current user.

    Clears their session data and redirects the user to the login page.

    Returns:
        Response: redirects to login view upon success.

    """
    logout_user()
    return redirect(url_for("auth.login"))