"""
JobBridge AI - Resume parsing engine.
Extract text from PDF/DOCX, parse skills/education/experience/name/email/phone.
AI-extracts everything — resume is the single source of truth.
"""

import os
import re
import json

# Optional: PyMuPDF (fitz)
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# Optional: python-docx for DOCX resumes
try:
    import docx  # type: ignore[import]
    HAS_DOCX = True
except Exception:
    HAS_DOCX = False

# Strict technical skill keywords (No soft skills, No MS Office)
SKILL_KEYWORDS = {
    "Programming Languages": [
        "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "ruby",
        "php", "swift", "kotlin", "scala", "r", "matlab", "perl", "dart", "lua", "sql"
    ],
    "Frameworks & Libraries": [
        "react", "angular", "vue", "next.js", "node", "express", "django", "flask",
        "fastapi", "spring", "rails", "laravel", "asp.net", "svelte", "nuxt",
        "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy"
    ],
    "Databases": [
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "sql", "nosql",
        "sqlite", "dynamodb", "cassandra", "mariadb", "oracle"
    ],
    "AI / ML / Data": [
        "machine learning", "deep learning", "nlp", "computer vision",
        "natural language processing", "data science", "data analysis",
        "spark", "airflow", "kafka", "hadoop", "databricks", "snowflake"
    ],
    "Cloud & DevOps": [
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
        "ci/cd", "jenkins", "github actions", "linux", "nginx", "apache",
        "serverless", "microservices"
    ],
    "Development Tools": [
        "git", "graphql", "rest api", "api design", "postman", "swagger",
        "bitbucket", "gitlab"
    ]
}

# Mapping for normalization
SKILL_NORMALIZATION = {
    "python3": "Python",
    "ml": "Machine Learning",
    "ai": "AI",
    "js": "JavaScript",
    "ts": "TypeScript",
    "postgres": "PostgreSQL",
}

# Strict degree extraction - anchors and exclusions
EDUCATION_PATTERNS = {
    # Degrees must not be part of "Certificate of..." or "Diploma of..."
    "degree_field": r"(?i)\b(?:b\.?s\.?|b\.?a\.?|b\.?tech|b\.?e\.?|bachelor[s]?|m\.?s\.?|m\.?a\.?|m\.?tech|m\.?e\.?|master[s]?|ph\.?d\.?|mba|m\.?b\.?a\.?)\s*(?:in|of)?\s*([\w\s&,]{3,40})",
    "institution": r"(?i)(?:university|college|institute|school)\s+of\s+([\w\s&,]{3,60})",
    "year": r"\b(20\d{2}|19\d{2})\b"
}

# Noisy phrases that indicate a certificate, not a degree
CERTIFICATE_NOISE = ["completion", "presented to", "successfully", "learning plan", "badge", "certificate", "diploma", "nanodegree"]
EDUCATION_FIELD_EXCLUSIONS = ["solutions", "front-end", "back-end", "full-stack", "developer", "engineer", "intern", "project"]

DOMAIN_KEYWORDS = {
    "Web Development": ["react", "angular", "vue", "html", "css", "django", "flask", "express", "next.js"],
    "AI & Data Science": ["machine learning", "deep learning", "nlp", "tensorflow", "pytorch", "data analysis"],
    "Cloud & DevOps": ["aws", "azure", "docker", "kubernetes", "ci/cd", "terraform"],
    "Database Systems": ["postgresql", "mysql", "mongodb", "schema design", "etl"],
    "Mobile Development": ["android", "ios", "flutter", "react native", "swift", "kotlin"]
}

EXPERIENCE_PATTERNS = [
    r"(?i)(?:\d+\+?\s* years?)\s*(?:of\s*)?(?:experience|exp\.?)",
    r"(?i)(?:experience|exp\.?)\s*:\s*\d+\+?\s*years?",
    r"(?i)\d+\s*-\s*\d+\s*years?\s*(?:of\s*)?experience",
    r"(?i)\d+\s*\+?\s*years?\s+(?:in|of)\s+\w+",
]

