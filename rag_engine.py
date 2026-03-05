"""
JobBridge AI - RAG-based job matching engine.
Embed resumes and job descriptions with SentenceTransformers, store in FAISS, similarity search.
Lazy-loads model to avoid slow cold starts.
"""

import os
import json
import logging
import numpy as np
from database import create_connection, get_connection

logger = logging.getLogger("jobbridge_ai")

# Lazy-loaded model
_MODEL = None
_HAS_ST = None
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2

# FAISS
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_STORE_DIR = os.path.join(BASE_DIR, "vector_store")
INDEX_PATH = os.path.join(VECTOR_STORE_DIR, "faiss.index")
METADATA_PATH = os.path.join(VECTOR_STORE_DIR, "metadata.json")


def _get_model():
    """Lazy-load SentenceTransformer model."""
    global _MODEL, _HAS_ST
    if _HAS_ST is None:
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            _HAS_ST = True
            logger.info("SentenceTransformer model loaded successfully")
        except Exception as e:
            _HAS_ST = False
            logger.warning("SentenceTransformer not available: %s — using fallback", e)
    return _MODEL, _HAS_ST


def _ensure_vector_store():
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)


def _get_embedding(text: str) -> np.ndarray:
    """Get embedding vector for text."""
    if not text or not text.strip():
        text = " "
    model, has_st = _get_model()
    if has_st and model is not None:
        return model.encode(text, convert_to_numpy=True)
    # Fallback: deterministic pseudo-embedding for demo
    np.random.seed(hash(text) % (2**32))
    return np.random.randn(EMBEDDING_DIM).astype("float32") * 0.1


