#!/usr/bin/env python3
import sqlite3
import subprocess
import os
from pathlib import Path
import dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load environment variables from .env file in the project root
# Assumes the script is in /scripts and .env is in /
PROJECT_ROOT = Path(__file__).resolve().parent.parent
dotenv.load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Database Configuration
DB_MOUNT_PATH_STR = os.getenv("DB_MOUNT_PATH")
DATABASE_FILENAME = os.getenv("DATABASE_FILENAME", "db.sqlite3")

if DB_MOUNT_PATH_STR:
    DATABASE = Path(DB_MOUNT_PATH_STR) / DATABASE_FILENAME
else:
    # Default to project root if not specified (consistent with app/main.py's default)
    DATABASE = PROJECT_ROOT / DATABASE_FILENAME

if not DATABASE.parent.exists():
    logging.error(
        f"Database directory {DATABASE.parent} does not exist. "
        "Please check DB_MOUNT_PATH."
    )
    # Depending on setup, you might want to exit or create it.
    # For a cleanup script, it's safer to assume it should exist.
    exit(1)


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Error connecting to database {DATABASE}: {e}")
        return None


def find_expired_instances(db_conn):
    """Finds user instances that are past their expiration date and are 'running'."""
    try:
        cursor = db_conn.cursor()
        query = """
            SELECT id, container_name, user_id
            FROM user_instances
            WHERE status = 'running' AND expires_at < DATETIME('now')
        """
        cursor.execute(query)
        instances = cursor.fetchall()
        return instances
    except sqlite3.Error as e:
        logging.error(f"Error querying expired instances: {e}")
        return []


def stop_and_remove_container(container_name):
    """Stops and removes a Docker container."""
    if not container_name:
        logging.warning("Container name is missing, cannot stop/remove.")
        return False
    try:
        logging.info(f"Attempting to stop container: {container_name}")
        subprocess.run(
            ["docker", "stop", container_name],
            check=True,
            capture_output=True,
            text=True,
        )
        logging.info(f"Successfully stopped container: {container_name}")

        logging.info(f"Attempting to remove container: {container_name}")
        subprocess.run(
            ["docker", "rm", container_name], check=True, capture_output=True, text=True
        )
        logging.info(f"Successfully removed container: {container_name}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(
            f"Failed to stop/remove container {container_name}. Error: {e.stderr}"
        )
        # If stop fails, rm might also fail or container might not exist.
        # Check if container still exists before trying to remove if stop failed.
        # For simplicity, we assume if stop worked, rm should be attempted.
        # If stop failed, it might be already stopped/removed.
        # Check if container exists
        check_exists_ps = subprocess.run(
            ["docker", "ps", "-a", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )
        if container_name not in check_exists_ps.stdout:
            logging.info(
                f"Container {container_name} does not exist, likely already removed."
            )
            return True  # Effectively removed
        return False
    except Exception as e:
        logging.error(
            f"An unexpected error occurred while managing container {container_name}: {e}"
        )
        return False


def update_instance_status_in_db(db_conn, instance_id, new_status="stopped_expired"):
    """Updates the status of a user instance in the database."""
    try:
        cursor = db_conn.cursor()
        query = "UPDATE user_instances SET status = ?, container_id = NULL WHERE id = ?"
        cursor.execute(query, (new_status, instance_id))
        db_conn.commit()
        logging.info(f"Updated instance ID {instance_id} status to '{new_status}'.")
        return True
    except sqlite3.Error as e:
        logging.error(f"Error updating instance ID {instance_id} in database: {e}")
        return False


def main():
    logging.info("Starting RStudio cleanup script...")

    if not DATABASE.exists():
        logging.error(f"Database file not found at {DATABASE}. Exiting.")
        return

    db_conn = get_db_connection()
    if not db_conn:
        logging.error("Failed to connect to the database. Exiting.")
        return

    try:
        expired_instances = find_expired_instances(db_conn)
        if not expired_instances:
            logging.info("No expired RStudio instances found.")
            return

        logging.info(f"Found {len(expired_instances)} expired instance(s) to process.")
        cleaned_count = 0
        for instance in expired_instances:
            logging.info(
                f"Processing instance ID: {instance['id']}, "
                f"Container: {instance['container_name']}"
            )
            if stop_and_remove_container(instance["container_name"]):
                if update_instance_status_in_db(db_conn, instance["id"]):
                    cleaned_count += 1
                else:
                    # E501: Line shortened
                    logging.error(
                        f"Failed to update database for instance ID: {instance['id']} "
                        "after container removal."
                    )
            else:
                # E501: Line shortened
                logging.warning(
                    f"Could not stop/remove container {instance['container_name']}. "
                    f"Database not updated for instance ID: {instance['id']}."
                )
        logging.info(
            f"Successfully cleaned up {cleaned_count} of "  # E501: Line shortened
            f"{len(expired_instances)} expired instances."
        )

    finally:
        if db_conn:
            db_conn.close()
            logging.info("Database connection closed.")
    logging.info("RStudio cleanup script finished.")


if __name__ == "__main__":
    main()
