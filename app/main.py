from fastapi import FastAPI, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3
import subprocess
import secrets
import os
import logging  # Added import for logging
from datetime import datetime  # Added import for datetime
import dotenv  # Import dotenv
from urllib.parse import quote  # Added for URL encoding messages
from passlib.context import CryptContext  # Import CryptContext
import re  # Added for email validation

# Load environment variables from .env file if it exists
dotenv.load_dotenv()

# Basic Configuration
BASE_DIR = (
    Path(__file__).resolve().parent.parent
)  # This is /app in the Docker container

# --- Path Configuration ---
# These paths are relative to BASE_DIR if not overridden by environment variables
# that specify absolute paths for container volumes.

# Database Path
# Example: /app/db_data/db.sqlite3
# (if DB_MOUNT_PATH=/app/db_data and DATABASE_FILENAME=db.sqlite3)
DB_MOUNT_PATH_STR = os.getenv("DB_MOUNT_PATH")
DATABASE_FILENAME = os.getenv("DATABASE_FILENAME", "db.sqlite3")
if DB_MOUNT_PATH_STR:
    DATABASE = Path(DB_MOUNT_PATH_STR) / DATABASE_FILENAME
else:
    DATABASE = BASE_DIR / DATABASE_FILENAME

# User Data Path
# Example: /app/user_data_mount (if USER_DATA_MOUNT_PATH=/app/user_data_mount)
USER_DATA_MOUNT_PATH_STR = os.getenv("USER_DATA_MOUNT_PATH")
if USER_DATA_MOUNT_PATH_STR:
    USER_DATA_BASE_DIR = Path(USER_DATA_MOUNT_PATH_STR)
else:
    USER_DATA_BASE_DIR = BASE_DIR / "user_data"  # Default to local user_data folder

# Docker Templates Path (usually part of the application code)
DOCKER_TEMPLATES_DIR_NAME = os.getenv("DOCKER_TEMPLATES_DIR_NAME", "docker_templates")
DOCKER_TEMPLATES_DIR = BASE_DIR / DOCKER_TEMPLATES_DIR_NAME

# Static and Templates paths (usually part of the application code)
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_JINJA_DIR = BASE_DIR / "templates"

# RStudio Configuration
RSTUDIO_MIN_PORT = int(
    os.getenv("RSTUDIO_MIN_PORT", "9002")
)  # Changed default from 8787
RSTUDIO_MAX_PORT = int(
    os.getenv("RSTUDIO_MAX_PORT", "9050")
)  # Changed default from 9000
RSTUDIO_DEFAULT_MEMORY = os.getenv("RSTUDIO_DEFAULT_MEMORY", "16g")
RSTUDIO_DEFAULT_CPUS = os.getenv("RSTUDIO_DEFAULT_CPUS", "2.0")
RSTUDIO_DOCKER_IMAGE = os.getenv("RSTUDIO_DOCKER_IMAGE", "rocker/rstudio:latest")
RSTUDIO_SESSION_EXPIRY_DAYS = int(os.getenv("RSTUDIO_SESSION_EXPIRY_DAYS", "14"))

# User/Admin Configuration
INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "admin")

# Uvicorn development server configuration
UVICORN_HOST = os.getenv("UVICORN_HOST", "0.0.0.0")
UVICORN_PORT = int(os.getenv("UVICORN_PORT", "8001"))  # Changed default from 8000

# New variables
SESSION_DURATION_HOURS = int(os.getenv("SESSION_DURATION_HOURS", "8"))
RSTUDIO_USER_DATA_BASE_PATH = os.getenv("RSTUDIO_USER_DATA_BASE_PATH", "./user_data")
RSTUDIO_IMAGE_NAME = os.getenv("RSTUDIO_IMAGE_NAME", "rocker/rstudio:latest")
RSTUDIO_PORT_RANGE_START = int(os.getenv("RSTUDIO_PORT_RANGE_START", "10000"))
RSTUDIO_PORT_RANGE_END = int(os.getenv("RSTUDIO_PORT_RANGE_END", "11000"))
RSTUDIO_BASE_URL_PATH = os.getenv("RSTUDIO_BASE_URL_PATH", "").rstrip("/")
RSTUDIO_USER_STORAGE_LIMIT = os.getenv(
    "RSTUDIO_USER_STORAGE_LIMIT"
)  # Existing variable

app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_JINJA_DIR)


