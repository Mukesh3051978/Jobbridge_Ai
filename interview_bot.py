"""
JobBridge AI - AI Interview Bot.
Generate questions with difficulty levels, evaluate answers, score, store results.
Computes interview readiness score for dashboard.
"""

import re
import random
import json
import logging
from database import create_connection, get_connection

logger = logging.getLogger("jobbridge_ai")

# Optional LLM (OpenAI); fallback to rule-based scoring
try:
    import os
    if os.environ.get("OPENAI_API_KEY"):
        import openai
        openai.api_key = os.environ.get("OPENAI_API_KEY")
        HAS_OPENAI = True
    else:
        HAS_OPENAI = False
except ImportError:
    HAS_OPENAI = False

# ---- Question templates by difficulty ----

APTITUDE_BEGINNER = [
    "If a train travels 60 miles in 1 hour, how far will it travel in 15 minutes?",
    "Which number comes next in the sequence: 2, 4, 8, 16, ...?",
    "If all Roses are Flowers and some Flowers fade quickly, can we conclude that some Roses fade quickly?",
]
APTITUDE_INTERMEDIATE = [
    "A person buys a product for $80 and sells it for $100. What is the profit percentage?",
    "If 5 machines can produce 5 widgets in 5 minutes, how long would it take 100 machines to produce 100 widgets?",
    "Find the missing number: 1, 4, 9, 16, 25, ...?",
]
APTITUDE_ADVANCED = [
    "In a room of 30 people, what is the probability that at least two people share the same birthday? (Briefly explain logic)",
    "If you have two ropes that each take 1 hour to burn but burn inconsistently, how do you measure 45 minutes?",
    "Logical reasoning: If A > B and C < B, which is larger, A or C?",
]

TECHNICAL_BEGINNER = [
    "What do you know about {topic}? Can you explain the basics?",
    "How would you describe {topic} to someone who has never heard of it?",
    "What is one project where you used {topic}?",
]
TECHNICAL_INTERMEDIATE = [
    "What is your experience with {topic}? Describe a project where you used it.",
    "How would you approach {topic} in a production environment?",
    "What are the main challenges when working with {topic}?",
]
TECHNICAL_ADVANCED = [
    "Explain the internal workings of {topic} and how you've optimized it at scale.",
    "Compare {topic} with alternatives. When would you NOT choose it?",
    "Describe a production issue you debugged related to {topic}. Walk me through your approach.",
]


def get_job_description_for_interview(job_id: int) -> str:
    """Fetch job title and description for question generation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, skills FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
    if not row:
        return "General role"
    return f"Role: {row['title']}. Description: {row['description']}. Key skills: {row['skills']}"


def get_manual_questions(job_id: int) -> list:
    """Fetch manual questions for a job from DB."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT question_text, difficulty FROM job_questions WHERE job_id = ? ORDER BY id", (job_id,))
        rows = cursor.fetchall()
    return [{"order": i + 1, "text": r["question_text"], "type": "technical", "difficulty": r["difficulty"]} for i, r in enumerate(rows)]


