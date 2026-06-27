from extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    customized = db.Column(db.Boolean, default=False)
    fitness_level = db.Column(db.Integer)
    age = db.Column(db.Integer)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    weekly_days = db.Column(db.String(256))
    target_goal = db.Column(db.String(256))
    plans = db.relationship("RunningPlan", backref="user", cascade="all, delete-orphan")

class RunningPlan(db.Model):
    __tablename__ = "running_plan"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    workouts = db.relationship("Workout", backref="plan", cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    weeks_count = db.Column(db.Integer, nullable=False)

class Workout(db.Model):
    __tablename__ = "workout"
    id = db.Column(db.Integer, primary_key=True)
    day_number = db.Column(db.Integer, nullable=False)
    workout_type = db.Column(db.String(50), nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("running_plan.id"), nullable=False)