# Name patterns and exclusions
NAME_PATTERNS = [
    r"^([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*$",
    r"(?i)name\s*:\s*([A-Za-z\s.\-]{2,50})",
]

# Common role titles frequently appearing in headers that should NOT be extracted as name
ROLE_TITLES = [
    "full stack", "frontend", "backend", "developer", "engineer", "software", "student",
    "intern", "specialist", "architect", "manager", "lead", "designer", "analyst",
    "fresher", "expert", "professional", "development"
]

EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_PATTERN = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"


def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from a PDF file using PyMuPDF."""
    if not HAS_PYMUPDF:
        return ""
    try:
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except Exception:
        return ""


def extract_text_from_docx(file_path: str) -> str:
    """Extract raw text from a DOCX resume."""
    if not HAS_DOCX:
        return ""
    try:
        document = docx.Document(file_path)
        return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        return ""


def clean_text(text: str) -> str:
    """Normalize whitespace and remove noisy characters."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    return text.strip()


def extract_skills(text: str) -> list:
    """Extract skills from text using strict category-based matching."""
    text_lower = text.lower()
    found = set()
    for cat, kws in SKILL_KEYWORDS.items():
        for kw in kws:
            # Word boundary check to avoid partial matches
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                normalized = SKILL_NORMALIZATION.get(kw, kw.title() if len(kw) > 2 else kw.upper())
                found.add(normalized)
    
    # Priority normalization for common tech
    if "Python" in found: found.discard("python")
    if "Sql" in found: found.add("SQL"); found.discard("Sql")
    
    return sorted(list(found))


def extract_education_structured(text: str) -> dict:
    """Extract education in Degree, Field, Institution, Year format with strict noise filtering."""
    cleanup = lambda s: clean_text(s).strip(",. ")
    
    edu = {"degree": "", "field": "", "institution": "", "year": ""}
    
    # Pre-filter text to remove noisy certificate paragraphs and common project noise
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        l_lower = line.lower()
        if any(noise in l_lower for noise in CERTIFICATE_NOISE):
            # Exception: if it's a real degree line like "B.Tech in CS (Certificate attached)"
            if not re.search(r"\b(B\.?Tech|B\.?E\.?|M\.?Tech|B\.?S\.?|MBA)\b", line, re.I):
                continue
        cleaned_lines.append(line)
    
    search_text = " ".join(cleaned_lines)

    # Try degree/field
    m = re.search(EDUCATION_PATTERNS["degree_field"], search_text)
    if m:
        deg = cleanup(m.group(0).split()[0])
        field = cleanup(m.group(1))
        
        # Stricter validation for the field
        f_lower = field.lower()
        if len(field) > 2 and not any(noise in f_lower for noise in CERTIFICATE_NOISE) \
           and not any(ex in f_lower for ex in EDUCATION_FIELD_EXCLUSIONS):
            edu["degree"] = deg
            edu["field"] = field
    
    # Try institution
    m = re.search(EDUCATION_PATTERNS["institution"], search_text)
    if m:
        inst = cleanup(m.group(1))
        i_lower = inst.lower()
        if not any(noise in i_lower for noise in CERTIFICATE_NOISE) \
           and not any(ex in i_lower for ex in EDUCATION_FIELD_EXCLUSIONS):
            edu["institution"] = inst
    
    # Try year
    years = re.findall(EDUCATION_PATTERNS["year"], text) 
    if years:
        edu["year"] = years[-1]
        
    return edu


def extract_domains(skills: list) -> list:
    """Identify project domains based on extracted skills."""
    found_domains = set()
    skills_lower = [s.lower() for s in skills]
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(kw in skills_lower for kw in kws):
            found_domains.add(domain)
    return sorted(list(found_domains))