def generate_questions(job_id: int | None = None, user_id: int | None = None,
                       num_questions: int = 5, difficulty: str = "Intermediate") -> list:
    """
    Generate interview questions from job description and candidate resume/skills.
    If job is in 'Manual' mode, returns fixed questions.
    If 'AI' mode, strictly generates skill-specific questions (NO behavioral).
    """
    if job_id:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT interview_mode FROM jobs WHERE id = ?", (job_id,))
            job_row = cursor.fetchone()
            if job_row and job_row["interview_mode"] == "Manual":
                return get_manual_questions(job_id)

    base_desc = get_job_description_for_interview(job_id) if job_id else "General technical role"
    text_for_topics = base_desc

    # Enrich with candidate resume skills
    candidate_skills = []
    if user_id is not None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT skills, resume_parsed_data FROM profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
        if row:
            skills_text = row["skills"] or ""
            try:
                parsed = json.loads(row["resume_parsed_data"]) if row["resume_parsed_data"] else {}
            except Exception:
                parsed = {}
            parsed_skills = parsed.get("skills", [])
            candidate_skills = parsed_skills
            text_for_topics += " Candidate Skills: " + skills_text + " " + " ".join(parsed_skills)

    # Select template pools based on difficulty
    if difficulty == "Beginner":
        technical_pool = TECHNICAL_BEGINNER
        aptitude_pool = APTITUDE_BEGINNER
    elif difficulty == "Advanced":
        technical_pool = TECHNICAL_ADVANCED
        aptitude_pool = APTITUDE_ADVANCED
    else:
        technical_pool = TECHNICAL_INTERMEDIATE
        aptitude_pool = APTITUDE_INTERMEDIATE

    questions: list[dict] = []
    # Extract specific technical keywords from combined text
    # Prioritize candidate skills that match job requirements
    skills_match = re.findall(r"[\w\s\+#]+", text_for_topics)
    topics = [s.strip() for s in skills_match if 3 <= len(s.strip()) <= 25]
    
    # Filter for known technical keywords or candidate skills
    tech_topics = [t for t in topics if any(cs.lower() in t.lower() or t.lower() in cs.lower() for cs in candidate_skills)]
    if not tech_topics:
        tech_topics = topics[:15]
    
    if not tech_topics:
        tech_topics = ["software development", "programming", "system design"]

    used_topics = set()
    for i in range(num_questions):
        # Alternate between technical and aptitude or focus on technical
        if i % 3 == 2: # Every 3rd question is aptitude
            q = random.choice(aptitude_pool)
            questions.append({"order": i + 1, "text": q, "type": "aptitude", "difficulty": difficulty})
        else:
            # Choose a unique topic if possible
            available = [t for t in tech_topics if t not in used_topics]
            topic = random.choice(available if available else tech_topics)
            used_topics.add(topic)
            
            q = random.choice(technical_pool).format(topic=topic)
            questions.append({"order": i + 1, "text": q, "type": "technical", "difficulty": difficulty})
    
    return questions


def evaluate_answer_with_llm(question: str, answer: str, job_title: str) -> dict:
    """Use OpenAI to score and give feedback. Returns {score, feedback, is_technical}."""
    if not HAS_OPENAI:
        return evaluate_answer_rule_based(question, answer)
    try:
        from openai import OpenAI
        client = OpenAI()
        r = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an interview evaluator. Score the candidate's answer from 1 to 10 and give one short feedback sentence."},
                {"role": "user", "content": f"Job: {job_title}\nQuestion: {question}\nAnswer: {answer}\nRespond in format: SCORE: <1-10>\nFEEDBACK: <one sentence>"},
            ],
            max_tokens=150,
        )
        text = r.choices[0].message.content or ""
        score = 7.0
        feedback = text
        for part in text.replace("FEEDBACK:", " ").split():
            if part.isdigit() and 1 <= int(part) <= 10:
                score = float(part)
                break
        return {"score": score, "feedback": feedback[:500]}
    except Exception as e:
        logger.warning("LLM evaluation failed: %s — falling back to rule-based", e)
        return evaluate_answer_rule_based(question, answer)


def evaluate_answer(question: str, answer: str, job_title: str = "General") -> dict:
    """Evaluate answer using LLM if available, else rule-based. Returns {score, feedback}."""
    if HAS_OPENAI:
        return evaluate_answer_with_llm(question, answer, job_title)
    return evaluate_answer_rule_based(question, answer)


def evaluate_answer_rule_based(question: str, answer: str) -> dict:
    """Rule-based scoring: length, structure keywords, numbers, specificity."""
    score = 5.0
    feedback_parts = []

    answer_len = len(answer.strip())
    if answer_len < 20:
        score -= 1.5
        feedback_parts.append("Answer was quite brief — add more detail.")
    elif answer_len > 200:
        score += 1.0
        feedback_parts.append("Good depth in your answer.")
    elif answer_len > 100:
        score += 0.5

    # Structure / STAR method indicators
    if any(w in answer.lower() for w in ["result", "outcome", "learned", "achieved", "delivered"]):
        score += 0.5
        feedback_parts.append("Good use of outcome-oriented language.")

    # Metrics usage
    if any(w in answer.lower() for w in ["%", "percent", "improved", "reduced", "increased", "saved"]):
        score += 1.0
        feedback_parts.append("Great use of metrics.")

    # Technical depth
    if any(w in answer.lower() for w in ["implemented", "designed", "architected", "built", "deployed", "optimized"]):
        score += 0.5

    # Personal ownership
    if any(w in answer.lower() for w in ["i ", "my ", "i've ", "i'd "]):
        score += 0.3

    score = max(1.0, min(10.0, round(score, 1)))
    feedback = " ".join(feedback_parts) if feedback_parts else "Keep being specific and structured in your answers."
    return {"score": score, "feedback": feedback}


