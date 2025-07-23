# filepath: /Users/mani/work/rstudio-portal/app/db/database.py
import sqlite3
import logging
from datetime import datetime, timezone
from app.core.config import (
    DATABASE_PATH,
    INITIAL_ADMIN_USERNAME,
)

logger = logging.getLogger(__name__)


def get_db():
    # Ensure the parent directory for the database file exists
    db_path_obj = DATABASE_PATH
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Connecting to database at: {db_path_obj}")
    db = sqlite3.connect(str(db_path_obj))  # Use str() for Path object
    db.row_factory = sqlite3.Row
    return db


def init_db():
    # Ensure the parent directory for the database file exists before connecting
    db_path_obj = DATABASE_PATH
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Initializing database at: {db_path_obj}")

    conn = sqlite3.connect(str(db_path_obj))
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        is_admin BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME,
        lab_name TEXT
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS user_instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        container_name TEXT NOT NULL,
        container_id TEXT,
        port INTEGER NOT NULL,
        password TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME,
        status TEXT DEFAULT 'requested',
        stopped_at DATETIME,
        instance_type TEXT DEFAULT 'rstudio',
        memory_limit TEXT DEFAULT '16g',
        cpu_limit TEXT DEFAULT '2.0',
        storage_limit TEXT DEFAULT '200G',
        session_days INTEGER DEFAULT 2,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """
    )

    # OTP tokens table
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS otp_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT NOT NULL,
        expires_at DATETIME NOT NULL,
        attempts INTEGER DEFAULT 0,
        used BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    # Check and add 'instance_type' column if it doesn't exist
    cursor.execute("PRAGMA table_info(user_instances)")
    columns = [column[1] for column in cursor.fetchall()]
    if "instance_type" not in columns:
        cursor.execute(
            "ALTER TABLE user_instances ADD COLUMN instance_type TEXT DEFAULT 'rstudio'"
        )
        logger.info("Added 'instance_type' column to 'user_instances' table.")

    # Add resource limit columns if they don't exist
    if "memory_limit" not in columns:
        cursor.execute(
            "ALTER TABLE user_instances ADD COLUMN memory_limit TEXT DEFAULT '16g'"
        )
        logger.info("Added 'memory_limit' column to 'user_instances' table.")

    if "cpu_limit" not in columns:
        cursor.execute(
            "ALTER TABLE user_instances ADD COLUMN cpu_limit TEXT DEFAULT '2.0'"
        )
        logger.info("Added 'cpu_limit' column to 'user_instances' table.")

    if "storage_limit" not in columns:
        cursor.execute(
            "ALTER TABLE user_instances ADD COLUMN storage_limit TEXT DEFAULT '200G'"
        )
        logger.info("Added 'storage_limit' column to 'user_instances' table.")

    # Add session_days column if it doesn't exist
    if "session_days" not in columns:
        cursor.execute(
            "ALTER TABLE user_instances ADD COLUMN session_days INTEGER DEFAULT 2"
        )
        logger.info("Added 'session_days' column to 'user_instances' table.")

    # Migration: Update lab_name constraint to allow NULL values
    # Check if lab_name constraint needs to be updated (for existing databases)
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {col[1]: col for col in cursor.fetchall()}

    if "lab_name" in user_columns:
        # Check if lab_name has NOT NULL constraint by attempting to insert NULL
        try:
            cursor.execute(
                "INSERT INTO users (email, lab_name) VALUES ('test_null_check', NULL)"
            )
            cursor.execute("DELETE FROM users WHERE email = 'test_null_check'")
            logger.info("lab_name column already allows NULL values.")
        except sqlite3.IntegrityError:
            # If we get here, lab_name has NOT NULL constraint and needs migration
            logger.info("Migrating lab_name column to allow NULL values...")

            # Backup existing data
            cursor.execute("CREATE TEMPORARY TABLE users_backup AS SELECT * FROM users")

            # Drop and recreate the users table with updated schema
            cursor.execute("DROP TABLE users")
            cursor.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME,
                    lab_name TEXT
                )
                """
            )

            # Restore data from backup
            cursor.execute(
                """
                INSERT INTO users (id, email, is_admin, created_at, last_login, lab_name)
                SELECT id, email, is_admin, created_at, last_login, lab_name FROM users_backup
                """
            )

            # Drop backup table
            cursor.execute("DROP TABLE users_backup")
            logger.info("Successfully migrated lab_name column to allow NULL values.")

    # Create initial admin user if not exists
    admin_email = INITIAL_ADMIN_USERNAME
    cursor.execute("SELECT * FROM users WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (email, is_admin, created_at, lab_name) VALUES (?, ?, ?, ?)",
            (admin_email, True, datetime.now(timezone.utc), "GeDaC"),
        )
        logger.info(f"Admin user {admin_email} created.")
    conn.commit()
    conn.close()
    logger.info("Database initialized.")
