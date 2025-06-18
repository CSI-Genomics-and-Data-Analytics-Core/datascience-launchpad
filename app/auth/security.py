# filepath: /Users/mani/work/rstudio-portal/app/auth/security.py
from fastapi import Request, HTTPException, status, Depends
from datetime import datetime, timedelta
from app.db.database import get_db
from app.core.config import DEFAULT_SESSION_HOURS, REMEMBER_ME_SESSION_DAYS


def get_current_user(request: Request):
    email = request.cookies.get("user_email")
    if not email:
        return None

    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        # Check if session is still valid
        session_expires = request.cookies.get("session_expires")
        if session_expires:
            try:
                expires_dt = datetime.fromisoformat(session_expires)
                if datetime.utcnow() > expires_dt:
                    return None  # Session expired
            except ValueError:
                return None  # Invalid date format

        return user
    finally:
        db.close()


def get_current_active_user(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    return current_user


def create_user_session(email: str, remember_me: bool = False) -> dict:
    """Create session data for authenticated user"""
    if remember_me:
        expires_at = datetime.utcnow() + timedelta(days=REMEMBER_ME_SESSION_DAYS)
    else:
        expires_at = datetime.utcnow() + timedelta(hours=DEFAULT_SESSION_HOURS)

    return {"email": email, "expires_at": expires_at, "remember_me": remember_me}


def is_valid_nus_email(email: str) -> bool:
    """Check if email is a valid NUS email address"""
    import re

    allowed_domains = [
        r"^[a-zA-Z0-9._%+-]+@visitor\.nus\.edu\.sg$",
        r"^[a-zA-Z0-9._%+-]+@u\.nus\.edu$",
        r"^[a-zA-Z0-9._%+-]+@nus\.edu\.sg$",
    ]

    return any(re.fullmatch(pattern, email.lower()) for pattern in allowed_domains)
