import os
import logging
import secrets
import subprocess
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

# Import configurations, database, and auth functions from new modules
from app.core.config import (
    USER_DATA_BASE_DIR,
    STATIC_DIR,
    TEMPLATES_JINJA_DIR,
    RSTUDIO_MIN_PORT,
    RSTUDIO_MAX_PORT,
    RSTUDIO_DEFAULT_MEMORY,
    RSTUDIO_DEFAULT_CPUS,
    RSTUDIO_DOCKER_IMAGE,
    JUPYTER_DOCKER_IMAGE,
    JUPYTER_MIN_PORT,
    JUPYTER_MAX_PORT,
    JUPYTER_DEFAULT_MEMORY,
    JUPYTER_DEFAULT_CPUS,
    INITIAL_ADMIN_USERNAME,  # Used for admin detection
    RSTUDIO_USER_STORAGE_LIMIT,
    MAX_CONCURRENT_SESSIONS,
    DEFAULT_SESSION_DAYS,
    LAB_NAMES,
)
from app.db.database import get_db, init_db
from app.auth.security import (
    get_current_user,
    get_current_active_user,
    create_user_session,
    is_valid_nus_email,
)
from app.auth.otp import get_otp_service


class UserMiddleware(BaseHTTPMiddleware):
    """Middleware to populate request.state.user for templates"""

    async def dispatch(self, request: Request, call_next):
        # Get user from cookies and populate request.state
        user = get_current_user(request)
        request.state.user = user
        response = await call_next(request)
        return response


app = FastAPI()

# Add user middleware
app.add_middleware(UserMiddleware)

# Mount static files using STATIC_DIR from config
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# Setup templates using TEMPLATES_JINJA_DIR from config
templates = Jinja2Templates(directory=str(TEMPLATES_JINJA_DIR))

logger = logging.getLogger(__name__)  # Keep logger setup

# Call init_db from the imported module at startup
init_db()


# --- Helper Functions ---


def ensure_user_data_directory(user_dir: Path) -> bool:
    """
    Ensure a user data directory exists for RStudio containers.
    
    Creates the directory if it doesn't exist. Attempts to set ownership to UID 1000
    (rstudio user in Docker containers) but continues if this fails.
    
    Args:
        user_dir: Path to the user-specific data directory to create/ensure
        
    Returns:
        True if directory exists and is usable, False otherwise
    """
    try:
        # Ensure parent directory exists first
        user_dir.parent.mkdir(parents=True, exist_ok=True)
        # Create user-specific directory if it doesn't exist
        user_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to set ownership to UID 1000 (rstudio user) - only if we can
        try:
            os.chown(user_dir, 1000, 1000)
            os.chmod(user_dir, 0o755)
            logging.info(f"Set ownership of '{user_dir}' to 1000:1000")
        except (PermissionError, OSError) as chown_err:
            # Can't chown - try chmod to 777 as fallback
            try:
                os.chmod(user_dir, 0o777)
                logging.warning(f"Could not chown '{user_dir}': {chown_err}. Set to 777 instead.")
            except (PermissionError, OSError):
                # Can't even chmod - directory might still work if permissions are already OK
                logging.warning(f"Could not change permissions on '{user_dir}'. Continuing anyway.")
        
        logging.info(f"User data directory '{user_dir}' is ready")
        return True
        
    except PermissionError as perm_err:
        logging.error(f"Permission denied for user data directory '{user_dir}': {perm_err}")
        return False
    except OSError as os_err:
        logging.error(f"OS error with user data directory '{user_dir}': {os_err}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error with user data directory '{user_dir}': {e}", exc_info=True)
        return False


# --- Routes ---


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: dict = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "index.html", {"request": request, "title": "Welcome"}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    message = request.query_params.get("message")
    context = {"request": request, "title": "Login"}
    if message:
        context["success"] = message
    return templates.TemplateResponse("login.html", context)