# --- Database Helper ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rstudio_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            container_name TEXT NOT NULL,
            container_id TEXT,
            port INTEGER NOT NULL,
            password TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            status TEXT DEFAULT 'requested', -- requested, running, stopped, error
            stopped_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """
    )
    db.commit()
    db.close()


# Initialize DB on startup
init_db()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Authentication (Simplified - consider a robust solution for production) ---
# For simplicity, we'll store a "session" in a cookie.
# In a real app, use FastAPI's security utilities or a library like
# Flask-Login/FastAPI-Users.


def get_current_user(request: Request):
    username = request.cookies.get("username")
    if not username:
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    db.close()
    return user


# Dependency for requiring authentication
def get_current_active_user(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    return current_user


# --- Routes ---


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: dict = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    # Serve the new index.html for unauthenticated users
    return templates.TemplateResponse(
        "index.html", {"request": request, "title": "Welcome"}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "title": "Login"}
    )


@app.post("/login")
async def login_action(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    db.close()

    if user and pwd_context.verify(password, user["password"]):
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="username", value=username, httponly=True, samesite="Lax", secure=False
        )  # Set secure=True if using HTTPS
        return response
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid credentials", "title": "Login"},
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html", {"request": request, "title": "Register"}
    )


@app.post("/register")
async def register_action(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    username = username.strip()  # Remove leading/trailing whitespace

    # Validate username format if not the initial admin
    if username.lower() != INITIAL_ADMIN_USERNAME.lower():
        allowed_domains = [
            r"^[a-zA-Z0-9._%+-]+@visitor\.nus\.edu\.sg$",
            r"^[a-zA-Z0-9._%+-]+@u\.nus\.edu$",
            r"^[a-zA-Z0-9._%+-]+@nus\.edu\.sg$",
        ]

        is_valid_nus_email = False
        for domain_pattern in allowed_domains:
            if re.search(domain_pattern, username.lower()):
                is_valid_nus_email = True
                break

        if not is_valid_nus_email:
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "Username must be a valid NUS email address (e.g., @visitor.nus.edu.sg, @u.nus.edu, @nus.edu.sg).",
                    "title": "Register",
                },
            )

    db = get_db()
    try:
        hashed_password = pwd_context.hash(password)
        # Make the first registered user an admin,
        # or if username matches INITIAL_ADMIN_USERNAME
        is_admin_val = 0
        cursor_check = db.cursor()
        cursor_check.execute("SELECT COUNT(*) FROM users")
        user_count = cursor_check.fetchone()[0]
        if (
            user_count == 0 or username.lower() == INITIAL_ADMIN_USERNAME.lower()
        ):  # Use configured admin username
            is_admin_val = 1

        db.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
            (username, hashed_password, is_admin_val),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Username already taken",
                "title": "Register",
            },
        )
    finally:
        db.close()

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, current_user: dict = Depends(get_current_active_user)
):
    db = get_db()
    raw_instances = db.execute(  # Renamed to raw_instances
        "SELECT * FROM rstudio_instances WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],),
    ).fetchall()
    db.close()

    processed_instances = []
    for raw_instance in raw_instances:
        instance_dict = dict(
            raw_instance
        )  # Convert Row to dict for easier modification
        for field in ["created_at", "expires_at", "stopped_at"]:
            value = instance_dict.get(field)
            if value and isinstance(value, str):
                try:
                    # Handles "YYYY-MM-DD HH:MM:SS.ffffff" or "YYYY-MM-DDTHH:MM:SS.ffffff"
                    # and also "YYYY-MM-DD HH:MM:SS" if space is used as separator
                    instance_dict[field] = datetime.fromisoformat(
                        value.replace(" ", "T")
                    )
                except ValueError:
                    # Fallback for "YYYY-MM-DD HH:MM:SS" if fromisoformat fails (e.g. older Python or truly different format)
                    try:
                        instance_dict[field] = datetime.strptime(
                            value, "%Y-%m-%d %H:%M:%S"
                        )
                    except ValueError as e_strptime:
                        logging.warning(
                            f"Could not parse date string '{value}' for field '{field}' in instance ID {instance_dict.get('id')}. Error: {e_strptime}. Setting to None."
                        )
                        instance_dict[field] = (
                            None  # Set to None to prevent template error
                        )
            elif not isinstance(value, datetime) and value is not None:
                # If it's not a string, not a datetime, and not None (e.g., int/float from other storage types)
                logging.warning(
                    f"Unexpected type '{type(value)}' for date field '{field}' in instance ID {instance_dict.get('id')}. Setting to None."
                )
                instance_dict[field] = None

        processed_instances.append(instance_dict)

    # Get base URL for RStudio links
    base_url = str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "instances": processed_instances,  # Pass processed instances
            "base_url": base_url,
            "title": "Dashboard",
        },
    )


@app.post("/request_rstudio")
async def request_rstudio_instance(
    request: Request, current_user: dict = Depends(get_current_active_user)
):
    db = get_db()
    # Check if user already has a running or requested instance
    existing_instance_row = db.execute(  # Renamed for clarity and fetching status
        "SELECT id, status FROM rstudio_instances WHERE user_id = ? AND "
        "(status = 'running' OR status = 'requested')",
        (current_user["id"],),
    ).fetchone()

    if existing_instance_row:
        db.close()
        message = "You already have an active RStudio session or one is being prepared."
        if existing_instance_row["status"] == "requested":
            # E501: Line shortened
            message = (
                "An RStudio instance is currently being set up for you. "
                "Please check the dashboard again shortly."
            )
        elif existing_instance_row["status"] == "running":
            # E501: Line shortened
            message = (
                "You already have a running RStudio instance. "
                "Access it from the dashboard."
            )

        encoded_message = quote(message)  # URL encode the message
        # E501: Line shortened
        return RedirectResponse(
            url=f"/dashboard?message={encoded_message}",
            status_code=status.HTTP_302_FOUND,
        )

    username_full = current_user["username"]
    # Ensure username_part correctly extracts the part before '@'
    username_part = (
        username_full.split("@")[0] if "@" in username_full else username_full
    )

    # Construct container_name using the (hopefully) corrected username_part
    container_name = f"rstudio-{username_part}-{secrets.token_hex(4)}"
    rstudio_password = secrets.token_urlsafe(12)

    # Find an available port (very basic, improve for production)
    used_ports_rows = db.execute(
        "SELECT port FROM rstudio_instances WHERE status = 'running'"
    ).fetchall()
    used_ports = {row["port"] for row in used_ports_rows}

    host_port = RSTUDIO_MIN_PORT  # Use configured min port
    while host_port in used_ports:
        host_port += 1
        if host_port > RSTUDIO_MAX_PORT:  # Use configured max port
            db.close()
            # OLD: raise HTTPException(status_code=500, detail="No available ports for RStudio.")
            # NEW: Redirect with error
            error_message = quote(
                "No available ports for RStudio. Please try again later or contact an administrator."
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

    # Use username_part for the user-specific data directory path
    user_specific_data_dir = USER_DATA_BASE_DIR / username_part
    os.makedirs(user_specific_data_dir, exist_ok=True)

    # Store request in DB first
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO rstudio_instances
           (user_id, container_name, port, password, status)
           VALUES (?, ?, ?, ?, ?)""",
        (current_user["id"], container_name, host_port, rstudio_password, "requested"),
    )
    db.commit()
    instance_id = cursor.lastrowid
    db.close()

    try:
        # Run Docker container
        # This is a blocking call, for production use Celery or similar
        # background task manager
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--memory",
            RSTUDIO_DEFAULT_MEMORY,  # Use configured memory
            "--cpus",
            RSTUDIO_DEFAULT_CPUS,  # Use configured CPUs
            "-e",
            f"PASSWORD={rstudio_password}",
            "-v",
            f"{user_specific_data_dir.resolve()}:/home/rstudio",
            "--rm",
            "-p",
            f"{host_port}:8787",  # Map host port to RStudio's internal port 8787
            "-e",
            f"USER={username_part}",  # Use username_part for the RStudio USER env variable
            RSTUDIO_DOCKER_IMAGE,  # Use configured Docker image
        ]
        # Add storage limit if specified and not empty
        if RSTUDIO_USER_STORAGE_LIMIT and RSTUDIO_USER_STORAGE_LIMIT.strip():
            cmd.extend(["--storage-opt", f"size={RSTUDIO_USER_STORAGE_LIMIT}"])

        logging.info(
            f"Attempting to run RStudio container with command: {' '.join(cmd)}"
        )

        try:
            process_result = subprocess.run(
                cmd, check=True, capture_output=True, text=True
            )  # Corrected variable name
            container_id_full = process_result.stdout.strip()
            container_id_short = container_id_full[
                :12
            ]  # Docker typically shows short IDs

            db_update = get_db()
            db_update.execute(
                """UPDATE rstudio_instances
                   SET container_id = ?, status = 'running',
                       expires_at = datetime('now', ?)
                   WHERE id = ?""",
                (
                    container_id_short,
                    f"+{RSTUDIO_SESSION_EXPIRY_DAYS} days",
                    instance_id,
                ),  # Use configured expiry days
            )
            db_update.commit()
            db_update.close()

        except subprocess.CalledProcessError as e:
            logging.error(
                f"Failed to start RStudio container {container_name}. Error: {e.stderr}"
            )
            # Attempt to update DB status to 'error'
            db_update_error = get_db()
            try:
                db_update_error.execute(
                    "UPDATE rstudio_instances SET status = 'error' WHERE id = ?",
                    (instance_id,),
                )
                db_update_error.commit()
                logging.info(
                    f"Instance {instance_id} status updated to 'error' after subprocess failure."
                )
            except Exception as db_err_inner:
                logging.error(
                    f"Failed to update instance {instance_id} to status 'error' after subprocess failure: {db_err_inner}"
                )
            finally:
                db_update_error.close()

            error_message = quote(
                f"Failed to start RStudio container: {e.stderr.strip()}"
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

    except Exception as e:
        db_exc = get_db()
        db_exc.execute(
            "UPDATE rstudio_instances SET status = 'error' WHERE id = ?",
            (instance_id,),
        )
        db_exc.commit()
        db_exc.close()
        logging.error(
            f"Unexpected error in request_rstudio_instance for instance {instance_id}: {str(e)}",
            exc_info=True,
        )
        error_message = quote(
            f"An unexpected error occurred while preparing your RStudio instance: {str(e)}"
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}", status_code=status.HTTP_302_FOUND
        )

    return RedirectResponse(
        url="/dashboard?message="
        + quote(f"RStudio instance '{container_name}' is being prepared."),
        status_code=status.HTTP_302_FOUND,
    )


