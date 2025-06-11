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
            raise HTTPException(
                status_code=500, detail="No available ports for RStudio."
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
            raise HTTPException(
                status_code=500, detail=f"Failed to start RStudio container: {e.stderr}"
            )

    except Exception as e:
        db_exc = get_db()
        db_exc.execute(
            "UPDATE rstudio_instances SET status = 'error' WHERE id = ?",
            (instance_id,),
        )
        db_exc.commit()
        db_exc.close()
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@app.post("/stop_rstudio/{instance_id}")
async def stop_rstudio_instance(
    request: Request,
    instance_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    db = get_db()
    instance = db.execute(
        "SELECT * FROM rstudio_instances WHERE id = ? AND user_id = ?",
        (instance_id, current_user["id"]),
    ).fetchone()

    if not instance or not instance["container_name"]:
        db.close()
        raise HTTPException(
            status_code=404, detail="Instance not found or not authorized"
        )

    container_name = instance["container_name"]

    try:
        # Attempt to stop the container
        logging.info(f"Attempting to stop container: {container_name}")
        stop_result = subprocess.run(
            ["docker", "stop", container_name], capture_output=True, text=True
        )
        if stop_result.returncode != 0:
            if "No such container" not in stop_result.stderr:
                logging.error(
                    f"Error stopping container {container_name}: {stop_result.stderr}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to stop RStudio container {container_name}: {stop_result.stderr}",
                )
            logging.info(
                f"Container {container_name} already stopped or does not exist (stop command)."
            )
        else:
            logging.info(f"Successfully stopped container: {container_name}")

        # Attempt to remove the container (it might have been auto-removed if started with --rm)
        logging.info(f"Attempting to remove container: {container_name}")
        rm_result = subprocess.run(
            ["docker", "rm", container_name], capture_output=True, text=True
        )
        if rm_result.returncode != 0:
            if "No such container" not in rm_result.stderr:
                logging.error(
                    f"Error removing container {container_name}: {rm_result.stderr}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to remove RStudio container {container_name}: {rm_result.stderr}",
                )
            logging.info(
                f"Container {container_name} already removed or does not exist (rm command)."
            )
        else:
            logging.info(f"Successfully removed container: {container_name}")

        db.execute(
            """UPDATE rstudio_instances SET status = 'stopped',
               container_id = NULL WHERE id = ?""",
            (instance_id,),
        )
        db.commit()
    except HTTPException:  # Re-raise HTTPExceptions directly
        raise
    except Exception as e:  # Catch any other unexpected errors
        logging.error(
            f"Unexpected error during stop/remove of {container_name}: {str(e)}"
        )
        # Potentially update status to 'error_stopping' in a real scenario
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred while stopping/removing RStudio container: {str(e)}",
        )
    finally:
        if db:  # Ensure db connection is closed
            db.close()

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
