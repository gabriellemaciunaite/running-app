from backend.extensions import db
from flask_login import UserMixin
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import List

class Run(db.Model):
    __tablename__ = 'run'
    id = db.Column(db.Integer, primary_key=True)
    google_session_id = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), default="Untitled Run")
    description = db.Column(db.Text, default="")
    distance_meters = db.Column(db.Float, default=0.0)
    duration_seconds = db.Column(db.Float, default=0.0)
    calories_burned = db.Column(db.Integer, default=0)
    steps = db.Column(db.Integer, default=0)
    start_time_ms = db.Column(db.BigInteger, nullable=False)
    end_time_ms = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.google_session_id,
            "name": self.name,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "distance_meters": self.distance_meters,
            "distance_km": round((self.distance_meters or 0) / 1000.0, 2),
            "calories_burned": self.calories_burned,
            "steps": self.steps,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
        }

    # Relationship back to User
    user = db.relationship('User', backref=db.backref('runs', lazy=True, cascade="all, delete-orphan"))

class Friendship(db.Model):
    __tablename__ = 'friendship'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending' or 'accepted'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_friend_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_friend_requests')

class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    customized = db.Column(db.Boolean, default=False)
    fitness_level = db.Column(db.String(256))
    age = db.Column(db.Integer)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    weekly_days = db.Column(db.String(256))
    target_goal = db.Column(db.String(256))
    plans = db.relationship("RunningPlan", backref="user", cascade="all, delete-orphan")
    google_connected = db.Column(db.Boolean, default=False)
    google_access_token = db.Column(db.Text)
    google_refresh_token = db.Column(db.Text)
    google_token_expires_at = db.Column(db.Integer)

    login_streak = db.Column(db.Integer, default=0)
    last_login_date = db.Column(db.DateTime, nullable=True)
    pr_5k = db.Column(db.Float, default=0.0)
    pr_10k = db.Column(db.Float, default=0.0)
    pr_marathon = db.Column(db.Float, default=0.0)

    def update_login_streak(self):
        now = datetime.now()
        today = now.date()

        if self.last_login_date is None:
            self.login_streak = 1
        else:
            last_date = self.last_login_date.date()
            if last_date == today - timedelta(days=1):
                self.login_streak += 1
            elif last_date < today - timedelta(days=1):
                self.login_streak = 1  # Reset streak if missed a day
        self.last_login_date = now
        db.session.commit()

class RunningPlan(db.Model):
    __tablename__ = "running_plan"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    days = db.relationship("WorkoutDay", backref="plan", cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    name = db.Column(db.String(255), nullable=False)

class WorkoutDay(db.Model):
    __tablename__ = "workout_day"
    id = db.Column(db.Integer, primary_key=True)
    day_name = db.Column(db.String(255), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("running_plan.id"), nullable=False)
    exercises = db.relationship("Exercise", backref="workout_day", cascade="all, delete-orphan")

class Exercise(db.Model):
    __tablename__ = "exercise"
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey("workout_day.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(50))
    completed = db.Column(db.Boolean, default=False)
    workout_type = db.Column(db.String(50), nullable=False)
    time = db.Column(db.String(50))
    description = db.Column(db.String(150))



class GeminiExercise(BaseModel):
    name: str = Field(description="The name of the exercise")
    sets: int = Field(description="The number of sets of the exercise if 'strength' is chosen")
    reps: str = Field(description="The number of reps of the exercise if 'strength' is chosen")
    workout_type: str = Field(description="This option is either 'cardio' for running or 'strength' for otherwise/general")
    time: str = Field(description="The duration of the exercise if 'cardio' is chosen")
    description: str = Field(description="A short sentence describing the exercise")

class GeminiWorkoutDay(BaseModel):
    day_name: str = Field(description="e.g., 'Day 1: Upper Body'")
    exercises: List[GeminiExercise]

class GeminiPlanSchema(BaseModel):
    name: str = Field(description="Catchy title for this specific routine")
    days: List[GeminiWorkoutDay]