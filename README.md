
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

### Clone the repository:
```
git clone https://github.com/gabriellemaciunaite/running-app.git
cd running-app/backend
```
### Create and activate virtual environment:
```
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### Install dependencies:
```
pip install -r requirements.txt

```

## 2. Configure Environment Variables

Create a `.env` file in the `backend/` directory:

```env
FLASK_APP=app.py
FLASK_DEBUG=True
SECRET_KEY=your_secret_key
DATABASE_URL=your_database_url

```

---

## 3. Running the App

You need **three terminal windows** running simultaneously:

#### Terminal 1: Start Redis

```
sudo service redis-server start

```

#### Terminal 2: Start Celery Beat (Google Fit Sync)

```bash
# Start Celery Beat Scheduler
celery -A app.celery beat --loglevel=info

```

#### Terminal 3: Start Flask Server

```bash
flask run

```

---

## Usage
Access to the website can be found [here](https://www.website.com). Otherwise follow the instructions set in Installation for setting it up yourself.