def _load_index():
    """Load FAISS index and metadata from disk if present."""
    _ensure_vector_store()
    index = None
    metadata = []
    if HAS_FAISS and os.path.isfile(INDEX_PATH):
        try:
            index = faiss.read_index(INDEX_PATH)
        except Exception as e:
            logger.warning("Failed to load FAISS index: %s", e)
    if os.path.isfile(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = []
    return index, metadata


def _save_index(index, metadata: list) -> None:
    """Persist FAISS index and metadata."""
    _ensure_vector_store()
    if HAS_FAISS and index is not None:
        try:
            faiss.write_index(index, INDEX_PATH)
        except Exception as e:
            logger.error("Failed to save FAISS index: %s", e)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def _build_text_for_job(job: dict) -> str:
    """Build a single text blob for job embedding."""
    parts = [job.get("title", ""), job.get("description", ""), job.get("skills", ""),
             job.get("company_name", ""), job.get("location", "")]
    return " ".join(str(p) for p in parts if p)


def _build_text_for_candidate(profile: dict, resume_parsed: dict = None) -> str:
    """Build text for candidate from profile and optional parsed resume."""
    parts = [profile.get("headline", ""), profile.get("about", ""),
             profile.get("skills", ""), profile.get("education", ""),
             profile.get("preferred_industries", "")]
    if resume_parsed:
        if isinstance(resume_parsed, str):
            try:
                resume_parsed = json.loads(resume_parsed)
            except Exception:
                resume_parsed = {}
        parts.append(resume_parsed.get("cleaned_text", "")[:3000])
        parts.append(" ".join(resume_parsed.get("skills", [])))
    return " ".join(str(p) for p in parts if p)


def add_job_embedding(job_id: int, job: dict) -> None:
    """Compute job embedding and add to FAISS; update metadata and DB."""
    text = _build_text_for_job(job)
    vec = _get_embedding(text).reshape(1, -1).astype("float32")
    index, metadata = _load_index()

    # Check existing
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT faiss_index FROM embedding_metadata WHERE entity_type = 'job' AND entity_id = ?", (job_id,))
        row = cursor.fetchone()

    if row is not None:
        metadata = [m for m in metadata if not (m.get("type") == "job" and m.get("id") == job_id)]

    if HAS_FAISS:
        if index is None:
            index = faiss.IndexFlatIP(EMBEDDING_DIM)
        faiss.normalize_L2(vec)
        index.add(vec)
        idx = index.ntotal - 1
    else:
        idx = len(metadata)

    metadata.append({"type": "job", "id": job_id, "index": idx})
    _save_index(index, metadata)

    with get_connection() as conn:
        conn.cursor().execute(
            "INSERT OR REPLACE INTO embedding_metadata (entity_type, entity_id, faiss_index) VALUES ('job', ?, ?)",
            (job_id, idx),
        )


def add_candidate_embedding(user_id: int, profile: dict, resume_parsed: dict = None) -> None:
    """Compute candidate embedding and add/update in FAISS."""
    text = _build_text_for_candidate(profile, resume_parsed)
    vec = _get_embedding(text).reshape(1, -1).astype("float32")
    index, metadata = _load_index()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT faiss_index FROM embedding_metadata WHERE entity_type = 'candidate' AND entity_id = ?", (user_id,))
        row = cursor.fetchone()

    if row is not None:
        metadata = [m for m in metadata if not (m.get("type") == "candidate" and m.get("id") == user_id)]

    if HAS_FAISS:
        if index is None:
            index = faiss.IndexFlatIP(EMBEDDING_DIM)
        faiss.normalize_L2(vec)
        index.add(vec)
        idx = index.ntotal - 1
    else:
        idx = len(metadata)

    metadata.append({"type": "candidate", "id": user_id, "index": idx})
    _save_index(index, metadata)

    with get_connection() as conn:
        conn.cursor().execute(
            "INSERT OR REPLACE INTO embedding_metadata (entity_type, entity_id, faiss_index) VALUES ('candidate', ?, ?)",
            (user_id, idx),
        )


def _index_to_id_map(metadata: list, entity_type: str) -> dict:
    """Map FAISS index position -> entity id for given type."""
    return {m["index"]: m["id"] for m in metadata if m.get("type") == entity_type}


def search_jobs_for_candidate(user_id: int, top_k: int = 20) -> list:
    """Get top-k job IDs and similarity scores for a candidate. Returns [{job_id, score}]."""
    index, metadata = _load_index()
    if index is None or not HAS_FAISS:
        return _fallback_jobs_for_candidate(user_id, top_k)

    job_map = _index_to_id_map(metadata, "job")
    if not job_map:
        return _fallback_jobs_for_candidate(user_id, top_k)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return _fallback_jobs_for_candidate(user_id, top_k)
        profile = dict(row)

    text = _build_text_for_candidate(profile, profile.get("resume_parsed_data"))
    vec = _get_embedding(text).reshape(1, -1).astype("float32")
    faiss.normalize_L2(vec)
    k = min(top_k + 5, index.ntotal)
    if k <= 0:
        return _fallback_jobs_for_candidate(user_id, top_k)
    scores, indices = index.search(vec, k)
    results = []
    for s, i in zip(scores[0], indices[0]):
        if i < 0:
            continue
        job_id = job_map.get(i)
        if job_id is not None:
            score = max(0, min(100, float(s) * 100))
            results.append({"job_id": job_id, "score": round(score, 1)})
        if len(results) >= top_k:
            break
    return results


def _fallback_jobs_for_candidate(user_id: int, top_k: int) -> list:
    """When FAISS not available, return jobs with placeholder scores."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM jobs WHERE is_active = 1 ORDER BY created_at DESC LIMIT ?", (top_k,))
        rows = cursor.fetchall()
    return [{"job_id": r["id"], "score": 75.0 + (i % 20)} for i, r in enumerate(rows)]


def search_candidates_for_job(job_id: int, top_k: int = 50) -> list:
    """Get top-k candidate user_ids and match scores for a job. Returns [{user_id, score}]."""
    index, metadata = _load_index()
    if index is None or not HAS_FAISS:
        return _fallback_candidates_for_job(job_id, top_k)

    cand_map_inv = {m["index"]: m["id"] for m in metadata if m.get("type") == "candidate"}
    if not cand_map_inv:
        return _fallback_candidates_for_job(job_id, top_k)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return []
        job = dict(row)

    text = _build_text_for_job(job)
    vec = _get_embedding(text).reshape(1, -1).astype("float32")
    faiss.normalize_L2(vec)
    k = min(top_k + 5, index.ntotal)
    if k <= 0:
        return _fallback_candidates_for_job(job_id, top_k)
    scores, indices = index.search(vec, k)
    results = []
    for s, i in zip(scores[0], indices[0]):
        if i < 0:
            continue
        uid = cand_map_inv.get(i)
        if uid is not None:
            score = max(0, min(100, float(s) * 100))
            results.append({"user_id": uid, "score": round(score, 1)})
        if len(results) >= top_k:
            break
    return results


def _fallback_candidates_for_job(job_id: int, top_k: int) -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM profiles WHERE COALESCE(visibility, 1) = 1 LIMIT ?", (top_k,))
        rows = cursor.fetchall()
    return [{"user_id": r["user_id"], "score": 70.0 + (i % 25)} for i, r in enumerate(rows)]


def get_skill_gap(job_skills: str, candidate_skills: str) -> dict:
    """Return {missing_skills: [], matching_skills: [], match_pct: float}."""
    j_skills = set(s.strip().lower() for s in (job_skills or "").split(",") if s.strip())
    c_skills = set(s.strip().lower() for s in (candidate_skills or "").split(",") if s.strip())
    matching = j_skills & c_skills
    missing = j_skills - c_skills
    total = len(j_skills) or 1
    return {
        "matching_skills": sorted(list(matching)),
        "missing_skills": sorted(list(missing)),
        "match_pct": round(100 * len(matching) / total, 1),
    }


def get_resume_improvement_suggestions(job_skills: str, candidate_skills: str) -> list:
    """Return list of resume improvement suggestions based on skill gap."""
    gap = get_skill_gap(job_skills, candidate_skills)
    suggestions = []
    for skill in gap.get("missing_skills", [])[:5]:
        suggestions.append(f"Add or highlight skill: **{skill.title()}**")
    if not suggestions:
        suggestions.append("Your skills align well with this role. Keep your resume updated.")
    return suggestions
