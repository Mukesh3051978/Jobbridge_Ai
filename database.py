"""
JobBridge AI - Database module.
SQLite schema and connection management for the full application.
Production-ready: context managers, proper migrations, no silent failures.
"""

import sqlite3
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger("jobbridge_ai")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobbridge.db")


def create_connection():
    """Create and return a database connection with row factory and WAL mode."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_connection():
    """Context manager for safe connection handling. Auto-commits on success, rolls back on error."""
    conn = create_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor():
    """Context manager for connection and cursor."""
    with get_connection() as conn:
        yield conn.cursor()


def create_tables():
    """Create all application tables if they do not exist."""
    conn = create_connection()
    cursor = conn.cursor()

    # Users: id, name, email, password, phone, role, created_at
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            role TEXT NOT NULL CHECK(role IN ('job_seeker', 'recruiter', 'admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Job seeker profiles: linked to user_id
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            phone TEXT,
            headline TEXT,
            location TEXT,
            about TEXT,
            summary TEXT,
            experience_years INTEGER,
            experience_level TEXT,
            experience_description TEXT,
            education TEXT,
            skills TEXT,
            preferred_locations TEXT,
            preferred_industries TEXT,
            profile_photo_path TEXT,
            resume_path TEXT,
            resume_parsed_data TEXT,
            interview_readiness_score REAL DEFAULT 0,
            visibility INTEGER DEFAULT 1,
            portfolio_url TEXT,
            github_url TEXT,
            linkedin_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Jobs: posted by recruiter (includes salary)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recruiter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            skills TEXT NOT NULL,
            experience_min INTEGER,
            experience_max INTEGER,
            salary TEXT,
            location TEXT,
            job_type TEXT,
            company_name TEXT,
            is_active INTEGER DEFAULT 1,
            interview_enabled INTEGER DEFAULT 0,
            interview_mode TEXT DEFAULT 'AI',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Job-specific questions (for Manual mode)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            question_text TEXT NOT NULL,
            difficulty TEXT DEFAULT 'Intermediate',
            expected_answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Resume uploads metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            original_filename TEXT,
            parsed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Certificates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            original_filename TEXT,
            issuer TEXT,
            candidate_name_extracted TEXT,
            is_verified INTEGER DEFAULT 0,
            verification_notes TEXT,
            is_suspicious INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Interview sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interview_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
            job_title TEXT,
            difficulty TEXT DEFAULT 'Intermediate',
            status TEXT DEFAULT 'in_progress',
            application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
            overall_score REAL,
            technical_score REAL,
            communication_score REAL,
            recruiter_score REAL,
            recruiter_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    # Individual Q&A per session
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interview_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
            question_text TEXT NOT NULL,
            answer_text TEXT NOT NULL,
            score REAL,
            feedback TEXT,
            recruiter_score REAL,
            recruiter_remarks TEXT,
            suggested_answer TEXT,
            suggested_score_range TEXT,
            question_order INTEGER,
            question_type TEXT DEFAULT 'behavioral',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Vector store metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embedding_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL CHECK(entity_type IN ('job', 'candidate')),
            entity_id INTEGER NOT NULL,
            faiss_index INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(entity_type, entity_id)
        )
    """)

    # Applications: status includes 'reviewed'
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            match_score REAL,
            status TEXT DEFAULT 'applied' CHECK(status IN ('applied', 'reviewed', 'shortlisted', 'rejected')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, job_id)
        )
    """)

    # Companies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            website TEXT,
            description TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Recruiters
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recruiters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            phone TEXT,
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            designation TEXT,
            about TEXT,
            profile_photo_path TEXT,
            resume_path TEXT,
            linkedin_url TEXT,
            portfolio_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # ---- Lightweight migrations for existing DBs ----
    migrations = [
        "ALTER TABLE applications ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE profiles ADD COLUMN phone TEXT",
        "ALTER TABLE profiles ADD COLUMN summary TEXT",
        "ALTER TABLE profiles ADD COLUMN experience_description TEXT",
        "ALTER TABLE profiles ADD COLUMN visibility INTEGER DEFAULT 1",
        "ALTER TABLE profiles ADD COLUMN portfolio_url TEXT",
        "ALTER TABLE profiles ADD COLUMN github_url TEXT",
        "ALTER TABLE profiles ADD COLUMN linkedin_url TEXT",
        "ALTER TABLE profiles ADD COLUMN interview_readiness_score REAL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN salary TEXT",
        "ALTER TABLE recruiters ADD COLUMN about TEXT",
        "ALTER TABLE jobs ADD COLUMN interview_enabled INTEGER DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN interview_mode TEXT DEFAULT 'AI'",
        "ALTER TABLE interview_sessions ADD COLUMN application_id INTEGER",
        "ALTER TABLE interview_sessions ADD COLUMN recruiter_score REAL",
        "ALTER TABLE interview_sessions ADD COLUMN recruiter_feedback TEXT",
        "ALTER TABLE interview_answers ADD COLUMN recruiter_score REAL",
        "ALTER TABLE interview_answers ADD COLUMN recruiter_remarks TEXT",
        "ALTER TABLE interview_answers ADD COLUMN suggested_answer TEXT",
        "ALTER TABLE interview_answers ADD COLUMN suggested_score_range TEXT",
    ]
    for sql in migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


# ---- Profile helpers ----

def get_profile(user_id: int):
    """Get profile row for user_id as dict or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_profile(user_id: int, **kwargs) -> None:
    """Insert or update profile. Only allowed keys are persisted."""
    allowed = (
        "phone", "headline", "location", "about", "summary",
        "experience_years", "experience_level", "experience_description",
        "education", "skills", "preferred_locations", "preferred_industries",
        "profile_photo_path", "resume_path", "resume_parsed_data",
        "visibility", "portfolio_url", "github_url", "linkedin_url",
        "interview_readiness_score",
    )
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM profiles WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()
        if exists:
            updates = [f"{k} = ?" for k in kwargs if k in allowed]
            values = [kwargs[k] for k in kwargs if k in allowed]
            if updates:
                values.append(user_id)
                cursor.execute(
                    "UPDATE profiles SET " + ", ".join(updates) + ", updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    values,
                )
        else:
            cols = ["user_id"] + [k for k in allowed if k in kwargs]
            placeholders = ["?"] * len(cols)
            values = [user_id] + [kwargs[k] for k in cols if k != "user_id"]
            cursor.execute(
                "INSERT INTO profiles (" + ", ".join(cols) + ") VALUES (" + ", ".join(placeholders) + ")",
                values,
            )