@app.post("/request-otp")
async def request_otp_action(request: Request, email: str = Form(...)):
    email = email.strip().lower()

    # Validate email format
    if not is_valid_nus_email(email):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Please enter a valid NUS email address (e.g., user@nus.edu.sg, user@u.nus.edu, user@visitor.nus.edu.sg)",
                "title": "Login",
                "email_value": email,
            },
        )

    # Check if user exists, if not create them automatically
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user:
        # Auto-register new user with default lab
        try:
            cursor = db.cursor()

            # Determine if the user should be admin (first user)
            is_admin_val = 0
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            if user_count == 0 or email.lower() == INITIAL_ADMIN_USERNAME.lower():
                is_admin_val = 1

            # Create user account with no lab initially - user will select lab on first login
            cursor.execute(
                "INSERT INTO users (email, is_admin, created_at, lab_name) VALUES (?, ?, ?, ?)",
                (email, is_admin_val, datetime.now(timezone.utc), None),
            )
            db.commit()
            logger.info(f"Auto-registered new user: {email}")

        except sqlite3.Error as e:
            logger.error(f"Error auto-registering user {email}: {str(e)}")
            db.rollback()
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "An error occurred. Please try again.",
                    "title": "Login",
                    "email_value": email,
                },
            )

    db.close()

    # Request OTP (works for both existing and newly created users)
    otp_service = get_otp_service()
    success, message = otp_service.create_otp(email)

    if success:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "success": message,
                "title": "Login",
                "email_value": email,
                "otp_sent": True,
            },
        )
    else:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": message,
                "title": "Login",
                "email_value": email,
            },
        )


@app.post("/verify-otp")
async def verify_otp_action(
    request: Request,
    email: str = Form(...),
    otp_code: str = Form(...),
    remember_me: bool = Form(False),
):
    email = email.strip().lower()
    otp_code = otp_code.strip()

    # Verify OTP
    otp_service = get_otp_service()
    success, message = otp_service.verify_otp(email, otp_code)

    if success:
        # Update last login
        db = get_db()
        db.execute(
            "UPDATE users SET last_login = ? WHERE email = ?",
            (datetime.now(timezone.utc), email),
        )
        db.commit()
        db.close()

        # Create session
        session_data = create_user_session(email, remember_me)

        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="user_email",
            value=email,
            httponly=True,
            samesite="Lax",
            secure=False,  # Set to True in production with HTTPS
            expires=session_data["expires_at"] if remember_me else None,
        )
        response.set_cookie(
            key="session_expires",
            value=session_data["expires_at"].isoformat(),
            httponly=True,
            samesite="Lax",
            secure=False,  # Set to True in production with HTTPS
            expires=session_data["expires_at"] if remember_me else None,
        )
        return response
    else:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": message,
                "title": "Login",
                "email_value": email,
                "otp_sent": True,
            },
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, current_user: dict = Depends(get_current_active_user)
):  # Uses imported get_current_active_user

    db = get_db()  # Uses imported get_db

    # For non-admin users, only show running sessions
    # For admin users in the admin dashboard, show all sessions
    if current_user["is_admin"]:
        # Admin users can see all their sessions on their personal dashboard too
        raw_instances = db.execute(  # Renamed to raw_instances
            "SELECT * FROM user_instances WHERE user_id = ? ORDER BY created_at DESC",
            (current_user["id"],),
        ).fetchall()
    else:
        # Regular users only see running sessions
        raw_instances = db.execute(
            "SELECT * FROM user_instances WHERE user_id = ? AND status = 'running' ORDER BY created_at DESC",
            (current_user["id"],),
        ).fetchall()

    # Get current session count for display before closing db
    current_running_sessions = db.execute(
        "SELECT COUNT(*) as count FROM user_instances WHERE status = 'running'"
    ).fetchone()["count"]

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
            "memory_limit": RSTUDIO_DEFAULT_MEMORY,  # Uses imported RSTUDIO_DEFAULT_MEMORY
            "cpu_limit": RSTUDIO_DEFAULT_CPUS,  # Uses imported RSTUDIO_DEFAULT_CPUS
            "storage_limit": RSTUDIO_USER_STORAGE_LIMIT,  # Uses imported RSTUDIO_USER_STORAGE_LIMIT
            "jupyter_memory_limit": JUPYTER_DEFAULT_MEMORY,  # Uses imported JUPYTER_DEFAULT_MEMORY
            "jupyter_cpu_limit": JUPYTER_DEFAULT_CPUS,  # Uses imported JUPYTER_DEFAULT_CPUS
            "current_sessions": current_running_sessions,  # Current running sessions
            "max_sessions": MAX_CONCURRENT_SESSIONS,  # Maximum allowed sessions
            "default_session_days": DEFAULT_SESSION_DAYS,  # Default session duration
            "lab_names": LAB_NAMES,  # Available lab names for selection
        },
    )


@app.get("/select-lab", response_class=HTMLResponse)
async def select_lab_page(
    request: Request, current_user: dict = Depends(get_current_active_user)
):
    """Show lab selection page for new users"""
    return templates.TemplateResponse(
        "select_lab.html",
        {
            "request": request,
            "user": current_user,
            "lab_names": LAB_NAMES,
            "title": "Select Your Lab",
        },
    )


