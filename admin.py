"""
JobBridge AI - Admin dashboard module.
Platform analytics, user/job management, interview statistics, skill demand.
"""

from database import create_connection, get_connection
from collections import Counter


def get_all_users(role_filter: str = None) -> list:
    """List all users, optionally filter by role."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if role_filter:
            cursor.execute("SELECT id, name, email, role, created_at FROM users WHERE role = ? ORDER BY created_at DESC", (role_filter,))
        else:
            cursor.execute("SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC")
        return [dict(r) for r in cursor.fetchall()]


def get_all_jobs(active_only: bool = False) -> list:
    """List all jobs with recruiter name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT j.*, u.name as recruiter_name FROM jobs j JOIN users u ON u.id = j.recruiter_id WHERE j.is_active = 1 ORDER BY j.created_at DESC")
        else:
            cursor.execute("SELECT j.*, u.name as recruiter_name FROM jobs j JOIN users u ON u.id = j.recruiter_id ORDER BY j.created_at DESC")
        return [dict(r) for r in cursor.fetchall()]


def get_platform_stats() -> dict:
    """Return platform-wide counts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        counts = {}
        for key, sql in [
            ("users", "SELECT COUNT(*) as c FROM users"),
            ("job_seekers", "SELECT COUNT(*) as c FROM users WHERE role = 'job_seeker'"),
            ("recruiters", "SELECT COUNT(*) as c FROM users WHERE role IN ('recruiter', 'admin')"),
            ("jobs", "SELECT COUNT(*) as c FROM jobs WHERE is_active = 1"),
            ("profiles", "SELECT COUNT(*) as c FROM profiles"),
            ("interviews_completed", "SELECT COUNT(*) as c FROM interview_sessions WHERE status = 'completed'"),
            ("certificates", "SELECT COUNT(*) as c FROM certificates"),
            ("applications", "SELECT COUNT(*) as c FROM applications"),
        ]:
            cursor.execute(sql)
            counts[key] = cursor.fetchone()["c"]
    return counts


def get_interview_statistics() -> dict:
    """Aggregate interview scores and counts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM interview_sessions WHERE status = 'completed'")
        total = cursor.fetchone()["c"]
        cursor.execute(
            "SELECT AVG(overall_score) as avg_overall, AVG(technical_score) as avg_tech, AVG(communication_score) as avg_comm FROM interview_sessions WHERE status = 'completed'"
        )
        row = cursor.fetchone()
    return {
        "total_completed": total,
        "avg_overall_score": round(row["avg_overall"] or 0, 1),
        "avg_technical_score": round(row["avg_tech"] or 0, 1),
        "avg_communication_score": round(row["avg_comm"] or 0, 1),
    }


def get_skill_demand(top_n: int = 20) -> list:
    """Return most demanded skills across job postings: [(skill, count), ...]."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT skills FROM jobs WHERE is_active = 1")
        rows = cursor.fetchall()
    counter = Counter()
    for row in rows:
        for s in (row["skills"] or "").split(","):
            s = s.strip().lower()
            if s:
                counter[s] += 1
    return counter.most_common(top_n)


def get_recent_interviews(limit: int = 10) -> list:
    """List recent completed interviews with user name and job title."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT s.id, s.user_id, s.job_title, s.overall_score, s.completed_at, s.difficulty, u.name as user_name
               FROM interview_sessions s JOIN users u ON u.id = s.user_id
               WHERE s.status = 'completed' ORDER BY s.completed_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in cursor.fetchall()]
