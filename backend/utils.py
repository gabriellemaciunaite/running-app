import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from cryptography.fernet import Fernet

load_dotenv()
fernet = Fernet(os.getenv("FERNET_ENCRYPTION_KEY").encode())

def check_update(user, distance_meters, duration_seconds):
    DISTANCES = {
        "5k": {"min": 4850, "max": 5350},
        "10k": {"min": 9700, "max": 10500},
        "marathon": {"min": 41500, "max": 43000},
    }
    updated = False
    if DISTANCES["5k"]["min"] <= distance_meters <= DISTANCES["5k"]["max"]:
        if not user.pr_5k or user.pr_5k == 0.0 or duration_seconds < user.pr_5k:
            user.pr_5k = duration_seconds
            updated = True
    if DISTANCES["10k"]["min"] <= distance_meters <= DISTANCES["10k"]["max"]:
        if not user.pr_10k or user.pr_10k == 0.0 or duration_seconds < user.pr_10k:
            user.pr_10k = duration_seconds
            updated = True
    if DISTANCES["marathon"]["min"] <= distance_meters <= DISTANCES["marathon"]["max"]:
        if (
            not user.pr_marathon
            or user.pr_marathon == 0.0
            or duration_seconds < user.pr_marathon
        ):
            user.pr_marathon = duration_seconds
            updated = True
    return updated


def run_stats(start_ms, end_ms, headers):
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
                # Keep exact unrounded meters internally
                stats["distance_meters"] += float(num_val)
            elif "calories" in data_type:
                stats["calories_burned"] += round(num_val)
            elif "step" in data_type:
                stats["steps"] += int(num_val)
    return stats


def refresh_google_token(user, db) -> str | None:
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
        if response.ok:
            data = response.json()
            new_access_token = data.get("access_token")
            user.google_access_token = fernet.encrypt(new_access_token.encode()).decode()
            db.session.commit()
            return new_access_token
    except requests.RequestException as err:
        print(f"[ERROR] Failed to refresh token for user {user.id}: {err}")
    return None
