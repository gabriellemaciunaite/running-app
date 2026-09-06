from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.extensions import db, redis_client
from backend.models import User, Friendship

friends_bp = Blueprint("friends", __name__, url_prefix="/api")

@friends_bp.route("/leaderboard-data")
@login_required
def get_leaderboard_data():
    accepted_friendships = db.session.execute(
        db.select(Friendship).where(
            (Friendship.sender_id == current_user.id) | (Friendship.receiver_id == current_user.id),
            Friendship.status == "accepted"
        )
    ).scalars().all()

    friend_ids = {current_user.id}
    for f in accepted_friendships:
        friend_ids.add(f.receiver_id if f.sender_id == current_user.id else f.sender_id)

    year, week, _ = datetime.now(timezone.utc).isocalendar()
    redis_key = f"leaderboard:distance:{year}-W{week}"

    user_pool = db.session.execute(db.select(User).where(User.id.in_(friend_ids))).scalars().all()
    pipe = redis_client.pipeline()
    for user in user_pool:
        pipe.zscore(redis_key, str(user.id))
    scores = pipe.execute()

    friends_data = [
        {
            "id": user.id,
            "username": user.username,
            "streak": user.login_streak or 0,
            "weekly_km": round(float(score), 2) if score is not None else 0.0,
            "is_me": user.id == current_user.id,
            "pr_5k": user.pr_5k or 0.0,
            "pr_10k": user.pr_10k or 0.0,
            "pr_marathon": user.pr_marathon or 0.0,
        }
        for user, score in zip(user_pool, scores)
    ]
    friends_data.sort(key=lambda x: x["weekly_km"], reverse=True)

    pending_requests = db.session.execute(
        db.select(Friendship).where(Friendship.receiver_id == current_user.id, Friendship.status == "pending")
    ).scalars().all()

    incoming_requests = [
        {"request_id": req.id, "sender_username": req.sender.username}
        for req in pending_requests
    ]
    return jsonify({"friends": friends_data, "incoming_requests": incoming_requests}), 200

@friends_bp.route("/friends/request", methods=["POST"])
@login_required
def send_friend_request():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    target_user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()

    if not target_user:
        return jsonify({"error": "User not found"}), 404
    if target_user == current_user:
        return jsonify({"error": "You cannot add yourself"}), 400

    existing = db.session.execute(db.select(Friendship).where(
        ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == target_user.id))
        | ((Friendship.sender_id == target_user.id) & (Friendship.receiver_id == current_user.id))
    )).scalar_one_or_none()

    if existing:
        msg = "You are already friends with this user" if existing.status == "accepted" else "A pending friend request already exists"
        return jsonify({"error": msg}), 400

    db.session.add(Friendship(sender_id=current_user.id, receiver_id=target_user.id, status="pending"))
    db.session.commit()
    return jsonify({"message": f"Friend request sent to {target_user.username}"}), 200

@friends_bp.route("/friends/respond/<int:request_id>", methods=["POST"])
@login_required
def respond_friend_request(request_id):
    data = request.get_json() or {}
    action = data.get("action")
    friend_req = db.session.execute(
        db.select(Friendship).where(Friendship.id == request_id, Friendship.receiver_id == current_user.id)
    ).scalar_one_or_none()

    if friend_req is None:
        return jsonify({"error": "Friend request not found"}), 404
    if action == "accept":
        friend_req.status = "accepted"
    elif action == "decline":
        db.session.delete(friend_req)
    else:
        return jsonify({"error": "Invalid action. Must be 'accept' or 'decline'"}), 400

    db.session.commit()
    return jsonify({"message": f"Request {action}ed successfully"}), 200

@friends_bp.route("/friends/remove/<int:friend_id>", methods=["DELETE"])
@login_required
def remove_friend(friend_id):
    friendship = db.session.execute(
        db.select(Friendship).where(
            ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == friend_id))
            | ((Friendship.sender_id == friend_id) & (Friendship.receiver_id == current_user.id))
        )
    ).scalar_one_or_none()

    if friendship is None:
        return jsonify({"error": "Friendship record not found"}), 404

    db.session.delete(friendship)
    db.session.commit()
    return jsonify({"message": "Friend removed"}), 200