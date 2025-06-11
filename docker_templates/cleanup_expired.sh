#!/bin/bash
# This script will be run by cron to stop and remove expired RStudio containers.
# It needs to interact with the SQLite database to find expired containers.

DB_FILE="/opt/rstudio-portal/db.sqlite3" # Adjust path as necessary
LOG_FILE="/opt/rstudio-portal/logs/cleanup.log" # Ensure this directory exists and is writable

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

echo "----------------------------------------" >> "$LOG_FILE"
echo "Cleanup script started at $(date)" >> "$LOG_FILE"

if [ ! -f "$DB_FILE" ]; then
    echo "Database file $DB_FILE not found!" >> "$LOG_FILE"
    exit 1
fi

# SQLite query to find expired containers (status is 'running' and expires_at is in the past)
EXPIRED_CONTAINERS=$(sqlite3 "$DB_FILE" "SELECT container_name, id FROM rstudio_instances WHERE status = 'running' AND expires_at < datetime('now');")

if [ -z "$EXPIRED_CONTAINERS" ]; then
    echo "No expired containers found." >> "$LOG_FILE"
    echo "Cleanup script finished at $(date)" >> "$LOG_FILE"
    exit 0
fi

echo "Found expired containers:" >> "$LOG_FILE"
echo "$EXPIRED_CONTAINERS" >> "$LOG_FILE"

IFS=$'
' # Change Internal Field Separator to newline for looping
for line in $EXPIRED_CONTAINERS; do
    CONTAINER_NAME=$(echo "$line" | cut -d'|' -f1)
    INSTANCE_ID=$(echo "$line" | cut -d'|' -f2)

    if [ -z "$CONTAINER_NAME" ]; then
        echo "Skipping empty container name for instance ID $INSTANCE_ID." >> "$LOG_FILE"
        continue
    fi

    echo "Processing container: $CONTAINER_NAME (Instance ID: $INSTANCE_ID)" >> "$LOG_FILE"

    # Check if container exists and is running
    if docker ps -q --filter "name=^/${CONTAINER_NAME}$" --filter "status=running" | grep -q .; then
        echo "Stopping container $CONTAINER_NAME..." >> "$LOG_FILE"
        docker stop "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
            echo "Error stopping container $CONTAINER_NAME. It might have already been stopped." >> "$LOG_FILE"
        fi
    else
        echo "Container $CONTAINER_NAME is not running or does not exist." >> "$LOG_FILE"
    fi

    # Check if container exists (even if stopped) before removing
    if docker ps -aq --filter "name=^/${CONTAINER_NAME}$" | grep -q .; then
        echo "Removing container $CONTAINER_NAME..." >> "$LOG_FILE"
        docker rm "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
            echo "Error removing container $CONTAINER_NAME. It might have already been removed." >> "$LOG_FILE"
        fi
    else
         echo "Container $CONTAINER_NAME does not exist for removal." >> "$LOG_FILE"
    fi

    # Update database
    echo "Updating database for instance ID $INSTANCE_ID, setting status to 'expired_cleaned'." >> "$LOG_FILE"
    sqlite3 "$DB_FILE" "UPDATE rstudio_instances SET status = 'expired_cleaned' WHERE id = '$INSTANCE_ID';"
    if [ $? -eq 0 ]; then
        echo "Database updated successfully for instance ID $INSTANCE_ID." >> "$LOG_FILE"
    else
        echo "Error updating database for instance ID $INSTANCE_ID." >> "$LOG_FILE"
    fi

    # Optional: Archive user data
    # USER_ID=$(sqlite3 "$DB_FILE" "SELECT user_id FROM rstudio_instances WHERE id = '$INSTANCE_ID';")
    # USERNAME=$(sqlite3 "$DB_FILE" "SELECT username FROM users WHERE id = '$USER_ID';")
    # USER_DATA_DIR="/opt/rstudio-portal/user_data/$USERNAME"
    # ARCHIVE_DIR="/opt/rstudio-portal/archived_user_data"
    # mkdir -p "$ARCHIVE_DIR"
    # if [ -d "$USER_DATA_DIR" ]; then
    #   echo "Archiving data for $USERNAME..." >> "$LOG_FILE"
    #   tar -czf "$ARCHIVE_DIR/${USERNAME}_$(date +%Y%m%d_%H%M%S).tar.gz" -C "/opt/rstudio-portal/user_data" "$USERNAME" >> "$LOG_FILE" 2>&1
    #   # Optionally remove original data: rm -rf "$USER_DATA_DIR"
    # fi
done

echo "Cleanup script finished at $(date)" >> "$LOG_FILE"
echo "----------------------------------------" >> "$LOG_FILE"

exit 0