# ---- Application helpers ----

def apply_for_job(user_id: int, job_id: int, match_score: float = None) -> tuple[bool, str]:
    """Job seeker applies for a job. Returns (success, message). Prevents duplicates."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id))
            if cursor.fetchone():
                return False, "You have already applied for this job."
            cursor.execute(
                "INSERT INTO applications (user_id, job_id, match_score, status) VALUES (?, ?, ?, 'applied')",
                (user_id, job_id, match_score),
            )
            return True, "Application submitted."
    except sqlite3.IntegrityError:
        return False, "You have already applied for this job."
    except Exception as e:
        logger.exception("apply_for_job failed user_id=%s job_id=%s", user_id, job_id)
        return False, f"Application failed: {e}"


def get_applications_for_user(user_id: int) -> list:
    """Get all applications by a job seeker with job details and status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT a.id, a.job_id, a.match_score, a.status, a.created_at,
                      j.title, j.company_name, j.location, j.salary
               FROM applications a
               JOIN jobs j ON j.id = a.job_id
               WHERE a.user_id = ?
               ORDER BY a.created_at DESC""",
            (user_id,),
        )
        return [dict(r) for r in cursor.fetchall()]


def set_application_status(user_id: int, job_id: int, status: str, recruiter_id: int) -> bool:
    """Recruiter sets status. Creates application if missing."""
    if status not in ("applied", "reviewed", "shortlisted", "rejected"):
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM jobs WHERE id = ? AND recruiter_id = ?", (job_id, recruiter_id))
        if not cursor.fetchone():
            return False
        cursor.execute("SELECT id FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO applications (user_id, job_id, match_score, status) VALUES (?, ?, ?, ?)",
                (user_id, job_id, None, status),
            )
        else:
            cursor.execute(
                "UPDATE applications SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND job_id = ?",
                (status, user_id, job_id),
            )
    return True


def get_application_status(user_id: int, job_id: int) -> str | None:
    """Get application status for (user_id, job_id) or None if not applied."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id))
        row = cursor.fetchone()
        return row["status"] if row else None