def generate_professional_summary(skills: list, experience_years: int | None, education: dict) -> str:
    """
    Generate a clean, professional technical summary (max 3 lines).
    Excludes resume bullet copy-paste and noisy certificates.
    """
    if not skills or len(skills) < 2:
        return "Dedicated professional with a focus on technical problem solving and software development."
    
    top_skills = skills[:4]
    level = "Experienced " if (experience_years or 0) >= 3 else "Technical "
    summary = f"{level}professional with core expertise in {', '.join(top_skills)}."
    
    # Only mention degree if it's substantial (e.g. B.Tech, Master, etc)
    if education.get("degree") and education.get("field"):
        degree_lower = education["degree"].lower()
        if any(d in degree_lower for d in ["b.", "m.", "phd", "bachelor", "master"]):
            summary += f" Holds a degree in {education['field']}."
    
    summary += f" Committed to building robust, scalable solutions and staying current with evolving technologies."
    
    return summary[:280] # Limit to ~3 lines


def extract_experience_years(text: str) -> int | None:
    """Extract years of experience if mentioned."""
    for pat in EXPERIENCE_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            nums = re.findall(r"\d+", m.group(0))
            if nums:
                return min(int(nums[0]), 30)
    return None


def determine_experience_level(years: int | None, skills_count: int) -> str:
    """Determine experience level from years and skills count."""
    if years is not None:
        if years >= 5:
            return "Advanced"
        if years >= 2:
            return "Intermediate"
        return "Beginner"
    # Fallback: estimate from skills count
    if skills_count >= 12:
        return "Advanced"
    if skills_count >= 6:
        return "Intermediate"
    return "Beginner"


def extract_name(text: str) -> str | None:
    """Try to extract candidate name from resume text."""
    lines = text.strip().split("\n")
    # Most resumes have name as first non-empty line
    for line in lines[:8]: # Check slightly deeper
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 50:
            continue
        
        l_lower = line.lower()
        # Skip lines that are obviously role titles or contact labels
        if any(role in l_lower for role in ROLE_TITLES):
            if not re.search(r"[A-Z]", line): # If it's all lowercase, definitely not a name
                continue
            # If it's something like "NAGAVISHNU KARTHIK - FRONTEND DEVELOPER", we might want it, 
            # but usually it's a separate line.
            # Stricter: if the whole line is just a role title, skip it.
            if l_lower in ROLE_TITLES:
                continue
            # If it contains common role words but also looks like a name, check cap ratio
            # Names usually have high Cap/Lower ratio if they are in headers
            
        # Check if it looks like a name (mostly alphabetic, 2-4 words)
        words = line.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() and (w.isalpha() or w.replace('.','').isalpha()) for w in words if len(w) > 1):
            # Even if it looks like a name, check if it's purely a role
            if all(w.lower() in ROLE_TITLES for w in words):
                continue
            return line
            
    # Regex fallback
    for pat in NAME_PATTERNS:
        m = re.search(pat, text, re.MULTILINE)
        if m:
            name = m.group(1).strip()
            if 3 <= len(name) <= 50 and not any(role in name.lower() for role in ROLE_TITLES):
                return name
    return None


def extract_email(text: str) -> str | None:
    """Extract email address from resume text."""
    m = re.search(EMAIL_PATTERN, text)
    return m.group(0).lower() if m else None


def extract_phone(text: str) -> str | None:
    """Extract phone number from resume text."""
    m = re.search(PHONE_PATTERN, text)
    return m.group(0).strip() if m else None


def generate_experience_summary(years: int | None, skills: list, education: list) -> str:
    """Generate a brief experience summary from parsed data."""
    parts = []
    if years is not None:
        parts.append(f"{years} years of experience")
    if skills:
        top = skills[:5]
        parts.append(f"skilled in {', '.join(top)}")
    if education:
        parts.append(f"with {education[0]}")
    if parts:
        return ". ".join(parts) + "."
    return "Experience details not found in resume."