@app.post("/stop_rstudio/{instance_id}")
async def stop_rstudio_instance(
    instance_id: int,
    request: Request,
    current_user: dict = Depends(get_current_active_user),
):
    # Allow admin to stop any container, user can only stop their own
    db = get_db()
    instance = db.execute(
        "SELECT * FROM rstudio_instances WHERE id = ?",
        (instance_id,),
    ).fetchone()

    if not instance:
        db.close()
        error_message = quote("Instance not found.")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Only allow non-admins to stop their own containers
    if not current_user.get("is_admin") and instance["user_id"] != current_user["id"]:
        db.close()
        error_message = quote("You are not authorized to stop this instance.")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    container_name = instance["container_name"]
    logging.info(
        f"User '{current_user['username']}' attempting to stop instance ID {instance_id} (Container: {container_name})"
    )

    error_accumulator = []
    success_message_parts = []

    try:
        stop_cmd = ["docker", "stop", container_name]
        logging.info(f"Executing: {' '.join(stop_cmd)}")
        stop_process = subprocess.run(
            stop_cmd, capture_output=True, text=True, check=False
        )

        if stop_process.returncode == 0:
            logging.info(
                f"Successfully sent stop command to container {container_name}."
            )
            success_message_parts.append(
                f"Instance '{container_name}' stop command processed."
            )
        else:
            stderr_msg = stop_process.stderr.strip()
            logging.warning(f"Output from 'docker stop {container_name}': {stderr_msg}")
            if "No such container" in stderr_msg:
                logging.info(f"Container {container_name} was already removed.")
                success_message_parts.append(
                    f"Instance '{container_name}' was already stopped/removed."
                )
            elif "is already in progress" in stderr_msg.lower():
                logging.info(
                    f"Container {container_name} removal was already in progress."
                )
                success_message_parts.append(
                    f"Instance '{container_name}' stop/removal was already in progress."
                )
            else:
                error_accumulator.append(
                    f"Docker stop issue: {stderr_msg if stderr_msg else 'Unknown error from docker stop'}"
                )

        cursor = db.cursor()
        current_time_utc = datetime.utcnow()
        cursor.execute(
            "UPDATE rstudio_instances SET status = 'stopped', stopped_at = ? WHERE id = ?",
            (current_time_utc, instance_id),
        )
        db.commit()
        logging.info(
            f"Instance {instance_id} (Container: {container_name}) status updated to 'stopped', stopped_at={current_time_utc.isoformat()} in DB."
        )
        success_message_parts.append("Instance record updated to 'stopped'.")

    except Exception as e:
        logging.error(
            f"Unexpected critical error during stop operation for instance '{container_name}': {str(e)}",
            exc_info=True,
        )
        error_accumulator.append(f"Unexpected critical error: {str(e)}")
        if db:
            try:
                current_status_row = db.execute(
                    "SELECT status FROM rstudio_instances WHERE id = ?", (instance_id,)
                ).fetchone()
                if current_status_row and current_status_row["status"] != "stopped":
                    cursor = db.cursor()
                    cursor.execute(
                        "UPDATE rstudio_instances SET status = 'error' WHERE id = ?",
                        (instance_id,),
                    )
                    db.commit()
                    logging.info(
                        f"Instance {instance_id} status updated to 'error' due to critical exception."
                    )
            except Exception as db_err:
                logging.error(
                    f"Failed to update instance status to 'error' during critical exception handling: {db_err}"
                )

    finally:
        if db:
            db.close()

    if error_accumulator:
        full_error_detail = "; ".join(error_accumulator)
        combined_message = f"Error(s) stopping instance '{container_name}': {full_error_detail}. {' '.join(success_message_parts)}"
        final_message = quote(combined_message)
        return RedirectResponse(
            url=f"/dashboard?error={final_message}", status_code=status.HTTP_302_FOUND
        )
    else:
        final_success_message = quote(" ".join(success_message_parts))
        return RedirectResponse(
            url=f"/dashboard?message={final_success_message}",
            status_code=status.HTTP_302_FOUND,
        )


