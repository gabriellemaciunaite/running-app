from extensions import db
from flask_login import UserMixin
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List

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
    days = db.relationship("WorkoutDay", backref="plan", cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    name = db.Column(db.String(255), nullable=False)

class WorkoutDay(db.Model):
    __tablename__ = "workout_day"
    id = db.Column(db.Integer, primary_key=True)
    day_name = db.Column(db.Integer, nullable=False)
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



class OpenAIExercise(BaseModel):
    name: str = Field(description="The name of the exercise")
    sets: int = Field(description="The number of sets of the exercise if 'strength' is chosen")
    reps: str = Field(description="The number of reps of the exercise if 'strength' is chosen")
    workout_type: str = Field(description="This option is either 'cardio' for running or 'strength' for otherwise/general")
    time: str = Field(description="The duration of the exercise if 'cardio' is chosen")
    description: str = Field(description="A short sentence describing the exercise")

class OpenAIWorkoutDay(BaseModel):
    day_name: str = Field(description="e.g., 'Day 1: Upper Body'")
    exercises: List[OpenAIExercise]

class OpenAIPlanSchema(BaseModel):
    name: str = Field(description="Catchy title for this specific routine")
    days: List[OpenAIWorkoutDay]