def parse_resume(file_path: str) -> dict:
    """
    Resume Intelligence Engine: Extract structured technical data.
    Accuracy > Completeness. No noise.
    """
    try:
        ext = (os.path.splitext(file_path)[1] or "").lower()
        raw = extract_text_from_pdf(file_path) if ext == ".pdf" else extract_text_from_docx(file_path) if ext == ".docx" else ""
        cleaned = clean_text(raw)
        
        skills = extract_skills(cleaned or raw)
        domains = extract_domains(skills)
        education = extract_education_structured(cleaned or raw)
        experience_years = extract_experience_years(cleaned or raw)
        experience_level = determine_experience_level(experience_years, len(skills))
        
        professional_summary = generate_professional_summary(skills, experience_years, education)
        
        return {
            "skills": skills,
            "domains": domains,
            "education": education,
            "professional_summary": professional_summary,
            "experience_years": experience_years,
            "experience_level": experience_level,
            "extracted_name": extract_name(raw),
            "extracted_email": extract_email(cleaned or raw),
            "extracted_phone": extract_phone(cleaned or raw),
            "raw_text": raw,
            "cleaned_text": cleaned
        }
    except Exception as e:
        logger.error(f"Resume parsing failed: {e}")
        return {
            "skills": [],
            "domains": [],
            "education": {"degree": "", "field": "", "institution": "", "year": ""},
            "professional_summary": "",
            "experience_level": "Beginner",
            "extracted_name": None,
            "extracted_email": None,
            "extracted_phone": None,
            "raw_text": "",
            "cleaned_text": ""
        }


def cross_validate(parsed: dict, user_name: str = None, user_email: str = None) -> list[dict]:
    """
    Cross-validate extracted data against user-entered data.
    Returns list of dicts: [{field, status, message}]
    """
    flags = []
    ext_name = parsed.get("extracted_name")
    ext_email = parsed.get("extracted_email")

    if user_name and ext_name:
        if user_name.strip().lower() == ext_name.strip().lower():
            flags.append({"field": "name", "status": "match", "message": f"Name matches resume: {ext_name}"})
        else:
            flags.append({"field": "name", "status": "mismatch", "message": f"Profile name \"{user_name}\" differs from resume name \"{ext_name}\""})
    elif ext_name:
        flags.append({"field": "name", "status": "info", "message": f"Resume name: {ext_name}"})

    if user_email and ext_email:
        if user_email.strip().lower() == ext_email.strip().lower():
            flags.append({"field": "email", "status": "match", "message": f"Email matches resume"})
        else:
            flags.append({"field": "email", "status": "mismatch", "message": f"Account email differs from resume email \"{ext_email}\""})

    return flags


def save_parsed_to_profile(conn, user_id: int, parsed: dict) -> None:
    """
    Store parsed resume data into profiles.resume_parsed_data (JSON).
    Also updates skills, experience_years, experience_level, education in profile.
    """
    cursor = conn.cursor()
    data_json = json.dumps({
        "skills": parsed.get("skills", []),
        "domains": parsed.get("domains", []),
        "education": parsed.get("education", {}),
        "experience_years": parsed.get("experience_years"),
        "experience_level": parsed.get("experience_level", "Beginner"),
        "professional_summary": parsed.get("professional_summary", ""),
        "extracted_name": parsed.get("extracted_name"),
        "extracted_email": parsed.get("extracted_email"),
        "extracted_phone": parsed.get("extracted_phone"),
    })

    # Update profile with AI-extracted data
    skills_csv = ", ".join(parsed.get("skills", []))
    edu = parsed.get("education", {})
    education_text = f"{edu.get('degree','')} in {edu.get('field','')}" if edu.get('degree') else "Not specified"
    experience_years = parsed.get("experience_years")
    experience_level = parsed.get("experience_level", "Beginner")
    experience_desc = parsed.get("professional_summary", "")

    cursor.execute("SELECT id FROM profiles WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute(
            """UPDATE profiles
               SET resume_parsed_data = ?, skills = ?, education = ?,
                   experience_years = ?, experience_level = ?, experience_description = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ?""",
            (data_json, skills_csv, education_text, experience_years, experience_level, experience_desc, user_id),
        )
    else:
        cursor.execute(
            """INSERT INTO profiles (user_id, resume_parsed_data, skills, education,
                   experience_years, experience_level, experience_description, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (user_id, data_json, skills_csv, education_text, experience_years, experience_level, experience_desc),
        )