@app.post("/delete_rstudio/{instance_id}", name="delete_rstudio_instance")
async def delete_rstudio_instance_action(
    request: Request,
    instance_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    # Only allow admin to delete records
    if not current_user.get("is_admin"):
        error_message = quote("Only admin users can delete instance records.")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )
    db = get_db()
    instance = db.execute(
        "SELECT * FROM rstudio_instances WHERE id = ?",
        (instance_id,),
    ).fetchone()

    if not instance:
        db.close()
        error_message = quote(
            "Instance not found or you are not authorized to delete it."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        db.execute("DELETE FROM rstudio_instances WHERE id = ?", (instance_id,))
        db.commit()
        success_message = quote(
            f"Instance record '{instance['container_name']}' deleted successfully."
        )
        return RedirectResponse(
            url=f"/dashboard?message={success_message}",
            status_code=status.HTTP_302_FOUND,
        )
    except sqlite3.Error as e:
        db.rollback()
        error_message = quote(f"Database error while deleting instance: {str(e)}")
        logging.error(f"Failed to delete instance ID {instance_id} from database: {e}")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )
    finally:
        db.close()


@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("username")
    return response


# --- Admin (very basic, expand significantly) ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    db: sqlite3.Connection = Depends(get_db),
):
    if not current_user or not current_user.get("is_admin"):
        # Redirect to login if not logged in, or to dashboard if not admin
        if not current_user:
            return RedirectResponse(
                url="/login?error=" + quote("Please log in to view this page."),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        else:
            return RedirectResponse(
                url="/dashboard?error="
                + quote("You are not authorized to view this page."),
                status_code=status.HTTP_303_SEE_OTHER,
            )

    users_cursor = db.execute("SELECT id, username, is_admin FROM users")
    users = users_cursor.fetchall()

    instances_cursor = db.execute(
        "SELECT i.id, u.username, i.container_name, i.container_id, i.port, i.status, i.created_at, i.expires_at, i.stopped_at FROM rstudio_instances i JOIN users u ON i.user_id = u.id"
    )
    instances_raw = instances_cursor.fetchall()
    instances = []
    for inst_raw_row in instances_raw:  # Changed variable name to avoid conflict
        inst = dict(inst_raw_row)  # Convert row to dict for easier manipulation
        # Ensure we are accessing the correct date fields from the 'i' (instances) table alias
        for field_name in ["created_at", "expires_at", "stopped_at"]:
            value = inst.get(
                field_name
            )  # Direct access, assuming dict keys match column names from SELECT
            if value and isinstance(value, str):
                try:
                    inst[field_name] = datetime.fromisoformat(value.replace(" ", "T"))
                except ValueError:
                    try:
                        inst[field_name] = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError as e_strptime:
                        logging.warning(
                            f"Admin: Could not parse date string '{value}' for field '{field_name}' in instance ID {inst.get('id')}. Error: {e_strptime}. Setting to None."
                        )
                        inst[field_name] = None
            elif not isinstance(value, datetime) and value is not None:
                logging.warning(
                    f"Admin: Unexpected type '{type(value)}' for date field '{field_name}' in instance ID {inst.get('id')}. Setting to None."
                )
                inst[field_name] = None
        instances.append(inst)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "users": users,
            "instances": instances,
            "title": "Admin Dashboard",
        },
    )


if __name__ == "__main__":
    import uvicorn

    # Make sure USER_DATA_BASE_DIR exists
    os.makedirs(USER_DATA_BASE_DIR, exist_ok=True)
    # For development, run with:
    # uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    uvicorn.run(
        app, host=UVICORN_HOST, port=UVICORN_PORT
    )  # Use configured host and port
