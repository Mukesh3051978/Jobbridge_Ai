"""
JobBridge AI - Authentication module.
Secure login/registration with bcrypt, role-based access, email validation.
"""

import re
import sqlite3
import logging
import bcrypt
from database import create_connection, get_connection

logger = logging.getLogger("jobbridge_ai")

# Role mapping: UI display <-> DB value
ROLE_TO_DB = {"Job Seeker": "job_seeker", "Recruiter": "recruiter", "Admin": "admin"}
DB_TO_ROLE = {v: k for k, v in ROLE_TO_DB.items()}

# Professional email domains (Microsoft + corporate allowed)
BLOCKED_DOMAINS = {"mailinator.com", "tempmail.com", "guerrillamail.com", "throwaway.email", "yopmail.com"}
PREFERRED_DOMAINS = {"outlook.com", "hotmail.com", "live.com", "microsoft.com"}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate email format and domain.
    Returns (is_valid, message).
    """
    email = (email or "").strip().lower()
    if not email:
        return False, "Email is required."
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format."
    domain = email.split("@")[1]
    if domain in BLOCKED_DOMAINS:
        return False, "Disposable email addresses are not allowed."
    return True, ""


def hash_password(password: str) -> bytes:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, hashed: bytes) -> bool:
    """Verify password against stored hash."""
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(password.encode("utf-8"), hashed)


def register_user(name: str, email: str, password: str, role: str, phone: str = None) -> tuple[bool, str]:
    """
    Register a new user. Role must be 'Job Seeker' or 'Recruiter' (Admin only via DB).
    Returns (success, message).
    """
    if not name or not email or not password:
        return False, "Name, email and password are required."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    valid, msg = validate_email(email)
    if not valid:
        return False, msg

    db_role = ROLE_TO_DB.get(role, "job_seeker")
    if db_role == "admin":
        return False, "Admin registration is not allowed."

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email, password, phone, role) VALUES (?, ?, ?, ?, ?)",
                (name.strip(), email.strip().lower(), hash_password(password), (phone or "").strip() or None, db_role),
            )
            return True, "Account created successfully. You can now log in."
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    except Exception as e:
        logger.exception("register_user failed for email=%s", email)
        return False, f"Registration failed: {e}"


def login_user(email: str, password: str):
    """
    Authenticate user. Returns user dict or None if invalid.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, email, password, phone, role, created_at FROM users WHERE email = ?",
            (email.strip().lower(),),
        )
        row = cursor.fetchone()
        if not row:
            return None
        if not verify_password(password, row["password"]):
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "phone": row["phone"],
            "role": DB_TO_ROLE.get(row["role"], row["role"]),
            "role_db": row["role"],
            "created_at": row["created_at"],
        }


def get_user_by_id(user_id: int):
    """Fetch user by id. Returns dict without password, or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, email, phone, role, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "phone": row["phone"],
            "role": DB_TO_ROLE.get(row["role"], row["role"]),
            "role_db": row["role"],
            "created_at": row["created_at"],
        }


def update_user_name(user_id: int, name: str) -> None:
    """Update user display name."""
    with get_connection() as conn:
        conn.cursor().execute("UPDATE users SET name = ? WHERE id = ?", (name.strip(), user_id))


def update_user_phone(user_id: int, phone: str) -> None:
    """Update user phone number."""
    with get_connection() as conn:
        conn.cursor().execute("UPDATE users SET phone = ? WHERE id = ?", ((phone or "").strip() or None, user_id))


def is_admin(role_db: str) -> bool:
    return role_db == "admin"


def is_recruiter(role_db: str) -> bool:
    return role_db in ("recruiter", "admin")


def is_job_seeker(role_db: str) -> bool:
    return role_db == "job_seeker"
