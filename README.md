
# Fitness & Running Analytics Platform

A running app built with **Flask**, **Redis**, and **Celery**. Features automated workout plans, integration with Google Fit to provide running statistics, and real-time social leaderboards.

---

## Technical Features

* **Real-Time Leaderboards (Redis Sorted Sets):** Employs Redis `ZSET` data structures to maintain $O(\log N)$ rank lookups and updates, allowing real-time social leaderboard sorting without querying the main SQL database.
* **Background Data Sync (Celery + Redis):** Uses Celery Beat workers to asynchronously fetch user-logged runs from the **Google Fit API** on a scheduled interval.
* **Automated Workout Plans:** Uses Gemini API to dynamically generate tailored workout plans for users based on their goals and fitness level.

---

## Getting Started

## 1. Installation & Environment Setup

Clone the repository:
```
git clone https://github.com/gabriellemaciunaite/running-app.git
cd running-app/backend
```

## 2. Configure environment variables:

Create a `.env` file in the `backend/` directory:

```env
FLASK_APP=app.py
FLASK_DEBUG=True
SECRET_KEY=your_secret_key
DATABASE_URL=your_database_url
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_CLIENT_ID=your_google_fit_client_id
GOOGLE_CLIENT_SECRET=your_google_fit_client_secret
FERNET_ENCRYPTION_KEY=your_32-byte_b65_string
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

```

---

## 3. Running the App

You need **Docker** for this setup.

To build the images and start the containers in the background:

```
docker compose up -d --build

```
One running, you can access the web app at [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## Usage
Access to the website can be found [here](https://running-app-iam1.onrender.com) (note only pre-approved accounts can link to Google Fit, and automated synchronization is disabled in this demo).\
Otherwise follow the instructions set in **Getting Started** for setting it up yourself.
