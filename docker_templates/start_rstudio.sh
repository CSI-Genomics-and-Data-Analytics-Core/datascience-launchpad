#!/bin/bash
# This is a template, actual values will be substituted by the FastAPI app.
# Not directly used by the current main.py, but can be a reference or used by a different provisioning script.

USER_NAME="$1"
RSTUDIO_PASSWORD="$2"
HOST_PORT="$3"
USER_HOME_DIR="$4" # e.g., /opt/rstudio-portal/user_data/alice
CONTAINER_NAME="rstudio-${USER_NAME}"
MEMORY_LIMIT="2g" # Default, can be parameterized
CPU_LIMIT="1.0" # Default, can be parameterized

if [ -z "$USER_NAME" ] || [ -z "$RSTUDIO_PASSWORD" ] || [ -z "$HOST_PORT" ] || [ -z "$USER_HOME_DIR" ]; then
  echo "Usage: $0 <username> <rstudio_password> <host_port> <user_home_dir>"
  exit 1
fi

# Ensure user data directory exists
mkdir -p "$USER_HOME_DIR"
chown 1000:1000 "$USER_HOME_DIR" # RStudio user in rocker images is often uid 1000

echo "Starting RStudio container for $USER_NAME on port $HOST_PORT..."
echo "Password: $RSTUDIO_PASSWORD"
echo "User data directory: $USER_HOME_DIR"

docker run -d \
  --name "$CONTAINER_NAME" \
  --memory="$MEMORY_LIMIT" \
  --cpus="$CPU_LIMIT" \
  -e "PASSWORD=$RSTUDIO_PASSWORD" \
  -e "USER=rstudio" \
  -v "$USER_HOME_DIR:/home/rstudio" \
  -p "$HOST_PORT:8787" \
  rocker/rstudio:latest # Consider pinning a specific version

if [ $? -eq 0 ]; then
  echo "RStudio container '$CONTAINER_NAME' started successfully."
  echo "Access at: http://<your-server-ip>:$HOST_PORT"
else
  echo "Failed to start RStudio container '$CONTAINER_NAME'."
  exit 1
fi