def get_candidate_full_profile(user_id: int) -> dict | None:
    """Get full profile with certificates for recruiter viewer."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT p.*, u.name, u.email, u.phone as user_phone FROM profiles p JOIN users u ON u.id = p.user_id WHERE p.user_id = ?",
            (user_id,),
        )
        profile = cursor.fetchone()
        if not profile:
            return None
        cursor.execute(
            "SELECT id, original_filename, file_path, is_verified, is_suspicious, verification_notes FROM certificates WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        certs = [dict(r) for r in cursor.fetchall()]
        return {"profile": dict(profile), "certificates": certs}


# ---- Recruiter/company helpers ----

def upsert_company_and_recruiter(
    user_id: int,
    phone: str | None = None,
    company_name: str | None = None,
    company_website: str | None = None,
    company_description: str | None = None,
    company_location: str | None = None,
    designation: str | None = None,
    about: str | None = None,
    profile_photo_path: str | None = None,
    resume_path: str | None = None,
    linkedin_url: str | None = None,
    portfolio_url: str | None = None,
) -> None:
    """Create or update recruiter + company records."""
    with get_connection() as conn:
        cursor = conn.cursor()
        company_id = None
        if company_name:
            cursor.execute(
                "SELECT id FROM companies WHERE name = ? AND IFNULL(website, '') = IFNULL(?, '')",
                (company_name.strip(), (company_website or "").strip() or None),
            )
            row = cursor.fetchone()
            if row:
                company_id = row["id"]
                cursor.execute(
                    "UPDATE companies SET description = COALESCE(?, description), location = COALESCE(?, location) WHERE id = ?",
                    (company_description, company_location, company_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO companies (name, website, description, location) VALUES (?, ?, ?, ?)",
                    (company_name.strip(), (company_website or "").strip() or None, company_description, company_location),
                )
                company_id = cursor.lastrowid

        cursor.execute("SELECT id FROM recruiters WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone()
        field_map = {}
        if phone is not None:
            field_map["phone"] = phone
        if designation is not None:
            field_map["designation"] = designation
        if about is not None:
            field_map["about"] = about
        if profile_photo_path is not None:
            field_map["profile_photo_path"] = profile_photo_path
        if resume_path is not None:
            field_map["resume_path"] = resume_path
        if linkedin_url is not None:
            field_map["linkedin_url"] = linkedin_url
        if portfolio_url is not None:
            field_map["portfolio_url"] = portfolio_url
        if company_id is not None:
            field_map["company_id"] = company_id

        if exists:
            if field_map:
                sets = [f"{k} = ?" for k in field_map]
                vals = list(field_map.values()) + [user_id]
                cursor.execute("UPDATE recruiters SET " + ", ".join(sets) + ", updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", vals)
        else:
            cols = ["user_id"] + list(field_map.keys())
            vals = [user_id] + list(field_map.values())
            placeholders = ",".join("?" for _ in cols)
            cursor.execute("INSERT INTO recruiters (" + ", ".join(cols) + ") VALUES (" + placeholders + ")", vals)


def get_recruiter_profile(user_id: int) -> dict | None:
    """Get recruiter + company profile."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.*, c.name as company_name, c.website as company_website,
                   c.description as company_description, c.location as company_location,
                   u.name as recruiter_name, u.email as recruiter_email
            FROM recruiters r
            JOIN users u ON u.id = r.user_id
            LEFT JOIN companies c ON c.id = r.company_id
            WHERE r.user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# ---- DB Initialization ----

def init_db() -> None:
    """Ensure DB file exists and tables are created. Create upload and vector_store directories."""
    base = os.path.dirname(os.path.abspath(__file__))
    for folder in (
        "uploads", "uploads/resumes", "uploads/certificates",
        "uploads/photos", "uploads/recruiter_photos", "uploads/recruiter_resumes",
        "vector_store",
    ):
        path = os.path.join(base, folder)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.exception("Failed to create directory %s", path)
            raise RuntimeError(f"Cannot create upload directory: {e}") from e
    try:
        create_tables()
    except sqlite3.Error as e:
        logger.exception("create_tables failed")
        raise RuntimeError(f"Database schema failed: {e}") from e
