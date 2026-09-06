import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from backend.extensions import fernet

load_dotenv()

def check_update(user, distance_meters, duration_seconds):
    """Updates a user's User object fields if a new PR for a given category has been reached (5k,
    10k, marathon).

    Returns:
        Boolean: True if an update has been made, otherwise False.
    """
    # Ranges for each distance in which a run will be considered
    distances = {
        "pr_5k": (4900, 5100),
        "pr_10k": (9800, 10200),
        "pr_marathon": (41500, 42600),
    }
    for field, (min_dis, max_dis) in distances.items():
        if min_dis <= distance_meters <= max_dis:
            current_pr = getattr(user, field) or 0.0
            if current_pr == 0.0 or duration_seconds < current_pr:
                setattr(user, field, duration_seconds)
                return True
            # Function runs for every Run - do not need to check other categories as no overlap
            break  
    return False


def run_stats(start_ms, end_ms, headers):
    """Obtains the distance, calories burnt, and steps of a specific run.

    Returns:
        Dictionary: if successful, a dictionary containing 3 key-value pairs (distance_meters, 
        calories_burned, steps) is returned, otherwise, each value is nullified (0).

    """
    aggregate_url = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
    payload = {
        "aggregateBy": [
            {"dataTypeName": "com.google.distance.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.step_count.delta"},
        ],
        "startTimeMillis": start_ms,
        "endTimeMillis": end_ms,
    }
    res = requests.post(aggregate_url, json=payload, headers=headers)
    stats = {"distance_meters": 0.0, "calories_burned": 0, "steps": 0}
    # Return dictionary with empty values
    if not res.ok:
        return stats
    data = res.json()
    datasets = data.get("dataset", [])
    for bucket in data.get("bucket", []):
        datasets.extend(bucket.get("dataset", []))
    for dataset in datasets:
        for point in dataset.get("point", []):
            data_type = point.get("dataTypeName", "")
            value_list = point.get("value", [])
            if not value_list:
                continue
            val_obj = value_list[0]
            num_val = val_obj.get("fpVal", val_obj.get("intVal", 0))
            if "distance" in data_type:
                stats["distance_meters"] += float(num_val)
            elif "calories" in data_type:
                stats["calories_burned"] += round(num_val)
            elif "step" in data_type:
                stats["steps"] += int(num_val)
    return stats


def refresh_google_token(user, db):
    """Generates a new OAuth access token for a specified user (after expiration).

    Returns:
        String: if successful, the access token is returned as a String.
        None: if an error has occured, then return None.

    """
    # User does not have a refresh token - cannot generate a new access token
    if not user.google_refresh_token:
        return None
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "refresh_token": fernet.decrypt((user.google_refresh_token).encode()).decode(),
        "grant_type": "refresh_token",
    }
    try:
        response = requests.post(token_url, data=payload, timeout=10)
        # No errors occurred - return the new access token
        if response.ok:
            data = response.json()
            new_access_token = data.get("access_token")
            user.google_access_token = fernet.encrypt(new_access_token.encode()).decode()
            db.session.commit()
            return new_access_token
    except Exception as e:
        print(f"[ERROR] Failed to refresh token for user {user.id}: {e}")
    return None
