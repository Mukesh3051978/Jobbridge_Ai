"""
JobBridge AI - Lightweight ML-based hire probability scoring.
Logistic regression on historical decisions, with rule-based fallback.
"""

from __future__ import annotations

import logging
from typing import Optional

from database import create_connection, get_connection

logger = logging.getLogger("jobbridge_ai")

try:
    from sklearn.linear_model import LogisticRegression
    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False


def _load_training_data(job_id: int):
    """Build training set from applications with interview sessions."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.user_id, a.match_score, a.status,
                   s.overall_score, s.technical_score, s.communication_score
            FROM applications a
            JOIN interview_sessions s
              ON s.user_id = a.user_id AND (s.job_id = a.job_id OR s.job_id IS NULL)
            WHERE a.job_id = ? AND a.status IN ('shortlisted', 'rejected')
              AND s.status = 'completed'
            """,
            (job_id,),
        )
        rows = cursor.fetchall()

    X, y = [], []
    for r in rows:
        if r["match_score"] is None or r["overall_score"] is None:
            continue
        X.append([
            float(r["match_score"] or 0.0),
            float(r["overall_score"] or 0.0),
            float(r["technical_score"] or r["overall_score"] or 0.0),
            float(r["communication_score"] or r["overall_score"] or 0.0),
        ])
        y.append(1 if r["status"] == "shortlisted" else 0)
    return X, y


def _rule_based_probability(match_score: float, overall: float, technical: float, communication: float) -> float:
    """Simple heuristic probability. Returns probability in [0, 1]."""
    m = max(0.0, min(1.0, (match_score or 0.0) / 100.0))
    o = max(0.0, min(1.0, (overall or 0.0) / 10.0))
    t = max(0.0, min(1.0, (technical or 0.0) / 10.0))
    c = max(0.0, min(1.0, (communication or 0.0) / 10.0))
    score = 0.4 * m + 0.3 * o + 0.2 * t + 0.1 * c
    return max(0.0, min(1.0, score))


def predict_hire_probability(job_id: int, user_id: int, match_score: Optional[float]) -> Optional[float]:
    """Predict P(hire) for (job_id, user_id). Returns probability in [0, 1] or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT overall_score, technical_score, communication_score
            FROM interview_sessions
            WHERE user_id = ? AND (job_id = ? OR job_id IS NULL) AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 1
            """,
            (user_id, job_id),
        )
        row = cursor.fetchone()

    if not row and match_score is None:
        return None

    overall = float(row["overall_score"]) if row and row["overall_score"] is not None else 0.0
    technical = float(row["technical_score"]) if row and row["technical_score"] is not None else overall
    communication = float(row["communication_score"]) if row and row["communication_score"] is not None else overall

    if not HAS_SKLEARN:
        return _rule_based_probability(match_score or 0.0, overall, technical, communication)

    X, y = _load_training_data(job_id)
    if len(set(y)) < 2 or len(y) < 10:
        return _rule_based_probability(match_score or 0.0, overall, technical, communication)

    try:
        model = LogisticRegression(max_iter=200)
        model.fit(X, y)
        prob = model.predict_proba([[float(match_score or 0.0), overall, technical, communication]])[0][1]
        return float(max(0.0, min(1.0, prob)))
    except Exception:
        return _rule_based_probability(match_score or 0.0, overall, technical, communication)
