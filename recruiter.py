import logging
from database import create_connection, get_connection
from rag_engine import search_candidates_for_job, add_job_embedding, get_skill_gap

logger = logging.getLogger("jobbridge_ai")

def create_job(recruiter_id: int, title: str, description: str, skills: str,
               experience_min: int = None, experience_max: int = None,
               salary: str = None, location: str = None,
               job_type: str = None, company_name: str = None,
               interview_enabled: int = 0, interview_mode: str = 'AI') -> int | None:
    """Create a job and index it for RAG. Returns job_id or None."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO jobs (recruiter_id, title, description, skills, experience_min,
                       experience_max, salary, location, job_type, company_name,
                       interview_enabled, interview_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (recruiter_id, title, description, skills, experience_min,
                 experience_max, salary, location, job_type or "Full-time", company_name,
                 interview_enabled, interview_mode),
            )
            job_id = cursor.lastrowid
    except Exception as e:
        logger.error(f"create_job failed: {e}")
        return None

    job = get_job_by_id(job_id)
    if job:
        try:
            add_job_embedding(job_id, job)
        except Exception:
            pass  # Non-critical: embedding can be rebuilt later
    return job_id


def update_job(job_id: int, recruiter_id: int, **kwargs) -> bool:
    """Update job fields. Only recruiter who created can update."""
    allowed = ("title", "description", "skills", "experience_min", "experience_max",
               "salary", "location", "job_type", "company_name", "is_active",
               "interview_enabled", "interview_mode")
    updates = []
    values = []
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            updates.append(f"{k} = ?")
            values.append(v)
    if not updates:
        return True
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM jobs WHERE id = ? AND recruiter_id = ?", (job_id, recruiter_id))
        if not cursor.fetchone():
            return False
        values.append(job_id)
        cursor.execute("UPDATE jobs SET " + ", ".join(updates) + ", updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)

    job = get_job_by_id(job_id)
    if job:
        try:
            add_job_embedding(job_id, job)
        except Exception:
            pass
    return True


def get_job_by_id(job_id: int) -> dict | None:
    """Fetch single job as dict."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_jobs_by_recruiter(recruiter_id: int, active_only: bool = True) -> list:
    """List jobs posted by recruiter."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM jobs WHERE recruiter_id = ? AND is_active = 1 ORDER BY updated_at DESC", (recruiter_id,))
        else:
            cursor.execute("SELECT * FROM jobs WHERE recruiter_id = ? ORDER BY updated_at DESC", (recruiter_id,))
        return [dict(r) for r in cursor.fetchall()]


def list_all_active_jobs(limit: int = 100) -> list:
    """List all active jobs for job seeker browse."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE is_active = 1 ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]


def get_candidates_for_job(job_id: int, skills_filter: list = None, experience_min: int = None,
                            location_filter: str = None, top_k: int = 50) -> list:
    """
    Get ranked candidates for a job (from RAG). Optionally filter by skills, experience, location.
    Returns list of dicts with user_id, score, profile snapshot.
    """
    ranked = search_candidates_for_job(job_id, top_k=top_k * 2)
    with get_connection() as conn:
        cursor = conn.cursor()
        result = []
        for r in ranked:
            cursor.execute("SELECT p.*, u.name, u.email, u.phone as user_phone FROM profiles p JOIN users u ON u.id = p.user_id WHERE p.user_id = ?", (r["user_id"],))
            row = cursor.fetchone()
            if not row:
                continue
            profile = dict(row)
            # Respect visibility
            if profile.get("visibility") is not None and int(profile.get("visibility")) == 0:
                continue
            if skills_filter:
                profile_skills = set((profile.get("skills") or "").lower().split(","))
                profile_skills = {s.strip() for s in profile_skills if s.strip()}
                if not profile_skills & set(s.lower() for s in skills_filter):
                    continue
            if experience_min is not None and (profile.get("experience_years") or 0) < experience_min:
                continue
            if location_filter and location_filter.lower() not in (profile.get("location") or "").lower():
                continue
            result.append({
                "user_id": r["user_id"],
                "score": r["score"],
                "name": profile.get("name"),
                "email": profile.get("email"),
                "phone": profile.get("user_phone") or profile.get("phone"),
                "headline": profile.get("headline"),
                "skills": profile.get("skills"),
                "location": profile.get("location"),
                "experience_years": profile.get("experience_years"),
                "experience_level": profile.get("experience_level"),
            })
            if len(result) >= top_k:
                break
    return result


def get_applicants_for_job(job_id: int) -> list:
    """Get all applicants for a specific job with their profiles and application status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT a.user_id, a.match_score, a.status, a.created_at as applied_at,
                      u.name, u.email, u.phone as user_phone,
                      p.skills, p.experience_years, p.experience_level, p.location,
                      p.headline, p.resume_path, p.profile_photo_path
               FROM applications a
               JOIN users u ON u.id = a.user_id
               LEFT JOIN profiles p ON p.user_id = a.user_id
               WHERE a.job_id = ?
               ORDER BY a.match_score DESC NULLS LAST, a.created_at DESC""",
            (job_id,),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_candidate_skill_gap(job_id: int, user_id: int) -> dict:
    """Get skill gap between job and candidate profile."""
    job = get_job_by_id(job_id)
    if not job:
        return {"matching_skills": [], "missing_skills": [], "match_pct": 0}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT skills FROM profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    cand_skills = row["skills"] if row else ""
    return get_skill_gap(job.get("skills") or "", cand_skills)


def add_manual_questions(job_id: int, questions: list[dict]) -> None:
    """Save manual questions for a job. questions: [{'text': str, 'difficulty': str}]"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM job_questions WHERE job_id = ?", (job_id,))
        for q in questions:
            cursor.execute(
                "INSERT INTO job_questions (job_id, question_text, difficulty) VALUES (?, ?, ?)",
                (job_id, q["text"], q.get("difficulty", "Intermediate")),
            )


def get_job_questions(job_id: int) -> list:
    """Fetch manual questions for a job."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM job_questions WHERE job_id = ?", (job_id,))
        return [dict(r) for r in cursor.fetchall()]
