# Dockerfile for the FastAPI application itself, not for RStudio containers

FROM python:3.9-slim

WORKDIR /app

# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin -c "Docker App User" appuser

# Install system dependencies that might be needed by Python packages
# e.g., for psycopg2 (PostgreSQL) you might need: libpq-dev gcc
# For SQLite, usually no extra deps are needed with python:slim
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY ./app /app/app
COPY ./templates /app/templates
COPY ./static /app/static
# The database and user_data will be mounted as volumes in production/docker-compose
# COPY ./db.sqlite3 /app/db.sqlite3 # Don't copy if it's a volume
# COPY ./user_data /app/user_data # Don't copy if it's a volume

# Ensure the app directory and subdirectories are owned by the appuser
# Create directories that will be mounted as volumes so permissions are set correctly
RUN mkdir -p /app/db_data /app/user_data_mount /app/logs && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Command to run the application
# The app/main.py will use environment variables for database and user data paths.
# Default Uvicorn host and port are 0.0.0.0:8000, configurable via UVICORN_HOST and UVICORN_PORT env vars.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# For build and run examples, see the README.md section on Docker.
