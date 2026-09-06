from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.extensions import db, gemini_client
from backend.models import RunningPlan, WorkoutDay, Exercise, GeminiPlanSchema

workouts_bp = Blueprint("workouts", __name__)

@workouts_bp.route("/generate_workout", methods=["POST"])
@login_required
def generate_workout():
    instruction = (
        "You are a professional personal trainer. Generate a tailored training plan for a runner.",
        f"User age: {current_user.age}, weight: {current_user.weight}kg, height: {current_user.height}cm.",
        f"Fitness level: {current_user.fitness_level}. Schedule: {current_user.weekly_days} days per week.",
        f"Primary target goal: {current_user.target_goal}.",
        "Adhere to these parameters when selecting exercises, sets, reps, time, workout type, and day counts.",
        "Remember that this is primarily for a running app. Strength training should have non-zero values for reps and sets. Cardio should have non-zero time.",
    )
    try:
        old_plan = db.session.execute(
            db.select(RunningPlan).filter_by(user_id=current_user.id)
        ).scalar_one_or_none()
        if old_plan:
            db.session.delete(old_plan)
            db.session.flush()

        completion = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Generate my training routine based entirely on my constraints.",
            config={
                "system_instruction": instruction,
                "response_mime_type": "application/json",
                "response_schema": GeminiPlanSchema,
            },
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
                db.session.add(
                    Exercise(
                        name=ex_data.name,
                        sets=ex_data.sets,
                        reps=ex_data.reps,
                        workout_type=ex_data.workout_type,
                        workout_day=db_day,
                        time=ex_data.time,
                    )
                )
        db.session.commit()
        return jsonify({"status": "success", "plan_id": plan.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@workouts_bp.route("/toggle_exercise/<int:exercise_id>", methods=["POST"])
@login_required
def toggle_exercise(exercise_id):
    data = request.get_json()
    if not data or "completed" not in data:
        return jsonify({"error": "Missing 'completed' state in payload"}), 400
    try:
        exercise = db.session.execute(
            db.select(Exercise).filter_by(id=exercise_id)
        ).scalar_one_or_none()
        if not exercise:
            return jsonify({"error": "This exercise is not found"}), 404
        if exercise.workout_day.plan.user_id != current_user.id:
            return jsonify({"error": "Unauthorized action"}), 403

        exercise.completed = not exercise.completed
        db.session.commit()
        return jsonify({
            "status": "success",
            "exercise_id": exercise_id,
            "completed": exercise.completed,
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500