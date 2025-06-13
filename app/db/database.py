# filepath: /Users/mani/work/rstudio-portal/app/db/database.py
import sqlite3
import logging
from datetime import datetime
from passlib.context import (
    CryptContext,
)  # Will be moved to auth, but needed by init_db for now
from app.core.config import (
    DATABASE_PATH,
    INITIAL_ADMIN_USERNAME,
    INITIAL_ADMIN_PASSWORD,
)

logger = logging.getLogger(__name__)
pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto"
)  # Temporary for init_db


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
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
    # Check and add 'instance_type' column if it doesn't exist
    cursor.execute("PRAGMA table_info(user_instances)")
    columns = [column[1] for column in cursor.fetchall()]
    if "instance_type" not in columns:
        cursor.execute(
            "ALTER TABLE user_instances ADD COLUMN instance_type TEXT DEFAULT 'rstudio'"
        )
        logger.info("Added 'instance_type' column to 'user_instances' table.")

    # Create initial admin user if not exists
    admin_username = INITIAL_ADMIN_USERNAME
    admin_password = INITIAL_ADMIN_PASSWORD  # Use from config
    cursor.execute("SELECT * FROM users WHERE username = ?", (admin_username,))
    if not cursor.fetchone():
        hashed_password = pwd_context.hash(admin_password)  # Use temporary pwd_context
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin, created_at, lab_name) VALUES (?, ?, ?, ?, ?)",
            (admin_username, hashed_password, True, datetime.utcnow(), "AdminLab"),
        )
        logger.info(f"Admin user {admin_username} created.")
    conn.commit()
    conn.close()
    logger.info("Database initialized.")
