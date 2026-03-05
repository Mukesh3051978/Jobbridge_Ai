"""
JobBridge AI - Startup and dependency validation.
Run at app load: DB init, dependency check, graceful failure messages.
"""

import logging
import sys

logger = logging.getLogger("jobbridge_ai")

# Configure once at import
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def check_dependencies() -> tuple[bool, list[str]]:
    """
    Verify required and optional dependencies. Returns (all_required_ok, list of warnings).
    """
    errors = []
    warnings = []

    # Required
    try:
        import streamlit  # noqa: F401
    except ImportError:
        errors.append("streamlit is required. Install: pip install streamlit")
    try:
        import bcrypt  # noqa: F401
    except ImportError:
        errors.append("bcrypt is required. Install: pip install bcrypt")
    try:
        import sqlite3  # noqa: F401
    except ImportError:
        errors.append("sqlite3 (standard library) not available.")

    # Optional but recommended
    try:
        import fitz  # noqa: F401
    except ImportError:
        warnings.append("PyMuPDF not installed; PDF resume extraction may be limited.")
    try:
        import docx  # noqa: F401
    except ImportError:
        warnings.append("python-docx not installed; DOCX resumes will not be parsed.")
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except Exception:
        warnings.append("sentence-transformers not available; RAG uses fallback embeddings.")
    try:
        import faiss  # noqa: F401
    except ImportError:
        warnings.append("faiss-cpu not installed; vector search may be limited.")
    try:
        import plotly  # noqa: F401
    except ImportError:
        warnings.append("plotly not installed; radar charts will show text fallback.")
    try:
        import sklearn  # noqa: F401
    except ImportError:
        warnings.append("scikit-learn not installed; ML hire prediction uses rule-based fallback.")

    return (len(errors) == 0, errors + warnings)


def init_app() -> tuple[bool, str | None]:
    """
    Initialize DB and directories. Returns (success, error_message).
    Call once at app startup.
    """
    required_ok, messages = check_dependencies()
    if not required_ok:
        error_lines = [m for m in messages if "required" in m.lower() or "Install:" in m]
        return False, "Missing dependencies: " + "; ".join(error_lines[:5])

    for w in messages:
        logger.warning(w)

    try:
        from database import init_db
        init_db()
        return True, None
    except Exception as e:
        logger.exception("Database initialization failed")
        return False, f"Database could not be initialized: {e}"
