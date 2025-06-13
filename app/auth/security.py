# filepath: /Users/mani/work/rstudio-portal/app/auth/security.py
from fastapi import Request, HTTPException, status, Depends
from passlib.context import CryptContext
from app.db.database import get_db  # Assuming get_db will be accessible

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_current_user(request: Request):
    username = request.cookies.get("username")
    if not username:
        return None
    db = get_db()
    try:
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    finally:
        db.close()
    return user


def get_current_active_user(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,  # Or status.HTTP_401_UNAUTHORIZED depending on desired behavior
            detail="Not authenticated",
            headers={"Location": "/login"},  # Redirect to login
        )
    return current_user


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)
