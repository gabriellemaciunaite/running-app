from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.extensions import db, gemini_client
from backend.models import RunningPlan, WorkoutDay, Exercise, GeminiPlanSchema

workouts_bp = Blueprint("workouts", __name__)

@workouts_bp.route("/generate_workout", methods=["POST"])
@login_required
def generate_workout():
    """Creates a RunningPlan object for the user based on personal information given during the
    customize stage and returns the plan's id in the database.

    Returns:
        JSON Object: if successful return a success message alongside the RunningPlan id with error
        code 200, otherwise return an error message with error code 500.
    """
    instruction = (
        "You are a professional personal trainer. Generate a tailored training plan for a runner.",
        f"User age: {current_user.age}, weight: {current_user.weight}kg, height: {current_user.height}cm.",
        f"Fitness level: {current_user.fitness_level}. Schedule: {current_user.weekly_days} days per week.",
        f"Primary target goal: {current_user.target_goal}.",
        "Adhere to these parameters when selecting exercises, sets, reps, time, workout type, and day counts.",
        "Remember that this is primarily for a running app. Strength training should have non-zero values for reps and sets. Cardio should have non-zero time.",
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
                "response_schema": GeminiPlanSchema,
            },
        )
        # Fetch data outputted by the model
        data = completion.parsed
        if not data:
            return jsonify({"error": "Failed to generate the content for the workout plan."}), 500
        plan = RunningPlan(name=data.name, user=current_user)
        db.session.add(plan)
        # Create individual WorkoutDay objects containing Exercise objects
        for day_data in data.days:
            db_day = WorkoutDay(day_name=day_data.day_name, plan=plan)
            db.session.add(db_day)
            for exercise_data in day_data.exercises:
                db.session.add(
                    Exercise(
                        name=exercise_data.name,
                        sets=exercise_data.sets,
                        reps=exercise_data.reps,
                        workout_type=exercise_data.workout_type,
                        workout_day=db_day,
                        time=exercise_data.time,
                    )
                )
        db.session.commit()
        return jsonify({"status": "success", "plan_id": plan.id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"An error occurred whilst generating a workout plan: {str(e)}"}), 500

@workouts_bp.route("/toggle_exercise/<int:exercise_id>", methods=["POST"])
@login_required
def toggle_exercise(exercise_id):
    """Updates Exercise objects within the database by toggling their completed status.

    Returns:
        JSON Object: if successful return a success message alongside the Exercise id and completion
        status with error code 200, otherwise return an error message with error code 500/404/403/400.
    """
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
        # Reverse state of exercise.completed and commit to database
        exercise.completed = not exercise.completed
        db.session.commit()
        return jsonify({"status": "success", "exercise_id": exercise_id, "completed": exercise.completed,}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"The exercise could not be toggled: {str(e)}"}), 500