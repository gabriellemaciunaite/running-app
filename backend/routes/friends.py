from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.extensions import db, redis_client
from backend.models import User, Friendship
from datetime import datetime, timedelta, timezone

friends_bp = Blueprint("friends", __name__, url_prefix="/api")

@friends_bp.route("/leaderboard-data")
@login_required
def get_leaderboard_data():
    """Retrieve weekly distance leaderboard for the current user.
    
    Queries the sorted set to return a set of data for each friend of the current user, such
    as weekly_km (using zscore), pr_5k, streak, rank (using zrevrank), and more. Alongside an
    array of Friendships are returned (pending friend requests).

    Returns:
        JSON object: two key-value pairs, one being a list of data about each friend of the current
        user (friends), and the other being a list of pending friend requests (incoming_requests).

    """
    accepted_friendships = db.session.execute(
        db.select(Friendship).where(
            (Friendship.sender_id == current_user.id) | (Friendship.receiver_id == current_user.id),
            Friendship.status == "accepted"
        )
    ).scalars().all()

    # Populate friends_ids set
    friend_ids = {current_user.id}
    for f in accepted_friendships:
        if f.sender_id == current_user.id:
            friend_ids.add(f.receiver_id)
        else:
            friend_ids.add(f.sender_id)
    # Generate Redis key to provide scores only within this week
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    redis_key = f"leaderboard:distance:{year}-W{week}"
    users = db.session.execute(db.select(User).where(User.id.in_(friend_ids))).scalars().all()

    # For each user that is a friend of current_user, add to results a pair containing the user's
    # rank and their weekly distance
    pipe = redis_client.pipeline()
    for user in users:
        pipe.zrevrank(redis_key, str(user.id))
        pipe.zscore(redis_key, str(user.id))
    pipeline_results = pipe.execute()
    results = [pipeline_results[i : i + 2] for i in range(0, len(pipeline_results), 2)]
    # Structure return data
    friends_data = [
        {
            "id": user.id,
            "username": user.username,
            "rank": raw_rank + 1 if raw_rank is not None else None,
            "streak": user.login_streak or 0,
            "weekly_km": round(float(score), 2) if score is not None else 0.0,
            "is_me": user.id == current_user.id,
            "pr_5k": user.pr_5k or 0.0,
            "pr_10k": user.pr_10k or 0.0,
            "pr_marathon": user.pr_marathon or 0.0,
        }
        for user, (raw_rank, score) in zip(users, results)
    ]
    # Fetch all pending incoming requests and zip id with sender username
    pending_requests = db.session.execute(
        db.select(Friendship).where(Friendship.receiver_id == current_user.id, Friendship.status == "pending")
    ).scalars().all()
    incoming_requests = [{"request_id": req.id, "sender_username": req.sender.username} for req in pending_requests]
    return jsonify({"friends": friends_data, "incoming_requests": incoming_requests}), 200

@friends_bp.route("/friends/request", methods=["POST"])
@login_required
def send_friend_request():
    """Send an outgoing friend request to the user specified.
    
    Validates the friend request (check a valid id is provided, the id is distinct from yourself,
    and an outgoing request does not already exist). If successful, add the Friendship to the 
    database and a successful JSON response.

    Returns:
        JSON object: if successful, return a success response saying friend request sent with error
        code 200, otherwise an error response with a valid message and an error code 400/404.

    """
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
    # Passed validation - add friendship to db
    db.session.add(Friendship(sender_id=current_user.id, receiver_id=target_user.id, status="pending"))
    db.session.commit()
    return jsonify({"message": f"Friend request sent to {target_user.username}"}), 200

@friends_bp.route("/friends/respond/<int:request_id>", methods=["POST"])
@login_required
def respond_friend_request(request_id):
    """Respond to an incoming friend request.
    
    Validates the friend request (check a valid id is provided, the receiver is the id of the user
    responding to the request). If successful, either change the status of the request to "accepted"
    or delete the Friend object.

    Returns:
        JSON object: if successful, return a success response saying friend request either accepted
        or denied with error code 200, otherwise an error response with a valid message and an
        error code 400/404.

    """
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ("accept", "decline"):
        return jsonify({"error": "Invalid action. Must be 'accept' or 'decline'"}), 400
    friend_req = db.session.execute(
        db.select(Friendship).where(Friendship.id == request_id, Friendship.receiver_id == current_user.id)
    ).scalar_one_or_none()

    if friend_req is None:
        return jsonify({"error": "Friend request not found"}), 404
    if action == "accept":
        friend_req.status = "accepted"
        msg = "Request accepted"
    elif action == "decline":
        db.session.delete(friend_req)
        msg = "Request declined"
    db.session.commit()
    return jsonify({"message": msg}), 200

@friends_bp.route("/friends/remove/<int:friend_id>", methods=["DELETE"])
@login_required
def remove_friend(friend_id):
    """Remove a friend from the current user's friend list.
    
    Validates the Friendship object (check a valid id is provided, the current user is either the
    receiver or the sender of the friend request). If successful, delete the Friendship
    object.

    Returns:
        JSON object: if successful, return a success response saying friend remoed with error code
        200, otherwise an error response with a valid message and an error code 404.

    """
    friendship = db.session.execute(
        db.select(Friendship).where(
            ((Friendship.sender_id == current_user.id) & (Friendship.receiver_id == friend_id))
            | ((Friendship.sender_id == friend_id) & (Friendship.receiver_id == current_user.id))
        )
    ).scalar_one_or_none()

    if friendship is None:
        return jsonify({"error": "Friendship record not found"}), 404
    # Passed validation - delete the friendship
    db.session.delete(friendship)
    db.session.commit()
    return jsonify({"message": "Friend removed"}), 200