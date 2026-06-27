# running-app

## What is running-app?
A WIP AI-powered running companion that generates custom workout plans and routes with real-time GPS tracking and social leaderboards.
## Installation

1. **Clone the repo:**
```
git clone https://github.com/gabriellemaciunaite/running-app.git
cd running-app
```
2. **Setup the Flask backend:**
```
cd backend

# (Use 'python' instead if on Windows)
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```
3. **Configure Environment Variables:**  
  Create a `.env` file in the `backend/` directory.
```
FLASK_APP=app.py
FLASK_DEBUG=True
SECRET_KEY=your_secret_key
DATABASE_URL=your_database_url
```
4. **Run the application:**
```
flask run
```

## Usage
Access to the website can be found [here](website.com) (works best on mobile devices with GPS functionality). Otherwise follow the instructions set in **Installation** for setting it up yourself.