@app.post("/select-lab")
async def select_lab(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    lab_name: str = Form(...),
):
    """Handle lab selection for users"""
    if lab_name not in LAB_NAMES:
        return JSONResponse(
            content={"success": False, "error": "Invalid lab selection"},
            status_code=400,
        )

    # Update user's lab selection
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET lab_name = ? WHERE id = ?",
            (lab_name, current_user["id"]),
        )
        db.commit()

        return JSONResponse(
            content={"success": True, "message": f"Lab updated to {lab_name}"}
        )

    except sqlite3.Error as e:
        logger.error(f"Error updating lab for user {current_user['email']}: {str(e)}")
        db.rollback()

        return JSONResponse(
            content={"success": False, "error": "Database error occurred"},
            status_code=500,
        )
    finally:
        db.close()


@app.post("/request_rstudio")
async def request_rstudio_instance(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    memory_limit: str = Form(RSTUDIO_DEFAULT_MEMORY),
    cpu_limit: str = Form(RSTUDIO_DEFAULT_CPUS),
    storage_limit: str = Form(RSTUDIO_USER_STORAGE_LIMIT),
    session_days: int = Form(DEFAULT_SESSION_DAYS),
):  # Uses imported get_current_active_user
    db = get_db()  # Uses imported get_db
    # Check if user already has a running or requested instance
    existing_instance_row = db.execute(  # Renamed for clarity and fetching status
        "SELECT id, status FROM user_instances WHERE user_id = ? AND "
        "(status = 'running' OR status = 'requested')",
        (current_user["id"],),
    ).fetchone()

    if existing_instance_row:
        db.close()
        message = "You already have an active session or one is being prepared."
        if existing_instance_row["status"] == "requested":
            # E501: Line shortened
            message = (
                "An instance is currently being set up for you. "
                "Please check the dashboard again shortly."
            )
        elif existing_instance_row["status"] == "running":
            # E501: Line shortened
            message = (
                "You already have a running instance. "
                "Please stop the current one before launching a new one."
            )

        encoded_message = quote(message)  # URL encode the message
        # E501: Line shortened
        return RedirectResponse(
            url=f"/dashboard?message={encoded_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Check global session limit
    total_running_sessions = db.execute(
        "SELECT COUNT(*) as count FROM user_instances WHERE status = 'running'"
    ).fetchone()["count"]

    if total_running_sessions >= MAX_CONCURRENT_SESSIONS:
        db.close()
        message = (
            f"System capacity reached. Currently {total_running_sessions}/{MAX_CONCURRENT_SESSIONS} sessions are running. "
            "Please wait for another user to stop their session before requesting a new one."
        )
        encoded_message = quote(message)
        return RedirectResponse(
            url=f"/dashboard?error={encoded_message}",
            status_code=status.HTTP_302_FOUND,
        )

    email_full = current_user["email"]
    # Extract the part before '@' for container and directory naming
    email_username = email_full.split("@")[0] if "@" in email_full else email_full

    # Construct container_name using the email username part
    container_name = f"rstudio-{email_username}-{secrets.token_hex(4)}"
    rstudio_password = secrets.token_urlsafe(12)

    # Find an available port (very basic, improve for production)
    used_ports_rows = db.execute(
        "SELECT port FROM user_instances WHERE status = 'running'"
    ).fetchall()
    used_ports = {row["port"] for row in used_ports_rows}

    host_port = RSTUDIO_MIN_PORT  # Use imported RSTUDIO_MIN_PORT
    while host_port in used_ports:
        host_port += 1
        if host_port > RSTUDIO_MAX_PORT:  # Use imported RSTUDIO_MAX_PORT
            db.close()
            # Return redirect with error message instead of raising exception
            error_message = quote(
                "No available ports for RStudio. Please try again later or contact an administrator."
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

    # Use email_username for the user-specific data directory path
    user_specific_data_dir = (
        USER_DATA_BASE_DIR / email_username
    )  # Uses imported USER_DATA_BASE_DIR
    
    # Ensure user data directory exists with proper permissions
    if not ensure_user_data_directory(user_specific_data_dir):
        db.close()
        # Safely get directory permissions info for logging
        perm_info = "unknown"
        try:
            if USER_DATA_BASE_DIR.exists():
                perm_info = oct(USER_DATA_BASE_DIR.stat().st_mode)
            else:
                perm_info = "does not exist"
        except (OSError, PermissionError):
            perm_info = "cannot access (permission denied)"
        
        logging.error(
            f"Failed to ensure user data directory '{user_specific_data_dir}'. "
            f"Parent directory '{USER_DATA_BASE_DIR}' permissions: {perm_info}"
        )
        error_message = quote(
            "Permission error: Unable to create user data directory. Please contact an administrator."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Store request in DB first
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO user_instances
           (user_id, container_name, port, password, status, instance_type, memory_limit, cpu_limit, storage_limit, session_days)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            current_user["id"],
            container_name,
            host_port,
            rstudio_password,
            "requested",
            "rstudio",
            memory_limit,
            cpu_limit,
            storage_limit,
            session_days,
        ),
    )
    db.commit()
    instance_id = (
        cursor.lastrowid
    )  # Remove parentheses; lastrowid is a property, not a method
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
            memory_limit,  # Use custom memory limit
            "--cpus",
            cpu_limit,  # Use custom CPU limit
            "-e",
            f"PASSWORD={rstudio_password}",
            "-v",
            f"{user_specific_data_dir.resolve()}:/home/rstudio",
            "--rm",
            "-p",
            f"{host_port}:8787",  # Map host port to RStudio's internal port 8787
            # "-e",
            # f"USER={email_username}",  # Use email_username for the RStudio USER env variable
        ]
        cmd.append(RSTUDIO_DOCKER_IMAGE)  # Use imported RSTUDIO_DOCKER_IMAGE

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

            db_update = get_db()  # Uses imported get_db
            db_update.execute(
                """UPDATE user_instances
                   SET container_id = ?, status = 'running',
                       expires_at = datetime('now', ?)
                   WHERE id = ?""",
                (
                    container_id_short,
                    f"+{session_days} days",  # Use custom session_days
                    instance_id,
                ),
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
                    "UPDATE user_instances SET status = 'error' WHERE id = ?",
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
            "UPDATE user_instances SET status = 'error' WHERE id = ?",
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


@app.post("/request_jupyterlab")
async def request_jupyterlab_instance(
    request: Request,
    current_user: dict = Depends(get_current_active_user),
    memory_limit: str = Form(JUPYTER_DEFAULT_MEMORY),
    cpu_limit: str = Form(JUPYTER_DEFAULT_CPUS),
    storage_limit: str = Form(RSTUDIO_USER_STORAGE_LIMIT),
    session_days: int = Form(DEFAULT_SESSION_DAYS),
):  # Uses imported get_current_active_user
    db = get_db()  # Uses imported get_db
    existing_instance_row = db.execute(
        "SELECT id, status FROM user_instances WHERE user_id = ? AND "
        "(status = 'running' OR status = 'requested')",  # This check might need refinement if users can have one of each
        (current_user["id"],),
    ).fetchone()

    # For now, let's assume a user can have one active instance of any type.
    # This can be changed later to allow one RStudio AND one JupyterLab.
    if existing_instance_row:
        db.close()
        message = "You already have an active session or one is being prepared."
        if existing_instance_row["status"] == "requested":
            # E501: Line shortened
            message = (
                "An instance is currently being set up for you. "
                "Please check the dashboard again shortly."
            )
        elif existing_instance_row["status"] == "running":
            # E501: Line shortened
            message = (
                "You already have a running instance. "
                "Please stop the current one before launching a new one."
            )

        encoded_message = quote(message)  # URL encode the message
        # E501: Line shortened
        return RedirectResponse(
            url=f"/dashboard?message={encoded_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Check global session limit
    total_running_sessions = db.execute(
        "SELECT COUNT(*) as count FROM user_instances WHERE status = 'running'"
    ).fetchone()["count"]

    if total_running_sessions >= MAX_CONCURRENT_SESSIONS:
        db.close()
        message = (
            f"System capacity reached. Currently {total_running_sessions}/{MAX_CONCURRENT_SESSIONS} sessions are running. "
            "Please wait for another user to stop their session before requesting a new one."
        )
        encoded_message = quote(message)
        return RedirectResponse(
            url=f"/dashboard?error={encoded_message}",
            status_code=status.HTTP_302_FOUND,
        )

    email_full = current_user["email"]
    email_username = email_full.split("@")[0] if "@" in email_full else email_full
    container_name = f"jupyterlab-{email_username}-{secrets.token_hex(4)}"
    jupyter_token = secrets.token_urlsafe(24)  # Generate a secure token

    # Find an available port for JupyterLab
    used_ports_rows = db.execute(
        "SELECT port FROM user_instances WHERE status = 'running'"
    ).fetchall()
    used_ports = {row["port"] for row in used_ports_rows}

    host_port = JUPYTER_MIN_PORT  # Use imported JUPYTER_MIN_PORT
    while host_port in used_ports:
        host_port += 1
        if host_port > JUPYTER_MAX_PORT:  # Use imported JUPYTER_MAX_PORT
            db.close()
            error_message = quote(
                "No available ports for JupyterLab. Please try again later or contact an administrator."
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

    # Use email_username for the user-specific data directory path
    user_specific_data_dir = (
        USER_DATA_BASE_DIR / email_username
    )  # Uses imported USER_DATA_BASE_DIR
    
    # Ensure user data directory exists with proper permissions
    if not ensure_user_data_directory(user_specific_data_dir):
        db.close()
        # Safely get directory permissions info for logging
        perm_info = "unknown"
        try:
            if USER_DATA_BASE_DIR.exists():
                perm_info = oct(USER_DATA_BASE_DIR.stat().st_mode)
            else:
                perm_info = "does not exist"
        except (OSError, PermissionError):
            perm_info = "cannot access (permission denied)"
        
        logging.error(
            f"Failed to ensure user data directory '{user_specific_data_dir}'. "
            f"Parent directory '{USER_DATA_BASE_DIR}' permissions: {perm_info}"
        )
        error_message = quote(
            "Permission error: Unable to create user data directory. Please contact an administrator."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Store request in DB first
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO user_instances
           (user_id, container_name, port, password, status, instance_type, memory_limit, cpu_limit, storage_limit, session_days)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            current_user["id"],
            container_name,
            host_port,
            jupyter_token,
            "requested",
            "jupyterlab",
            memory_limit,
            cpu_limit,
            storage_limit,
            session_days,
        ),
    )
    db.commit()
    instance_id = (
        cursor.lastrowid
    )  # Remove parentheses; lastrowid is a property, not a method
    db.close()

    try:
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--memory",
            memory_limit,  # Use custom memory limit
            "--cpus",
            cpu_limit,  # Use custom CPU limit
            "-e",
            f"JUPYTER_TOKEN={jupyter_token}",  # Pass the token
            "-e",
            "JUPYTER_ENABLE_LAB=yes",
            # Grant sudo access if needed, or manage permissions carefully
            # "-e", "GRANT_SUDO=yes",
            # "-u", "root", # If running as root to chown, then drop privileges. Or use NB_UID/NB_GID.
            # For simplicity, let jovyan user own the work directory.
            # Ensure user_specific_data_dir has correct permissions for Docker to write if jovyan is not root.
            "-v",
            f"{user_specific_data_dir.resolve()}:/home/jovyan/work",
            "--rm",
            "-p",
            f"{host_port}:8888",  # JupyterLab typically runs on 8888
            "-e",
            f"JUPYTER_TOKEN={jupyter_token}",  # Pass the token
            # For JupyterLab, the user inside the container is often 'jovyan' or configurable.
            # The UID/GID mapping is crucial. The datascience-notebook often uses UID 1000 (jovyan).
            # We need to ensure the mounted directory has correct permissions for this user.
            # Example: "-u", "1000:100", # Run as jovyan user (UID 1000) and users group (GID 100)
            # This might need to be configurable or handled by the Docker image itself.
            # For now, let's assume the image handles user permissions or the user_specific_data_dir is world-writable enough.
            # The -e NB_USER=$email_username and -e NB_UID=$(id -u) might be useful if the image supports it.
            # The jupyter/docker-stacks images often create a user 'jovyan' with UID 1000.
            # Let's add a CHOWN_HOME='yes' and CHOWN_EXTRA_OPTS='-R' which some images use to fix permissions.
            # Also, NB_PREFIX might be useful if running behind a proxy, but not essential for direct access.
            "-e",
            "CHOWN_HOME=yes",
            "-e",
            "CHOWN_EXTRA_OPTS=-R",
            # Grant sudo access to the jovyan user if needed for package installs, though generally better to build custom image
            # "-e", "GRANT_SUDO=yes", # Uncomment if sudo access is needed inside container
        ]
        cmd.append(JUPYTER_DOCKER_IMAGE)  # Use imported JUPYTER_DOCKER_IMAGE
        # Add --user $(id -u):$(id -g) if running on Linux and want to map to host user,
        # but this can be problematic with pre-built images expecting a specific internal user.
        # For jupyter/datascience-notebook, it's usually better to let it run as 'jovyan'
        # and ensure the volume permissions are correct on the host.

        logging.info(
            f"Attempting to run JupyterLab container with command: {' '.join(cmd)}"
        )
        try:
            process_result = subprocess.run(
                cmd, check=True, capture_output=True, text=True
            )
            container_id_full = process_result.stdout.strip()
            container_id_short = container_id_full[:12]

            db_update = get_db()  # Uses imported get_db
            db_update.execute(
                """UPDATE user_instances
                   SET container_id = ?, status = 'running',
                       expires_at = datetime('now', ?)
                   WHERE id = ?""",
                (
                    container_id_short,
                    f"+{session_days} days",  # Use custom session_days
                    instance_id,
                ),
            )
            db_update.commit()
            db_update.close()

        except subprocess.CalledProcessError as e:
            logging.error(
                f"Failed to start JupyterLab container {container_name}. Error: {e.stderr}"
            )
            db_update_error = get_db()
            try:
                db_update_error.execute(
                    "UPDATE user_instances SET status = 'error' WHERE id = ?",
                    (instance_id,),
                )
                db_update_error.commit()
            finally:
                db_update_error.close()
            error_message = quote(
                f"Failed to start JupyterLab container: {e.stderr.strip()}"
            )
            return RedirectResponse(
                url=f"/dashboard?error={error_message}",
                status_code=status.HTTP_302_FOUND,
            )

    except Exception as e:
        db_exc = get_db()
        db_exc.execute(
            "UPDATE user_instances SET status = 'error' WHERE id = ?",
            (instance_id,),
        )
        db_exc.commit()
        db_exc.close()
        logging.error(
            f"Unexpected error in request_jupyterlab_instance for instance {instance_id}: {str(e)}",
            exc_info=True,
        )
        error_message = quote(
            f"An unexpected error occurred while preparing your JupyterLab instance: {str(e)}"
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}", status_code=status.HTTP_302_FOUND
        )

    return RedirectResponse(
        url="/dashboard?message="
        + quote(f"JupyterLab instance '{container_name}' is being prepared."),
        status_code=status.HTTP_302_FOUND,
    )


