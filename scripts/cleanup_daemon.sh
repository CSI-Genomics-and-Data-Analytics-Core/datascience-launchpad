#!/bin/bash

# Enhanced cleanup script with better error handling and logging
# This script provides an alternative to the Python version

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables if .env exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Database configuration
DB_MOUNT_PATH="${DB_MOUNT_PATH:-$PROJECT_ROOT}"
DATABASE_FILENAME="${DATABASE_FILENAME:-db.sqlite3}"
DB_FILE="$DB_MOUNT_PATH/$DATABASE_FILENAME"

# Logging configuration
LOG_DIR="/var/log/rstudio-portal"
LOG_FILE="$LOG_DIR/cleanup.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE" >&2
}

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running or not accessible"
        exit 1
    fi
}

# Function to validate database
validate_database() {
    if [ ! -f "$DB_FILE" ]; then
        log_error "Database file not found at $DB_FILE"
        exit 1
    fi

    # Test database connection
    if ! sqlite3 "$DB_FILE" "SELECT 1;" >/dev/null 2>&1; then
        log_error "Cannot connect to database at $DB_FILE"
        exit 1
    fi
}

# Function to cleanup expired instances
cleanup_expired_instances() {
    log "Starting cleanup of expired RStudio instances..."

    # Query for expired instances
    local query="SELECT id, container_name, user_id FROM user_instances WHERE status = 'running' AND expires_at < datetime('now');"
    local expired_instances

    expired_instances=$(sqlite3 "$DB_FILE" "$query" 2>/dev/null) || {
        log_error "Failed to query expired instances"
        return 1
    }

    if [ -z "$expired_instances" ]; then
        log "No expired instances found"
        return 0
    fi

    local total_count=$(echo "$expired_instances" | wc -l)
    local cleaned_count=0

    log "Found $total_count expired instance(s) to process"

    # Process each expired instance
    while IFS='|' read -r instance_id container_name user_id; do
        [ -z "$container_name" ] && continue

        log "Processing instance ID: $instance_id, Container: $container_name, User: $user_id"

        if cleanup_container "$container_name"; then
            if update_instance_status "$instance_id" "stopped_expired"; then
                ((cleaned_count++))
                log "Successfully cleaned up instance $instance_id"
            else
                log_error "Failed to update database for instance $instance_id"
            fi
        else
            log_error "Failed to cleanup container $container_name for instance $instance_id"
        fi

    done <<< "$expired_instances"

    log "Successfully cleaned up $cleaned_count of $total_count expired instances"
}

# Function to cleanup a single container
cleanup_container() {
    local container_name="$1"

    # Check if container exists
    if ! docker ps -a --filter "name=^${container_name}$" --format "{{.Names}}" | grep -q "^${container_name}$"; then
        log "Container $container_name does not exist, marking as cleaned"
        return 0
    fi

    # Stop container if running
    if docker ps --filter "name=^${container_name}$" --format "{{.Names}}" | grep -q "^${container_name}$"; then
        log "Stopping container $container_name..."
        if docker stop "$container_name" >/dev/null 2>&1; then
            log "Successfully stopped container $container_name"
        else
            log_error "Failed to stop container $container_name"
            return 1
        fi
    else
        log "Container $container_name is not running"
    fi

    # Remove container
    log "Removing container $container_name..."
    if docker rm "$container_name" >/dev/null 2>&1; then
        log "Successfully removed container $container_name"
        return 0
    else
        log_error "Failed to remove container $container_name"
        return 1
    fi
}

# Function to update instance status in database
update_instance_status() {
    local instance_id="$1"
    local new_status="$2"

    local update_query="UPDATE user_instances SET status = '$new_status', container_id = NULL WHERE id = '$instance_id';"

    if sqlite3 "$DB_FILE" "$update_query" 2>/dev/null; then
        log "Updated instance $instance_id status to '$new_status'"
        return 0
    else
        log_error "Failed to update instance $instance_id status to '$new_status'"
        return 1
    fi
}

# Function to cleanup old log files (keep last 30 days)
cleanup_old_logs() {
    find "$LOG_DIR" -name "*.log" -type f -mtime +30 -delete 2>/dev/null || true
}

# Main function
main() {
    log "========================================="
    log "RStudio cleanup script started"

    # Perform checks
    check_docker
    validate_database

    # Cleanup expired instances
    cleanup_expired_instances

    # Cleanup old logs
    cleanup_old_logs

    log "RStudio cleanup script finished"
    log "========================================="
}

# Run main function
main "$@"
