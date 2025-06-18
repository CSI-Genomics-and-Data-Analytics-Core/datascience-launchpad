# filepath: /Users/mani/work/rstudio-portal/app/db/database.py
import sqlite3
import logging
from datetime import datetime
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
        lab_name TEXT NOT NULL
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

    # Create initial admin user if not exists
    admin_email = INITIAL_ADMIN_USERNAME
    cursor.execute("SELECT * FROM users WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (email, is_admin, created_at, lab_name) VALUES (?, ?, ?, ?)",
            (admin_email, True, datetime.utcnow(), "AdminLab"),
        )
        logger.info(f"Admin user {admin_email} created.")
    conn.commit()
    conn.close()
    logger.info("Database initialized.")