@app.post("/stop_instance/{instance_id}")
async def stop_instance_action(
    instance_id: int,
    request: Request,
    current_user: dict = Depends(
        get_current_active_user
    ),  # Uses imported get_current_active_user
):
    db = get_db()  # Uses imported get_current_active_user
    instance = db.execute(
        "SELECT * FROM user_instances WHERE id = ?",
        (instance_id,),
    ).fetchone()

    if not instance:
        db.close()
        error_message = quote("Instance not found.")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    # Ensure 'is_admin' is accessed as a key, not with .get()
    if not current_user["is_admin"] and instance["user_id"] != current_user["id"]:
        db.close()
        error_message = quote("You are not authorized to stop this instance.")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    container_name = instance["container_name"]
    if not container_name:  # Check for empty container name
        db.close()
        logging.error(
            f"Instance ID {instance_id} has an empty container name. Cannot stop."
        )
        error_message = quote(
            "Instance has an invalid configuration (empty container name). Cannot proceed."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    logging.info(
        f"User '{current_user['email']}' attempting to stop instance ID {instance_id} (Container: {container_name})"
    )

    error_accumulator = []
    success_message_parts = []

    try:
        # Step 1: Attempt to stop the Docker container
        docker_stopped_or_not_found = False
        try:
            stop_cmd = ["docker", "stop", container_name]
            logging.info(f"Executing: {' '.join(stop_cmd)}")
            stop_process = subprocess.run(
                stop_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,  # Added timeout
            )

            if stop_process.returncode == 0:
                logging.info(
                    f"Successfully sent stop command to container {container_name}."
                )
                success_message_parts.append(
                    f"Instance '{container_name}' stop command processed."
                )
                docker_stopped_or_not_found = True
            else:
                stderr_msg = stop_process.stderr.strip()
                logging.warning(
                    f"Output from 'docker stop {container_name}': {stderr_msg}"
                )
                if "No such container" in stderr_msg:
                    logging.info(f"Container {container_name} was already removed.")
                    success_message_parts.append(
                        f"Instance '{container_name}' was already stopped/removed."
                    )
                    docker_stopped_or_not_found = True
                elif "is already in progress" in stderr_msg.lower():
                    logging.info(
                        f"Container {container_name} removal was already in progress."
                    )
                    success_message_parts.append(
                        f"Instance '{container_name}' stop/removal was already in progress."
                    )
                    docker_stopped_or_not_found = True
                else:
                    error_accumulator.append(
                        f"Docker stop issue: {stderr_msg if stderr_msg else 'Unknown error from docker stop'}"
                    )
        except FileNotFoundError:
            logging.error(
                "Docker command not found. Ensure Docker is installed and in PATH."
            )
            error_accumulator.append(
                "Docker command not found. Please contact an administrator."
            )
        except PermissionError:
            logging.error("Permission denied when trying to run Docker command.")
            error_accumulator.append(
                "Permission issue with Docker. Please contact an administrator."
            )
        except subprocess.TimeoutExpired:
            logging.error(f"Docker stop command timed out for {container_name}.")
            error_accumulator.append(
                f"Stopping instance '{container_name}' timed out. It may still be processing."
            )
        except (
            Exception
        ) as docker_ex:  # Catch other unexpected errors during docker operation
            logging.error(
                f"Unexpected error during Docker stop for {container_name}: {docker_ex}",
                exc_info=True,
            )
            error_accumulator.append(
                f"An unexpected error occurred while trying to stop the container: {str(docker_ex)}"
            )

        # Step 2: Update database record
        try:
            cursor = db.cursor()
            current_time_utc = datetime.now(timezone.utc)

            if docker_stopped_or_not_found:
                db_status_to_set = "stopped"
                stopped_at_value = current_time_utc
            else:
                # If docker_stopped_or_not_found is False, it implies a Docker-related error
                # occurred and was likely added to error_accumulator.
                # The instance status should reflect an error in this case.
                db_status_to_set = "error"
                stopped_at_value = (
                    None  # Do not set stopped_at if there was a docker error
                )

            cursor.execute(
                "UPDATE user_instances SET status = ?, stopped_at = ? WHERE id = ?",
                (db_status_to_set, stopped_at_value, instance_id),
            )
            db.commit()
            logging.info(
                f"Instance {instance_id} (Container: {container_name}) status updated to '{db_status_to_set}', stopped_at={stopped_at_value.isoformat() if stopped_at_value else 'None'} in DB."
            )
            # Only add to success_message_parts if the intended operation (stopping) was reflected
            if db_status_to_set == "stopped":
                success_message_parts.append(
                    f"Instance record status updated to '{db_status_to_set}'."
                )
            elif db_status_to_set == "error" and not docker_stopped_or_not_found:
                # If we set to error due to docker issue, it's not really a success part for the user message.
                # It's already in error_accumulator.
                pass

        except sqlite3.Error as db_update_err:
            logging.error(
                f"Database error updating instance {instance_id} status: {db_update_err}",
                exc_info=True,
            )
            error_accumulator.append(
                f"Failed to update instance status in database: {str(db_update_err)}"
            )
            # If DB update fails, the overall operation is problematic, ensure an error is reflected
            # even if docker part seemed to succeed.
            if docker_stopped_or_not_found and not any(
                "database" in e.lower() for e in error_accumulator
            ):
                error_accumulator.append(
                    "Docker stop succeeded but database update failed."
                )

    except Exception as e:
        logging.error(
            f"Unexpected critical error during stop operation for instance '{container_name}': {str(e)}",
            exc_info=True,
        )
        # Avoid adding duplicate generic error if a more specific one was already added.
        generic_error_msg = f"Unexpected critical error: {str(e)}"
        if not any(generic_error_msg in acc_msg for acc_msg in error_accumulator):
            error_accumulator.append(generic_error_msg)

        if db:
            try:
                current_status_row = db.execute(
                    "SELECT status FROM user_instances WHERE id = ?", (instance_id,)
                ).fetchone()
                if current_status_row and current_status_row["status"] not in [
                    "stopped",
                    "error",
                ]:
                    cursor = db.cursor()
                    cursor.execute(
                        "UPDATE user_instances SET status = 'error' WHERE id = ?",
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


@app.post(
    "/delete_instance/{instance_id}", name="delete_instance"
)  # Renamed from /delete_rstudio
async def delete_instance(
    instance_id: int,
    request: Request,
    current_user: dict = Depends(
        get_current_active_user
    ),  # Uses imported get_current_active_user
):
    db = get_db()  # Uses imported get_current_active_user
    instance = db.execute(
        "SELECT * FROM user_instances WHERE id = ?",
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
        db.execute("DELETE FROM user_instances WHERE id = ?", (instance_id,))
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
    response = RedirectResponse(
        url="/login?message=Successfully logged out", status_code=status.HTTP_302_FOUND
    )
    # Delete cookies with the same parameters they were set with
    response.delete_cookie(
        key="user_email", httponly=True, samesite="Lax", secure=False
    )
    response.delete_cookie(
        key="session_expires", httponly=True, samesite="Lax", secure=False
    )
    return response


# --- Admin (very basic, expand significantly) ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: dict = Depends(
        get_current_active_user
    ),  # Uses imported get_current_active_user
):
    """
    Admin dashboard that displays all users and their RStudio instances.
    Simplified version with direct database access (no threading).
    """
    # Check if user is admin
    if not current_user["is_admin"]:
        error_message = quote("You are not authorized to access this page.")
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        # Connect to database
        db = get_db()

        # Get all users
        users_data = db.execute(
            "SELECT id, email, is_admin, created_at, lab_name FROM users ORDER BY id"
        ).fetchall()

        # Get all instances with user information and ordered status
        instances_data = db.execute(
            """
            SELECT ui.id, ui.user_id, ui.container_name, ui.container_id, ui.port, ui.password,
                   ui.created_at, ui.expires_at, ui.status, ui.stopped_at, ui.instance_type,
                   u.email as owner_email
            FROM user_instances ui
            JOIN users u ON ui.user_id = u.id
            ORDER BY
                CASE ui.status
                    WHEN 'running' THEN 1
                    WHEN 'requested' THEN 2
                    WHEN 'stopped' THEN 3
                    WHEN 'error' THEN 4
                    ELSE 5
                END,
                ui.created_at DESC
        """
        ).fetchall()

        # Process users data
        users_list = []
        for user_row in users_data:
            user_dict = dict(user_row)

            # Process created_at date for each user
            if user_dict.get("created_at"):
                raw_created_at = user_dict["created_at"]
                if isinstance(raw_created_at, str):
                    try:
                        user_dict["created_at"] = datetime.fromisoformat(
                            raw_created_at.replace(" ", "T")
                        )
                    except ValueError:
                        try:
                            user_dict["created_at"] = datetime.strptime(
                                raw_created_at, "%Y-%m-%d %H:%M:%S.%f"
                            )
                        except ValueError:
                            try:
                                user_dict["created_at"] = datetime.strptime(
                                    raw_created_at, "%Y-%m-%d %H:%M:%S"
                                )
                            except ValueError:
                                logger.warning(
                                    f"Could not parse created_at for user {user_dict['id']}: {raw_created_at}"
                                )
                                user_dict["created_at"] = None
                elif not isinstance(raw_created_at, datetime):
                    logger.warning(
                        f"Unexpected type for created_at for user {user_dict['id']}: {type(raw_created_at)}"
                    )
                    user_dict["created_at"] = None

            users_list.append(user_dict)

        # Process instances data
        processed_instances = []
        for instance_row in instances_data:
            instance_dict = dict(instance_row)

            # Process date fields for each instance
            for field in ["created_at", "expires_at", "stopped_at"]:
                value = instance_dict.get(field)
                if value and isinstance(value, str):
                    try:
                        instance_dict[field] = datetime.fromisoformat(
                            value.replace(" ", "T")
                        )
                    except ValueError:
                        try:
                            instance_dict[field] = datetime.strptime(
                                value, "%Y-%m-%d %H:%M:%S"
                            )
                        except ValueError:
                            logging.warning(
                                f"Could not parse date string '{value}' for field '{field}' in instance ID {instance_dict.get('id')}. Setting to None."
                            )
                            instance_dict[field] = None
                elif not isinstance(value, datetime) and value is not None:
                    logging.warning(
                        f"Unexpected type '{type(value)}' for date field '{field}' in instance ID {instance_dict.get('id')}. Setting to None."
                    )
                    instance_dict[field] = None

            processed_instances.append(instance_dict)

        # Get base URL for RStudio links
        base_url = str(request.base_url).rstrip("/")

        # Close database connection
        db.close()

        # Render template with all data
        return templates.TemplateResponse(
            "admin_dashboard.html",
            {
                "request": request,
                "user": current_user,
                "users": users_list,
                "instances": processed_instances,
                "base_url": base_url,
                "title": "Admin Dashboard",
                "memory_limit": RSTUDIO_DEFAULT_MEMORY,  # Add memory limit
                "cpu_limit": RSTUDIO_DEFAULT_CPUS,  # Add CPU limit
                "storage_limit": RSTUDIO_USER_STORAGE_LIMIT,  # Storage limit now has default value
            },
        )

    except sqlite3.Error as db_error:
        # Handle database errors
        logging.error(f"Database error in admin_dashboard: {db_error}", exc_info=True)
        error_message = quote(
            "A database error occurred while loading the admin dashboard."
        )
        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )

    except Exception:
        # Handle general errors
        logging.error("Unexpected error in admin_dashboard:", exc_info=True)

        try:
            # Prepare error message for redirect
            error_message = quote(
                "An unexpected error occurred while trying to load the admin page."
            )
        except Exception:
            # Fallback if quoting fails
            error_message = "unexpected_error_occurred"

        return RedirectResponse(
            url=f"/dashboard?error={error_message}",
            status_code=status.HTTP_302_FOUND,
        )


# Add uvicorn startup if this file is run directly (for development)
if __name__ == "__main__":
    import uvicorn
    from app.core.config import UVICORN_HOST, UVICORN_PORT  # Import here for __main__

    # Configure logging for Uvicorn and application
    logging.basicConfig(level=logging.INFO)  # Basic config for root logger
    # You might want more sophisticated logging config, e.g., using logging.config.dictConfig

    logger.info(f"Starting Uvicorn server on {UVICORN_HOST}:{UVICORN_PORT}")
    uvicorn.run(app, host=UVICORN_HOST, port=UVICORN_PORT)
