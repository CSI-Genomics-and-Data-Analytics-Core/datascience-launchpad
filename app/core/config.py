# filepath: /Users/mani/work/rstudio-portal/app/core/config.py
import os
from pathlib import Path
import dotenv

# Load environment variables from .env file if it exists
dotenv.load_dotenv()

# --- Lab Names ---
LAB_NAMES = [
    "Anand JEYASEKHARAN",
    "Ashok VENKITARAMAN",
    "Boon Cher GOH",
    "Edward Kai-Hua CHOW",
    "Dario Campana",
    "David TAN",
    "Dennis KAPPEI",
    "Jason PITT",
    "Kevin WHITE",
    "Melissa Jane FULLWOOD",
    "Patrick TAN",
    "Polly Leilei CHEN",
    "Soo Chin LEE",
    "Takaomi SANDA",
    "Toshio SUDA",
    "Wai Leong TAM",
    "Wee Joo CHNG",
    "Yang ZHANG",
    "Yvonne TAY",
    "GeDaC",
    "Spatial Biology Core",
    "Other",
]

# --- Base Directories and Paths ---
BASE_DIR = (
    Path(__file__).resolve().parent.parent.parent
)  # Adjusted to point to project root

DB_MOUNT_PATH_STR = os.getenv("DB_MOUNT_PATH")
DATABASE_FILENAME = os.getenv("DATABASE_FILENAME", "db.sqlite3")
if DB_MOUNT_PATH_STR:
    DATABASE_PATH = Path(DB_MOUNT_PATH_STR) / DATABASE_FILENAME
else:
    DATABASE_PATH = BASE_DIR / DATABASE_FILENAME

USER_DATA_MOUNT_PATH_STR = os.getenv("USER_DATA_MOUNT_PATH")
if USER_DATA_MOUNT_PATH_STR:
    USER_DATA_BASE_DIR = Path(USER_DATA_MOUNT_PATH_STR)
else:
    USER_DATA_BASE_DIR = BASE_DIR / "user_data"

DOCKER_TEMPLATES_DIR_NAME = os.getenv("DOCKER_TEMPLATES_DIR_NAME", "docker_templates")
DOCKER_TEMPLATES_DIR = BASE_DIR / DOCKER_TEMPLATES_DIR_NAME

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_JINJA_DIR = BASE_DIR / "templates"

# --- RStudio Configuration ---
RSTUDIO_MIN_PORT = int(os.getenv("RSTUDIO_MIN_PORT", "9002"))
RSTUDIO_MAX_PORT = int(os.getenv("RSTUDIO_MAX_PORT", "9050"))
RSTUDIO_DEFAULT_MEMORY = os.getenv("RSTUDIO_DEFAULT_MEMORY", "16g")
RSTUDIO_DEFAULT_CPUS = os.getenv("RSTUDIO_DEFAULT_CPUS", "2.0")
RSTUDIO_DOCKER_IMAGE = os.getenv("RSTUDIO_DOCKER_IMAGE", "rocker/rstudio:latest")
RSTUDIO_SESSION_EXPIRY_DAYS = int(os.getenv("RSTUDIO_SESSION_EXPIRY_DAYS", "7"))
RSTUDIO_USER_STORAGE_LIMIT = os.getenv(
    "RSTUDIO_USER_STORAGE_LIMIT", "200G"
)  # Added from main

# --- JupyterLab Configuration ---
JUPYTER_DOCKER_IMAGE = os.getenv(
    "JUPYTER_DOCKER_IMAGE", "jupyter/datascience-notebook:latest"
)
JUPYTER_MIN_PORT = int(os.getenv("JUPYTER_MIN_PORT", "9051"))
JUPYTER_MAX_PORT = int(os.getenv("JUPYTER_MAX_PORT", "9100"))
JUPYTER_DEFAULT_MEMORY = os.getenv("JUPYTER_DEFAULT_MEMORY", "16g")
JUPYTER_DEFAULT_CPUS = os.getenv("JUPYTER_DEFAULT_CPUS", "2.0")
JUPYTER_SESSION_EXPIRY_DAYS = int(os.getenv("JUPYTER_SESSION_EXPIRY_DAYS", "7"))

# --- Application Configuration ---
MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "20"))
DEFAULT_SESSION_DAYS = int(os.getenv("DEFAULT_SESSION_DAYS", "2"))
INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
INITIAL_ADMIN_PASSWORD = os.getenv(
    "INITIAL_ADMIN_PASSWORD", "adminpass"
)  # Added for init_db
UVICORN_HOST = os.getenv("UVICORN_HOST", "0.0.0.0")
UVICORN_PORT = int(os.getenv("UVICORN_PORT", "8001"))
SESSION_DURATION_HOURS = int(os.getenv("SESSION_DURATION_HOURS", "8"))

# --- OTP Configuration ---
OTP_VALIDITY_MINUTES = int(os.getenv("OTP_VALIDITY_MINUTES", "10"))
OTP_LENGTH = int(os.getenv("OTP_LENGTH", "6"))
MAX_OTP_ATTEMPTS = int(os.getenv("MAX_OTP_ATTEMPTS", "3"))
MAX_OTP_REQUESTS_PER_HOUR = int(os.getenv("MAX_OTP_REQUESTS_PER_HOUR", "3"))

# --- Session Configuration ---
DEFAULT_SESSION_HOURS = int(os.getenv("DEFAULT_SESSION_HOURS", "24"))
REMEMBER_ME_SESSION_DAYS = int(os.getenv("REMEMBER_ME_SESSION_DAYS", "7"))

# --- SMTP Email Configuration ---
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@yourdomain.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "GeDaC Launchpad")

# SMTP Server Configuration
EMAIL_HOST = os.getenv("EMAIL_HOST", "email-smtp.ap-southeast-1.amazonaws.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() == "true"