def create_session(user_id: int, job_id: int = None, job_title: str = None,
                   difficulty: str = "Intermediate") -> int:
    """Create an interview session and return session_id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if job_title is None and job_id:
            cursor.execute("SELECT title FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            job_title = row["title"] if row else "General"
        cursor.execute(
            "INSERT INTO interview_sessions (user_id, job_id, job_title, difficulty, status) VALUES (?, ?, ?, ?, 'in_progress')",
            (user_id, job_id, job_title or "General", difficulty),
        )
        sid = cursor.lastrowid
    return sid


def save_answer(session_id: int, question_text: str, answer_text: str,
                score: float, feedback: str, order: int, question_type: str = "technical") -> None:
    """Persist one Q&A with score, feedback, and type."""
    with get_connection() as conn:
        conn.cursor().execute(
            """INSERT INTO interview_answers (session_id, question_text, answer_text, score, feedback, question_order, question_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, question_text, answer_text, score, feedback, order, question_type),
        )


def complete_session(session_id: int, overall_score: float,
                     technical_score: float, communication_score: float) -> None:
    """Mark session complete and store separate scores."""
    with get_connection() as conn:
        conn.cursor().execute(
            """UPDATE interview_sessions SET status = 'completed', overall_score = ?,
               technical_score = ?, communication_score = ?,
               completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (overall_score, technical_score, communication_score, session_id),
        )


def get_session_scores(session_id: int) -> list:
    """Get all answer scores for a session."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT score, question_type FROM interview_answers WHERE session_id = ? ORDER BY question_order", (session_id,))
        return [dict(r) for r in cursor.fetchall()]


def compute_separate_scores(session_id: int) -> tuple[float, float, float]:
    """Compute separate technical and aptitude scores from answer types."""
    entries = get_session_scores(session_id)
    tech_scores = [e["score"] for e in entries if e.get("question_type") == "technical" and e.get("score")]
    apt_scores = [e["score"] for e in entries if e.get("question_type") == "aptitude" and e.get("score")]
    all_scores = [e["score"] for e in entries if e.get("score")]

    overall = sum(all_scores) / len(all_scores) if all_scores else 0
    technical = sum(tech_scores) / len(tech_scores) if tech_scores else overall
    aptitude = sum(apt_scores) / len(apt_scores) if apt_scores else overall

    return round(overall, 1), round(technical, 1), round(aptitude, 1)


def get_next_question_for_session(session_id: int, all_questions: list) -> dict | None:
    """Return the next question that hasn't been answered yet."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT question_order FROM interview_answers WHERE session_id = ?", (session_id,))
        answered_orders = {r["question_order"] for r in cursor.fetchall()}
    for q in all_questions:
        if q["order"] not in answered_orders:
            return q
    return None


def get_interview_sessions_for_candidate(user_id: int, job_id: int = None) -> list:
    """Get completed interview sessions for a candidate. Returns list of dicts with session and Q&A."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if job_id:
            cursor.execute(
                "SELECT * FROM interview_sessions WHERE user_id = ? AND job_id = ? AND status = 'completed' ORDER BY completed_at DESC",
                (user_id, job_id),
            )
        else:
            cursor.execute(
                "SELECT * FROM interview_sessions WHERE user_id = ? AND status = 'completed' ORDER BY completed_at DESC",
                (user_id,),
            )
        sessions = [dict(r) for r in cursor.fetchall()]
        result = []
        for s in sessions:
            cursor.execute(
                "SELECT question_text, answer_text, score, feedback, question_order, question_type FROM interview_answers WHERE session_id = ? ORDER BY question_order",
                (s["id"],),
            )
            answers = [dict(r) for r in cursor.fetchall()]
            result.append({"session": s, "answers": answers})
    return result


def compute_interview_readiness(user_id: int) -> float:
    """
    Compute interview readiness score (0-100) for a candidate.
    Based on: completed sessions, average scores, improvement trend.
    """
    sessions = get_interview_sessions_for_candidate(user_id)
    if not sessions:
        return 0.0

    scores = [float(s["session"].get("overall_score") or 0) for s in sessions if s["session"].get("overall_score")]
    if not scores:
        return 0.0

    avg_score = sum(scores) / len(scores)
    session_count_bonus = min(len(sessions) * 5, 20)  # Up to 20 pts for practice
    score_component = avg_score * 8  # Scale 0-10 → 0-80

    readiness = min(100.0, score_component + session_count_bonus)
    return round(readiness, 1)
