"""
JobBridge AI - Certificate verification system.
OCR-based text extraction (Tesseract), validate candidate name and issuer, flag suspicious certificates.
"""

import os
import re
import logging

logger = logging.getLogger("jobbridge_ai")

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Known issuers (expanded)
KNOWN_ISSUERS = [
    "coursera", "edx", "udemy", "linkedin learning", "google", "microsoft", "aws", "amazon",
    "ibm", "meta", "deeplearning.ai", "university", "institute", "certification", "certified",
    "hackerrank", "leetcode", "comptia", "cisco", "oracle", "red hat", "hashicorp",
    "datacamp", "pluralsight", "udacity", "skillshare", "stanford", "mit", "harvard",
]

SUSPICIOUS_PATTERNS = [
    r"100%\s*free", r"guaranteed\s*pass", r"no\s*exam", r"instant\s*certificate",
    r"pay\s*only", r"click\s*here\s*to\s*verify", r"fake", r"template",
    r"sample\s*certificate", r"dummy",
]


def extract_text_from_image(file_path: str) -> str:
    """Extract text using Tesseract OCR from image."""
    if not HAS_OCR:
        return ""
    try:
        img = Image.open(file_path)
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        return pytesseract.image_to_string(img)
    except Exception as e:
        logger.warning("OCR extraction failed for %s: %s", file_path, e)
        return ""


def extract_text_from_pdf_certificate(file_path: str) -> str:
    """Extract text from first page of PDF certificate."""
    try:
        import fitz
        doc = fitz.open(file_path)
        text = doc[0].get_text() if len(doc) > 0 else ""
        doc.close()
        return text
    except Exception as e:
        logger.warning("PDF text extraction failed for %s: %s", file_path, e)
        return ""


def extract_text(file_path: str) -> str:
    """Unified extraction: image or PDF."""
    ext = (os.path.splitext(file_path)[1] or "").lower()
    if ext == ".pdf":
        return extract_text_from_pdf_certificate(file_path)
    return extract_text_from_image(file_path)


def find_candidate_name(text: str, expected_name: str = None) -> str | None:
    """Try to find a candidate/recipient name in certificate text."""
    text_clean = re.sub(r"\s+", " ", text)
    if expected_name:
        if expected_name.strip().lower() in text_clean.lower():
            return expected_name.strip()
    for pattern in [r"(?:awarded\s+to|presented\s+to|name\s*:)\s*([A-Za-z\s.\-]{2,50})",
                    r"(?:certificate\s+of\s+)\w+\s+to\s+([A-Za-z\s.\-]{2,50})"]:
        m = re.search(pattern, text_clean, re.I)
        if m:
            name = m.group(1).strip()
            if 2 <= len(name) <= 50:
                return name
    return None


def find_issuer(text: str) -> str | None:
    """Detect issuer/organization from known list or common patterns."""
    text_lower = text.lower()
    for issuer in KNOWN_ISSUERS:
        if issuer in text_lower:
            return issuer
    m = re.search(r"(?:issued\s+by|from|©|copyright)\s*[:\s]*([A-Za-z0-9\s&.\-]{2,40})", text_lower, re.I)
    if m:
        return m.group(1).strip()[:40]
    return None


def check_suspicious(text: str) -> tuple[bool, list]:
    """Check for suspicious phrases."""
    found = []
    for pat in SUSPICIOUS_PATTERNS:
        if re.search(pat, text, re.I):
            found.append(pat)
    return len(found) > 0, found


def verify_certificate(file_path: str, expected_candidate_name: str = None) -> dict:
    """Full verification pipeline."""
    raw = extract_text(file_path)
    candidate_name = find_candidate_name(raw, expected_candidate_name)
    issuer = find_issuer(raw)
    is_suspicious, suspicious_matches = check_suspicious(raw)
    notes = []
    is_verified = False

    if candidate_name:
        notes.append("Candidate name found.")
        is_verified = True
    else:
        notes.append("Candidate name not clearly found.")

    if issuer:
        notes.append(f"Issuer/organization: {issuer}.")
        is_verified = True
    else:
        notes.append("Issuer not identified.")

    if is_suspicious:
        notes.append("Suspicious phrases detected: " + ", ".join(suspicious_matches))
        is_verified = False

    return {
        "extracted_text": raw[:1500],
        "candidate_name": candidate_name,
        "issuer": issuer,
        "is_verified": is_verified and not is_suspicious,
        "is_suspicious": is_suspicious,
        "verification_notes": " ".join(notes),
    }


def save_verification_result(conn, certificate_id: int, result: dict) -> None:
    """Update certificate record with verification outcome."""
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE certificates SET issuer = ?, candidate_name_extracted = ?, is_verified = ?,
           verification_notes = ?, is_suspicious = ?
           WHERE id = ?""",
        (result.get("issuer"), result.get("candidate_name"),
         1 if result.get("is_verified") else 0,
         result.get("verification_notes"),
         1 if result.get("is_suspicious") else 0,
         certificate_id),
    )
