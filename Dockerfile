FROM python:3.12.2-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies for compiling psycopg2 and system utilities
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy current dir in the project to workdir in the image
COPY . .

RUN addgroup --system celerygroup && adduser --system --ingroup celerygroup celeryuser
# Set working directory permissions
RUN chown -R celeryuser:celerygroup /app
# Switch away from root user
USER celeryuser

# Expose Flask web port
EXPOSE 5000

# Default command runs the web app
CMD ["python", "wsgi.py"]
