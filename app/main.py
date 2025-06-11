from fastapi import FastAPI, Request, Form, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3
import subprocess
import os
import secrets
import logging  # Ensure logging is imported
import dotenv  # Import dotenv
from urllib.parse import quote  # Added for URL encoding messages
from passlib.context import CryptContext  # Import CryptContext

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
    instances = db.execute(
        "SELECT * FROM rstudio_instances WHERE user_id = ?", (current_user["id"],)
    ).fetchall()
    db.close()

    # Get base URL for RStudio links
    base_url = str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "instances": instances,
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

    username = current_user["username"]
    container_name = f"rstudio-{username}-{secrets.token_hex(4)}"
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

    user_specific_data_dir = USER_DATA_BASE_DIR / username
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
            f"USER={username}",  # Sets the RStudio user to the portal username
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
    request: Request,
    instance_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    db = None  # Initialize db to None for robust finally block
    instance_container_name_for_logging = (
        "N/A"  # For logging in case instance fetch fails
    )
    try:
        db = get_db()
        instance = db.execute(
            "SELECT * FROM rstudio_instances WHERE id = ? AND user_id = ?",
            (instance_id, current_user["id"]),
        ).fetchone()

        if not instance or not instance["container_name"]:
            if db:  # Close connection if open
                db.close()
            error_message = quote(
                "Instance not found or you are not authorized to stop it."
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

        container_name = instance["container_name"]
        instance_container_name_for_logging = container_name  # Set for logging
        docker_errors = []  # To collect messages from Docker command failures

        # Attempt to stop the container
        logging.info(
            f"Attempting to stop container: {container_name} (Instance ID: {instance_id})"
        )
        stop_result = subprocess.run(
            ["docker", "stop", container_name], capture_output=True, text=True
        )
        if stop_result.returncode == 0:
            logging.info(
                f"Successfully stopped container: {container_name}. It will be auto-removed due to --rm flag."
            )
        elif "No such container" in stop_result.stderr:
            logging.info(
                f"Container {container_name} already stopped/removed or did not exist (stop command)."
            )
        else:
            logging.error(
                f"Error stopping container {container_name}: {stop_result.stderr.strip()}"
            )
            docker_errors.append(f"Failed to stop: {stop_result.stderr.strip()}")

        # Removed explicit 'docker rm' section as containers are started with --rm

        # Update the database status to 'stopped'
        db.execute(
            "UPDATE rstudio_instances SET status = 'stopped', container_id = NULL WHERE id = ?",
            (instance_id,),
        )
        db.commit()
        logging.info(
            f"Instance {instance_id} ({container_name}) DB status updated to 'stopped'."
        )

        if docker_errors:
            combined_error_message = ". ".join(docker_errors)
            logging.error(
                f"Docker stop operation for {container_name} (Instance ID: {instance_id}) resulted in errors: {combined_error_message}"
            )
            error_message = quote(
                f"Error(s) during stop of RStudio instance '{container_name}': {combined_error_message}. The instance record has been marked as 'stopped'."
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

        logging.info(
            f"Successfully processed stop for {container_name} (Instance ID: {instance_id}). Container will be auto-removed."
        )
        success_message = quote(
            f"Instance '{container_name}' stopped successfully. The container will be automatically removed."
        )
        return RedirectResponse(
            url=f"/dashboard?message={success_message}",
            status_code=status.HTTP_302_FOUND,
        )

    except HTTPException as e:  # Catch any other HTTPExceptions
        # This is a safeguard. Ideally, all user-facing HTTPExceptions are converted to redirects.
        # If one is raised and not caught before this, log it and redirect.
        logging.error(
            f"Unexpected HTTPException during stop/remove for instance ID {instance_id}: {str(e)}",
            exc_info=True,
        )
        error_message = quote(
            "An unexpected issue occurred. Please check the dashboard for status."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}", status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        # Catch any other unexpected Python errors
        logging.error(
            f"Unexpected Python error during stop/remove of container for instance ID {instance_id} (name: {instance_container_name_for_logging}): {str(e)}",
            exc_info=True,  # Log full traceback
        )
        # Attempt to update DB status to 'error_stopping' for unexpected issues
        if db and instance_id is not None:
            try:
                # Ensure 'db' is the connection from the current try block, not a new one unless necessary
                # and ensure it's open. The 'finally' block handles closing.
                # If 'db' is already closed due to an earlier part of this try-except, this might fail or use a closed connection.
                # However, if 'db' was opened at the start of 'try' and the error is not db related, it should be open.
                current_db_conn = (
                    db  # Use the existing connection if available and not None
                )
                if (
                    current_db_conn is None
                ):  # Fallback if db was None (e.g. get_db() failed)
                    current_db_conn = get_db()

                current_db_conn.execute(
                    "UPDATE rstudio_instances SET status = 'error_stopping', container_id = NULL WHERE id = ?",
                    (instance_id,),
                )
                current_db_conn.commit()
                logging.info(
                    f"Instance {instance_id} status updated to 'error_stopping' due to unexpected Python error."
                )
                if current_db_conn is not db:  # if we opened a new connection
                    current_db_conn.close()

            except Exception as db_err:
                logging.error(
                    f"Failed to update instance {instance_id} status in DB during unexpected Python error handling: {db_err}"
                )

        error_message = quote(
            "An unexpected server error occurred while trying to stop/remove RStudio instance. Please check server logs. The instance may be in an inconsistent state."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}", status_code=status.HTTP_302_FOUND
        )
    finally:
        if db:
            db.close()

    # This line should not be reached if all paths in try/except return a RedirectResponse.
    # Kept for safety, but implies a logical flaw if hit.
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@app.post("/delete_rstudio/{instance_id}", name="delete_rstudio_instance")
async def delete_rstudio_instance_action(  # Renamed function to avoid conflict
    request: Request,
    instance_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    db = get_db()
    instance = db.execute(
        "SELECT * FROM rstudio_instances WHERE id = ? AND user_id = ?",
        (instance_id, current_user["id"]),
    ).fetchone()

    if not instance:
        db.close()
        # E501: Line shortened
        error_message = quote(
            "Instance not found or you are not authorized to delete it."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Only allow deletion of stopped, expired, or errored instances by the user
    # Actual container should be stopped/removed by the stop_rstudio_instance
    if instance["status"] not in ["stopped", "expired", "error", "stopped_expired"]:
        db.close()
        # E501: Line shortened
        error_message = quote(
            f"Instance in '{instance['status']}' state. Stop it first to delete."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        db.execute("DELETE FROM rstudio_instances WHERE id = ?", (instance_id,))
        db.commit()
        # E501: Line shortened
        success_message = quote(
            f"Instance record '{instance['container_name']}' deleted successfully."
        )
        return RedirectResponse(
            url=f"/dashboard?message={success_message}",
            status_code=status.HTTP_302_FOUND,
        )
    except sqlite3.Error as e:
        db.rollback()  # Rollback in case of error
        # E501: Line shortened
        error_message = quote(f"Database error while deleting instance: {str(e)}")
        # Log the error server-side
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
    request: Request, current_user: dict = Depends(get_current_active_user)
):
    if not current_user or not current_user["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for admin panel",
        )

    db = get_db()
    all_users = db.execute("SELECT id, username, is_admin FROM users").fetchall()
    all_instances = db.execute(
        """
        SELECT ri.*, u.username
        FROM rstudio_instances ri
        JOIN users u ON ri.user_id = u.id
    """
    ).fetchall()
    db.close()
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "users": all_users,
            "instances": all_instances,
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
