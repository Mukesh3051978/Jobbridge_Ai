"""
JobBridge AI - Main Streamlit application.
AI-powered job portal: Auth, Job Seeker (Profile, Resume, Jobs, AI Interview, Certificates),
Recruiter (Jobs, Candidates), Admin (Analytics).
Production-ready: resume = single source of truth, proper session management, Meta-style UI.
"""

import json
import logging
import os
import re
import uuid
from urllib.parse import quote
import streamlit as st

logger = logging.getLogger("jobbridge_ai")
try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except Exception:
    HAS_PLOTLY = False

from database import (
    create_connection, get_connection, init_db, get_profile, upsert_profile,
    apply_for_job, get_applications_for_user, set_application_status,
    get_application_status, get_candidate_full_profile,
    upsert_company_and_recruiter, get_recruiter_profile,
)
from auth import (
    login_user, register_user, get_user_by_id, ROLE_TO_DB,
    is_admin, is_recruiter, is_job_seeker, update_user_name, update_user_phone,
)
from resume_parser import parse_resume, save_parsed_to_profile, cross_validate
from rag_engine import (
    search_jobs_for_candidate, add_candidate_embedding,
    get_skill_gap, get_resume_improvement_suggestions,
)
from interview_bot import (
    generate_questions, create_session, save_answer, complete_session,
    get_session_scores, get_next_question_for_session, evaluate_answer,
    get_interview_sessions_for_candidate, compute_interview_readiness,
    compute_separate_scores,
)
from certificate_verifier import verify_certificate, save_verification_result
from recruiter import (
    create_job, list_jobs_by_recruiter, list_all_active_jobs,
    get_job_by_id, get_candidates_for_job, get_candidate_skill_gap,
    get_applicants_for_job, add_manual_questions, get_job_questions,
)
from ml_scoring import predict_hire_probability
from admin import (
    get_platform_stats, get_all_users, get_all_jobs,
    get_interview_statistics, get_skill_demand, get_recent_interviews,
)
from ui_components import (
    inject_css, render_circular_progress, render_profile_completion_bar,
    page_header, section_header, vertical_space, toast_success, toast_error,
    render_stat_card, render_skill_cards, render_status_badge,
    render_cross_validation,
)


def _ai_fit_label(match_score: float, hire_prob: float | None) -> str:
    score = match_score or 0
    prob = (hire_prob or 0) * 100
    combined = 0.6 * score + 0.4 * prob
    if combined >= 70:
        return "🟢 Strong Fit"
    if combined >= 40:
        return "🟡 Moderate Fit"
    return "🔴 Weak Fit"


# ---- Page config & session state ----
st.set_page_config(page_title="JobBridge AI", page_icon="💼", layout="wide", initial_sidebar_state="expanded")

for key, default in [("user", None), ("active_page", "Login"), ("init_error", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state.init_error is None:
    try:
        from startup_checks import init_app
        ok, err = init_app()
        if not ok:
            st.session_state.init_error = err
    except Exception as e:
        st.session_state.init_error = str(e)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _validate_upload(file, allowed_types: list) -> str | None:
    if file is None:
        return None
    if file.size > MAX_UPLOAD_BYTES:
        return "File too large (max 10 MB)."
    if allowed_types:
        ext = (file.name or "").rsplit(".", 1)[-1].lower()
        if ext not in [t.lower().lstrip(".") for t in allowed_types]:
            return f"Invalid file type '.{ext}'. Allowed: {', '.join(allowed_types)}."
    return None


def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "upload")
    name = re.sub(r"[^\w\.\- ]+", "_", name)
    return name[:140]


def _unique_upload_path(uid: int, subdir: str, original_name: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(base, "uploads", subdir)
    os.makedirs(folder, exist_ok=True)
    safe = _safe_filename(original_name)
    unique = f"{uid}_{uuid.uuid4().hex[:12]}_{safe}"
    return os.path.join(folder, unique)


def _save_upload(file, path: str, clear_key: str | None = None, success_message: str | None = None) -> None:
    """
    Save an uploaded file safely and optionally clear the uploader widget key.

    clear_key:
        Streamlit widget key for the uploader. We pop it from session_state after saving
        so that reruns don't keep re-triggering the upload block (which causes duplicate
        toasts and repeated saves).
    success_message:
        Optional toast text to show once after a successful save.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(file.getvalue())
    if clear_key:
        st.session_state.pop(clear_key, None)
    if success_message:
        toast_success(success_message)


def calculate_profile_completion(profile: dict | None, user: dict | None = None) -> int:
    if not profile:
        return 0
    score = 0
    if user and user.get("name"):
        score += 20
    if user and user.get("phone"):
        score += 20
    resume_path = profile.get("resume_path")
    if resume_path and os.path.isfile(resume_path):
        score += 30
    if profile.get("resume_parsed_data"):
        score += 10
    if profile.get("profile_photo_path") and os.path.isfile(profile.get("profile_photo_path")):
        score += 20
    return min(100, score)


# ---- Sidebar ----
PAGE_TO_LABEL = {
    "Login": "🔐 Login", "Register": "📝 Register",
    "Dashboard": "📊 Dashboard", "Profile": "👤 Profile", "Jobs": "💼 Jobs",
    "My Applications": "📄 My Applications", "AI Interview": "🤖 AI Interview",
    "Certificates": "📜 Certificates",
    "Recruiter Dashboard": "📊 Recruiter Dashboard", "Recruiter Profile": "🏢 Recruiter Profile",
    "Post Job": "➕ Post Job", "My Jobs": "📋 My Jobs",
    "Admin Dashboard": "⚙️ Admin",
}


def render_sidebar():
    inject_css()
    with st.sidebar:
        st.markdown("<div class='sidebar-brand'>💼 JobBridge AI</div><div class='sidebar-tagline'>AI-powered job portal</div>", unsafe_allow_html=True)
        st.markdown("---")
        if st.session_state.user is None:
            pages = ["🔐 Login", "📝 Register"]
        else:
            role_db = st.session_state.user.get("role_db", "")
            if is_admin(role_db):
                pages = ["📊 Dashboard", "👤 Profile", "💼 Jobs", "🤖 AI Interview", "📜 Certificates", "⚙️ Admin"]
            elif is_recruiter(role_db):
                pages = ["📊 Recruiter Dashboard", "🏢 Recruiter Profile", "➕ Post Job", "📋 My Jobs"]
            else:
                pages = ["📊 Dashboard", "👤 Profile", "💼 Jobs", "📄 My Applications", "🤖 AI Interview", "📜 Certificates"]
        page_map = {
            "🔐 Login": "Login", "📝 Register": "Register",
            "📊 Dashboard": "Dashboard", "👤 Profile": "Profile", "💼 Jobs": "Jobs",
            "📄 My Applications": "My Applications", "🤖 AI Interview": "AI Interview",
            "📜 Certificates": "Certificates",
            "📊 Recruiter Dashboard": "Recruiter Dashboard", "🏢 Recruiter Profile": "Recruiter Profile",
            "➕ Post Job": "Post Job", "📋 My Jobs": "My Jobs", "⚙️ Admin": "Admin Dashboard",
        }
        pending = st.session_state.pop("pending_nav_label", None)
        if pending and pending in pages:
            st.session_state["nav_radio"] = pending
        if "nav_radio" not in st.session_state or st.session_state["nav_radio"] not in pages:
            label = PAGE_TO_LABEL.get(st.session_state.active_page)
            st.session_state["nav_radio"] = label if label in pages else pages[0]
        choice = st.radio("Go to", pages, label_visibility="collapsed", key="nav_radio")
        st.session_state.active_page = page_map.get(choice, "Dashboard")
        if st.session_state.user:
            st.markdown("---")
            st.caption(f"**{st.session_state.user.get('name')}**")
            st.caption(st.session_state.user.get("role", ""))
            if st.button("Logout", use_container_width=True):
                # Clear per-user caches
                for k in ("_seeker_photo_path", "_recruiter_photo_path", "selected_job_id"):
                    st.session_state.pop(k, None)
                st.session_state.user = None
                st.session_state.active_page = "Login"
                st.session_state.pop("nav_radio", None)
                st.rerun()


# ---- Auth ----
def render_login():
    page_header("Welcome to JobBridge AI", "Sign in to continue.")
    vertical_space(18)
    st.markdown("<div style='display:flex;justify-content:center;'><div class='jb-auth-kicker'>🔐 Secure sign-in</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='auth-card-marker'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        email = st.text_input("Email address", placeholder="you@company.com", key="login_email")
        
        password = st.text_input("Password", type="password", 
                                placeholder="Enter your password", key="login_password")
        
        vertical_space(10)
        submitted = st.button("Continue", type="primary", use_container_width=True)

    st.markdown("<div class='jb-auth-hint'>Tip: Use a strong password and avoid public devices.</div>", unsafe_allow_html=True)
    
    if submitted:
        if not email or not password:
            toast_error("Please enter email and password.")
        else:
            user = login_user(email, password)
            if user:
                st.session_state.user = user
                role_db = user.get("role_db", "")
                if is_admin(role_db):
                    st.session_state.active_page = "Admin Dashboard"
                elif is_recruiter(role_db):
                    st.session_state.active_page = "Recruiter Dashboard"
                else:
                    st.session_state.active_page = "Dashboard"
                toast_success("Logged in successfully.")
                st.rerun()
            else:
                toast_error("Invalid email or password.")


def render_register():
    page_header("Create account", "Join JobBridge AI.")
    vertical_space(18)
    st.markdown("<div class='jb-auth-marker'></div>", unsafe_allow_html=True)
    st.markdown("<div style='display:flex;justify-content:center;'><div class='jb-auth-kicker'>📝 New account</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='auth-card-marker'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        role = st.radio("I am a", ["Job Seeker", "Recruiter"], horizontal=True, key="reg_role")
        name = st.text_input("Full name", placeholder="Jane Doe", key="reg_name")
        email = st.text_input("Email address", placeholder="jane@example.com", key="reg_email")
        
        col_phone1, col_phone2 = st.columns([1, 3])
        with col_phone1:
            country_code = st.selectbox("Code", ["+91", "+1", "+44", "+61", "+81", "+49", "+33", "+86", "+971", "+65"], index=0, key="reg_country_code")
        with col_phone2:
            phone_num = st.text_input("Phone number", placeholder="1234567890", key="reg_phone_num")
        phone = f"{country_code} {phone_num}" if phone_num else ""
        
        password = st.text_input("Password", type="password", 
                                placeholder="Create a password", key="reg_password")
        confirm = st.text_input("Confirm password", type="password", 
                               placeholder="Re-enter password", key="reg_confirm")
        
        vertical_space(10)
        agree = st.checkbox("I agree to the Terms and Privacy Policy", key="reg_agree")
        submitted = st.button("Create account", type="primary", use_container_width=True)

    if submitted:
        if not agree:
            toast_error("Please accept Terms and Privacy Policy.")
        elif password != confirm:
            toast_error("Passwords do not match.")
        elif len(password) < 6:
            toast_error("Password must be at least 6 characters.")
        elif not phone or len(phone.strip()) < 7:
            toast_error("Please enter a valid phone number.")
        else:
            ok, msg = register_user(name, email, password, role, phone)
            if ok:
                toast_success(msg)
                st.info("Go to Login to sign in.")
            else:
                toast_error(msg)


# ---- Job Seeker Profile (Minimal: name, phone, resume, photo. AI extracts the rest.) ----
def render_profile():
    uid = st.session_state.user["id"]
    user = get_user_by_id(uid) or st.session_state.user
    profile = get_profile(uid) or {}

    page_header("Profile", "Upload your resume — AI extracts skills, experience & education automatically.")
    vertical_space(20)

    # Basic info form
    with st.form("profile_form"):
        name = st.text_input("Full name", value=user.get("name", ""), placeholder="Your name")
        st.text_input("Email", value=user.get("email", ""), disabled=True, key="profile_email")
        current_phone = user.get("phone") or ""
        codes = ["+91", "+1", "+44", "+61", "+81", "+49", "+33", "+86", "+971", "+65"]
        def_code = "+91"
        def_num = current_phone
        if " " in current_phone:
            parts = current_phone.split(" ", 1)
            if parts[0] in codes:
                def_code = parts[0]
                def_num = parts[1]

        col_p1, col_p2 = st.columns([1, 3])
        with col_p1:
            country_code = st.selectbox("Code", codes, index=codes.index(def_code) if def_code in codes else 0)
        with col_p2:
            phone_num = st.text_input("Phone", value=def_num, placeholder="1234567890")
        phone = f"{country_code} {phone_num}" if phone_num else ""
        location = st.text_input("Location (optional)", value=profile.get("location") or "", placeholder="City, Country")
        visible_default = bool(profile.get("visibility", 1))
        visibility = st.toggle("Profile visible to recruiters", value=visible_default)
        submitted = st.form_submit_button("Save details", type="primary")
    if submitted:
        if name and name.strip():
            update_user_name(uid, name)
        if phone:
            update_user_phone(uid, phone)
        upsert_profile(uid, location=(location.strip() or None), visibility=1 if visibility else 0)
        st.session_state.user["name"] = name.strip()
        st.session_state.user["phone"] = phone.strip()
        toast_success("Profile saved.")
        st.rerun()

    # Resume upload
    vertical_space(24)
    section_header("📄 Resume (PDF or DOCX)", "AI will extract skills, experience & education automatically.")
    resume_path = profile.get("resume_path")
    if resume_path and os.path.isfile(resume_path):
        st.caption(f"**Current resume:** {os.path.basename(resume_path)}")
        with open(resume_path, "rb") as f:
            st.download_button("⬇️ Download resume", f, file_name=os.path.basename(resume_path), use_container_width=True)
        if profile.get("resume_parsed_data"):
            st.success("✅ AI analysis complete — skills and experience stored.")
        else:
            st.warning("⚠️ AI analysis not run. Re-upload to trigger.")
    else:
        st.info("No resume yet. Upload below to get started.")

    resume_file = st.file_uploader("Upload resume (max 10 MB)", type=["pdf", "docx"], key="resume_upload")
    if resume_file:
        err = _validate_upload(resume_file, ["pdf", "docx"])
        if err:
            toast_error(err)
        else:
            path = _unique_upload_path(uid, "resumes", resume_file.name)
            analysis_ok = False
            with st.status("🔄 Processing resume…", expanded=True) as status:
                try:
                    _save_upload(resume_file, path, clear_key="resume_upload")
                    st.write("✅ File saved")
                    parsed = parse_resume(path)
                    st.write(f"✅ Extracted {len(parsed.get('skills', []))} skills")
                    with get_connection() as conn:
                        save_parsed_to_profile(conn, uid, parsed)
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM profiles WHERE user_id = ?", (uid,))
                        if cursor.fetchone():
                            cursor.execute("UPDATE profiles SET resume_path = ? WHERE user_id = ?", (path, uid))
                        else:
                            cursor.execute("INSERT INTO profiles (user_id, resume_path) VALUES (?, ?)", (uid, path))
                    try:
                        add_candidate_embedding(uid, get_profile(uid) or {}, parsed)
                        st.write("✅ AI matching index updated")
                    except Exception:
                        pass
                    status.update(label="✅ Resume processed", state="complete")
                    analysis_ok = True
                except Exception as e:
                    status.update(label="❌ Error", state="error")
                    st.error(f"AI analysis failed: {e}")
                    try:
                        upsert_profile(uid, resume_path=path)
                    except Exception:
                        pass
            logger.info("Resume upload user_id=%s path=%s ok=%s", uid, path, analysis_ok)
            toast_success("Resume saved. Skills extracted." if analysis_ok else "Resume saved; AI analysis had an error.")
            st.rerun()

    # Show AI-extracted data
    profile = get_profile(uid) or {}
    parsed = {}
    if profile.get("resume_parsed_data"):
        try:
            parsed = json.loads(profile["resume_parsed_data"])
        except Exception:
            pass

    if parsed:
        vertical_space(24)
        section_header("🤖 AI-Extracted from Resume", "")
        cv_flags = cross_validate(parsed, user.get("name"), user.get("email"))
        if cv_flags:
            render_cross_validation(cv_flags)
            vertical_space(8)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Skills**")
            render_skill_cards(parsed.get("skills", []))
            exp = parsed.get("experience_years")
            level = parsed.get("experience_level", "")
            if exp is not None:
                st.caption(f"**Experience:** {exp} years · **Level:** {level}")
            elif level:
                st.caption(f"**Level:** {level}")
        with col2:
            st.markdown("**Education**")
            edu = parsed.get("education")
            if isinstance(edu, dict) and edu.get("degree"):
                st.caption(f"🎓 **{edu.get('degree')}** in {edu.get('field')}")
                st.caption(f"🏛️ {edu.get('institution')} ({edu.get('year', 'N/A')})")
            elif isinstance(edu, list):
                for line in edu[:5]:
                    st.caption(f"🎓 {line}" if line else "")
            else:
                st.caption("— No structured education data —")
            
            domains = parsed.get("domains") or []
            if domains:
                st.markdown("**Technical Domains**")
                st.caption(", ".join(domains))
            
            summary = parsed.get("professional_summary") or parsed.get("experience_summary")
            if summary:
                st.markdown("**AI Summary**")
                st.caption(summary)

    # Photo upload — save first, then display so photo appears immediately
    vertical_space(24)
    section_header("📸 Profile Photo", "")

    # If a file is uploaded in this render cycle, process it immediately
    photo = st.file_uploader("Upload photo (JPG/PNG, max 10 MB)", type=["jpg", "jpeg", "png"], key="photo_upload")
    if photo is not None:
        err = _validate_upload(photo, ["jpg", "jpeg", "png"])
        if err:
            toast_error(err)
        else:
            try:
                path = _unique_upload_path(uid, "photos", photo.name)
                _save_upload(photo, path)  # write file to disk (don't pop key yet)
                upsert_profile(uid, profile_photo_path=path)
                # Cache the path in session state so we display it immediately
                st.session_state["_seeker_photo_path"] = path
                st.session_state.pop("photo_upload", None)   # reset widget for next render
                toast_success("✅ Photo uploaded!")
            except Exception as e:
                toast_error(f"Photo upload failed: {e}")
                logger.exception("Photo upload failed user_id=%s", uid)

    # Determine which photo to display: session-state cache > DB
    _cached = st.session_state.get("_seeker_photo_path")
    if _cached and os.path.isfile(_cached):
        current_photo = _cached
    else:
        profile_fresh = get_profile(uid) or {}
        current_photo = profile_fresh.get("profile_photo_path")
        if current_photo:
            st.session_state["_seeker_photo_path"] = current_photo  # warm cache

    if current_photo and os.path.isfile(current_photo):
        st.image(current_photo, width=120, caption="✅ Current photo")
    else:
        st.caption("No photo uploaded yet.")


# ---- Job Seeker Dashboard ----
def render_dashboard():
    uid = st.session_state.user["id"]
    user = get_user_by_id(uid) or st.session_state.user
    profile = get_profile(uid) or {}
    page_header("Dashboard", "Your AI-powered career overview.")
    vertical_space(20)

    completion = calculate_profile_completion(profile, user)
    parsed = {}
    if profile.get("resume_parsed_data"):
        try:
            parsed = json.loads(profile["resume_parsed_data"])
        except Exception:
            pass

    try:
        readiness = compute_interview_readiness(uid)
    except Exception:
        readiness = 0.0

    # Top stats row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_stat_card(f"{completion}%", "Profile Complete", "👤")
    with c2:
        has_resume = bool(profile.get("resume_path") and os.path.isfile(profile.get("resume_path", "")))
        render_stat_card("✅" if has_resume else "❌", "Resume Uploaded", "📄")
    with c3:
        level = parsed.get("experience_level", "—")
        render_stat_card(level, "Experience Level", "📈")
    with c4:
        render_stat_card(f"{readiness:.0f}%", "Interview Ready", "🤖")

    # Profile completion bar
    vertical_space(8)
    render_profile_completion_bar(completion)
    if completion < 100:
        missing = []
        if not user.get("phone"):
            missing.append("phone number")
        if not (profile.get("resume_path") and os.path.isfile(profile.get("resume_path", ""))):
            missing.append("resume")
        if not (profile.get("profile_photo_path") and os.path.isfile(profile.get("profile_photo_path", ""))):
            missing.append("profile photo")
        if missing:
            st.caption(f"Complete your profile: add **{', '.join(missing)}** in the Profile tab.")

    # Skills
    vertical_space(20)
    section_header("🛠️ AI-Extracted Skills", "")
    skills = parsed.get("skills", [])
    if skills:
        render_skill_cards(skills, max_show=25)
    else:
        st.caption("Upload a resume in **Profile** to extract skills.")

    if profile.get("resume_path") and os.path.isfile(profile["resume_path"]):
        vertical_space(16)
        c_res1, c_res2 = st.columns([2, 1])
        with c_res1:
            with open(profile["resume_path"], "rb") as f:
                st.download_button("⬇️ Download resume", f, file_name=os.path.basename(profile["resume_path"]), use_container_width=True)
        with c_res2:
            if parsed.get("professional_summary"):
                st.button("✨ Refine Summary", on_click=lambda: toast_success("Refreshing AI Summary..."))

    # Applied jobs
    vertical_space(20)
    section_header("📄 Applied Jobs", "")
    apps = get_applications_for_user(uid)
    if not apps:
        st.caption("None yet. Go to **Jobs** to apply.")
    else:
        for a in apps[:10]:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                salary_txt = f" · {a.get('salary')}" if a.get("salary") else ""
                st.markdown(f"**{a['title']}** @ {a.get('company_name', '')}{salary_txt}")
                # Show interview status
                sessions = get_interview_sessions_for_candidate(uid, a["job_id"])
                if sessions:
                    s = sessions[0]["session"]
                    if s.get("recruiter_score") is not None:
                        score = float(s["recruiter_score"])
                        st.caption(f"Interview: **Verified** · Score: {score:.1f}/10")
                    else:
                        st.caption("Interview: **Pending Recruiter Review** ⏳")
                else:
                    job = get_job_by_id(a["job_id"])
                    if job and job.get("interview_enabled"):
                        st.caption("Interview: **Pending**")
            with col_b:
                render_status_badge(a["status"])

    # Top matches
    vertical_space(20)
    section_header("🎯 Top Job Matches", "")
    matches = search_jobs_for_candidate(uid, top_k=5)
    if not matches:
        st.caption("Upload a resume in **Profile** for AI matches.")
    for m in matches[:5]:
        job = get_job_by_id(m["job_id"])
        if job:
            salary_txt = f" · {job.get('salary')}" if job.get("salary") else ""
            st.markdown(f"• **{job.get('title')}** — {m['score']}% match{salary_txt}")


# ---- Jobs ----
def render_jobs():
    uid = st.session_state.user["id"]
    profile = get_profile(uid) or {}
    page_header("Explore Jobs", "AI-ranked matches and skill gap analysis.")
    vertical_space(20)
    keyword = st.text_input("🔍 Search jobs", placeholder="e.g. Data Analyst, Python")
    vertical_space(16)
    jobs = list_all_active_jobs(100)
    try:
        match_map = {m["job_id"]: m["score"] for m in search_jobs_for_candidate(uid, top_k=50)}
    except Exception:
        match_map = {}
    for job in jobs:
        if keyword and keyword.lower() not in (job.get("title") or "").lower() and keyword.lower() not in (job.get("description") or "").lower():
            continue
        score = match_map.get(job["id"], 0)
        app_status = get_application_status(uid, job["id"])
        status_label = f" · {app_status.title()}" if app_status else ""
        salary_txt = f" · {job.get('salary')}" if job.get("salary") else ""
        with st.expander(f"**{job['title']}** — {job.get('company_name', 'N/A')} · {score}% match{salary_txt}{status_label}"):
            st.write(job.get("description", "")[:500] + ("..." if len(job.get("description", "")) > 500 else ""))
            sg = get_skill_gap(job.get("skills") or "", profile.get("skills") or "")
            matching = sg.get("matching_skills", [])
            missing = sg.get("missing_skills", [])
            st.markdown("**Required skills**")
            if job.get("skills"):
                chips = [s.strip() for s in job["skills"].split(",") if s.strip()][:12]
                render_skill_cards(chips)
            if matching or missing:
                st.caption(f"Skill match: **{sg.get('match_pct', 0)}%** · Matched: {', '.join(matching[:6]) or '—'} · Missing: {', '.join(missing[:6]) or '—'}")
            st.caption(f"📍 {job.get('location', 'N/A')} | 💼 {job.get('job_type', 'Full-time')}")
            suggestions = get_resume_improvement_suggestions(job.get("skills") or "", profile.get("skills") or "")
            if suggestions:
                st.markdown("**💡 Resume tips:**")
                for s in suggestions:
                    st.markdown(f"- {s}")
            if app_status:
                render_status_badge(app_status)
            else:
                if job.get("interview_enabled"):
                    st.info("💡 Application to this job requires a skill-based AI interview.")
                if st.button("Apply", key=f"apply_{job['id']}", type="primary"):
                    ok, msg = apply_for_job(uid, job["id"], match_score=score)
                    if ok:
                        toast_success(msg)
                        if job.get("interview_enabled"):
                            st.session_state.active_page = "AI Interview"
                        st.rerun()
                    else:
                        toast_error(msg)


# ---- My Applications ----
def render_my_applications():
    uid = st.session_state.user["id"]
    page_header("My Applications", "Track your application status.")
    vertical_space(20)
    apps = get_applications_for_user(uid)
    if not apps:
        st.info("You haven't applied to any jobs yet. Go to **Jobs** to apply.")
        return
    for a in apps:
        col_a, col_b = st.columns([3, 1])
        with col_a:
            salary_txt = f" · {a.get('salary')}" if a.get("salary") else ""
            st.markdown(f"**{a['title']}** @ {a.get('company_name', 'N/A')} · {a.get('location', '')}{salary_txt}")
            st.caption(f"Match: {a.get('match_score') or '—'}% · Applied: {a.get('created_at', '')}")
        with col_b:
            render_status_badge(a["status"])
        st.markdown("---")


# ---- AI Interview ----
def render_ai_interview():
    uid = st.session_state.user["id"]
    page_header("AI Interview", "Skill-based technical interviews generated from your profile and job requirements.")
    vertical_space(20)
    
    # Session state for interview
    for key, default in [("interview_session_id", None), ("interview_questions", []), ("chat_history", []), ("current_q_idx", 0)]:
        if key not in st.session_state:
            st.session_state[key] = default

    # If no active session, show practice options or pending interviews
    if not st.session_state.interview_session_id:
        apps = get_applications_for_user(uid)
        interview_jobs = []
        for a in apps:
            job = get_job_by_id(a["job_id"])
            if job and job.get("interview_enabled"):
                # Check if interview already completed for this job
                sessions = get_interview_sessions_for_candidate(uid, a["job_id"])
                if not sessions:
                    interview_jobs.append(job)

        if interview_jobs:
            st.markdown("### 📝 Pending Job Interviews")
            for j in interview_jobs:
                col_j, col_b = st.columns([3, 1])
                with col_j:
                    st.markdown(f"**{j['title']}** @ {j.get('company_name', 'N/A')}")
                    st.caption(f"Mode: {j.get('interview_mode', 'AI')} · Required skills: {j.get('skills')}")
                with col_b:
                    if st.button("Start Interview", key=f"start_int_{j['id']}", type="primary", use_container_width=True):
                        # Start interview logic
                        difficulty = j.get("experience_level") or "Intermediate"
                        questions = generate_questions(j["id"], user_id=uid, num_questions=5, difficulty=difficulty)
                        sid = create_session(uid, j["id"], j["title"], difficulty=difficulty)
                        st.session_state.interview_questions = questions
                        st.session_state.interview_job_id = j["id"]
                        st.session_state.interview_session_id = sid
                        st.session_state.current_q_idx = 0
                        st.rerun()
            st.markdown("---")

        st.markdown("### 🎯 Practice Session")
        col1, col2 = st.columns(2)
        all_jobs = list_all_active_jobs(50)
        job_options = [None] + [j["id"] for j in all_jobs]
        def _job_label(x):
            if x is None: return "General Practice"
            j = get_job_by_id(x)
            return j["title"] if j else str(x)
        
        with col1:
            pract_job_id = st.selectbox("Select role for practice", options=job_options, format_func=_job_label)
        with col2:
            pract_diff = st.selectbox("Difficulty", ["Beginner", "Intermediate", "Advanced"], index=1)
        
        if st.button("▶️ Start Practice Interview", type="primary"):
            questions = generate_questions(pract_job_id, user_id=uid, num_questions=5, difficulty=pract_diff)
            job_title = "General"
            if pract_job_id:
                pj = get_job_by_id(pract_job_id)
                if pj: job_title = pj["title"]
            sid = create_session(uid, pract_job_id, job_title, difficulty=pract_diff)
            st.session_state.interview_questions = questions
            st.session_state.interview_job_id = pract_job_id
            st.session_state.interview_session_id = sid
            st.session_state.current_q_idx = 0
            st.rerun()

    else:
        # Active Interview UI - Card Based
        questions = st.session_state.interview_questions
        current_idx = st.session_state.current_q_idx
        
        if current_idx < len(questions):
            q = questions[current_idx]
            
            # Progress bar
            progress = (current_idx) / len(questions)
            st.progress(progress, text=f"Question {current_idx + 1} of {len(questions)}")
            
            # Premium Question Card
            from ui_components import render_interview_question_card
            render_interview_question_card(q['text'])
            
            vertical_space(20)
            st.markdown("<div class='no-copy-paste'>", unsafe_allow_html=True)
            user_ans = st.text_area("Your Answer", key=f"ans_{current_idx}", height=200, placeholder="Explain your approach, provide code samples if relevant...")
            st.markdown("</div>", unsafe_allow_html=True)
            
            col_left, col_right = st.columns([4, 1])
            with col_right:
                if st.button("Next Question →", type="primary", use_container_width=True):
                    if user_ans.strip():
                        with st.spinner("AI evaluating..."):
                            job_title = "General"
                            _jid = st.session_state.get("interview_job_id")
                            if _jid:
                                j = get_job_by_id(_jid)
                                if j: job_title = j["title"]
                            
                            ev = evaluate_answer(q["text"], user_ans, job_title)
                            save_answer(st.session_state.interview_session_id, q["text"], user_ans, ev.get("score", 0), ev.get("feedback", ""), q["order"], q["type"])
                            
                            st.session_state.current_q_idx += 1
                            st.rerun()
                    else:
                        st.warning("Please provide an answer before continuing.")
        else:
            # Interview Complete
            overall, technical, aptitude = compute_separate_scores(st.session_state.interview_session_id)
            complete_session(st.session_state.interview_session_id, overall, technical, aptitude)
            
            # Update readiness
            readiness = compute_interview_readiness(uid)
            upsert_profile(uid, interview_readiness_score=readiness)
            
            st.balloons()
            st.success("🎉 Interview Completed!")
            
            st.info("📨 **Submitted for Review**: Your answers have been safely submitted to the recruiter. Marks and feedback will appear in your dashboard once the recruiter has validated your performance.")

            if st.button("Return to Dashboard"):
                st.session_state.interview_session_id = None
                st.session_state.interview_questions = []
                st.session_state.current_q_idx = 0
                st.session_state.active_page = "Dashboard"
                st.rerun()


# ---- Certificates ----
def render_certificates():
    uid = st.session_state.user["id"]
    page_header("Certificates", "Upload and verify certificates.")
    vertical_space(20)
    cert_file = st.file_uploader("Upload certificate (PDF or image, max 10 MB)", type=["pdf", "png", "jpg", "jpeg"], key="cert_upload")
    if cert_file:
        err = _validate_upload(cert_file, ["pdf", "png", "jpg", "jpeg"])
        if err:
            toast_error(err)
        else:
            path = _unique_upload_path(uid, "certificates", cert_file.name)
            _save_upload(cert_file, path, clear_key="cert_upload")
            try:
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO certificates (user_id, file_path, original_filename) VALUES (?, ?, ?)", (uid, path, cert_file.name))
                    cert_id = cursor.lastrowid
                    result = verify_certificate(path, expected_candidate_name=st.session_state.user.get("name"))
                    save_verification_result(conn, cert_id, result)
                verified = "✅" if result.get("is_verified") else "❌"
                suspicious = "⚠️ Suspicious" if result.get("is_suspicious") else "✅ Clean"
                st.success(f"Uploaded. Verified: {verified} · {suspicious}")
                st.rerun()
            except Exception as e:
                toast_error(f"Certificate upload failed: {e}")

    vertical_space(24)
    section_header("📜 Your Certificates", "")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM certificates WHERE user_id = ? ORDER BY created_at DESC", (uid,))
            rows = [dict(r) for r in cursor.fetchall()]
    except Exception:
        rows = []
    for r in rows:
        verified_icon = "✅" if r.get("is_verified") else "❌"
        suspicious_icon = "⚠️" if r.get("is_suspicious") else ""
        st.markdown(f"- **{r['original_filename']}** — {verified_icon} {suspicious_icon} {r.get('verification_notes') or ''}")


# ---- Recruiter pages (Part 2 of app.py continues below) ----

def _experience_level_to_years(level: str) -> tuple[int | None, int | None]:
    if level == "Beginner":
        return 0, 2
    if level == "Intermediate":
        return 2, 5
    if level == "Advanced":
        return 5, 15
    return None, None


def render_post_job():
    uid = st.session_state.user["id"]
    page_header("Post a Job", "AI will match applicants to this role.")
    vertical_space(20)
    
    # Session state initialization for the wizard
    if "job_created" not in st.session_state:
        st.session_state.job_created = False
    if "created_job_id" not in st.session_state:
        st.session_state.created_job_id = None
    if "created_job_title" not in st.session_state:
        st.session_state.created_job_title = ""

    rec = get_recruiter_profile(uid) or {}
    default_company = rec.get("company_name") or ""

    if not st.session_state.job_created:
        # STEP 1: JOB DETAILS FORM
        with st.form("post_job"):
            title = st.text_input("Job title", placeholder="e.g. Backend Engineer")
            skills = st.text_input("Required skills (comma separated)", placeholder="Python, SQL, APIs")
            col1, col2 = st.columns(2)
            with col1:
                experience_level = st.selectbox("Experience level", ["Beginner", "Intermediate", "Advanced"])
            with col2:
                salary = st.text_input("Salary range", placeholder="e.g. $80k-$120k / year")
            location = st.text_input("Location", placeholder="City or Remote")
            description = st.text_area("Job description", placeholder="Responsibilities, requirements, what you offer.")
            
            st.markdown("---")
            section_header("🤖 Interview Settings", "Enable AI or Manual skill-based interview.")
            int_enabled = st.checkbox("Enable Interview", value=True)
            int_mode = st.radio("Interview Mode", ["AI", "Manual"], horizontal=True)
            
            submitted = st.form_submit_button("Create Job", type="primary")

        if submitted:
            if not title or not description or not skills:
                toast_error("Please fill in all required fields.")
                return

            exp_min, exp_max = _experience_level_to_years(experience_level)
            jid = create_job(uid, title, description, skills, 
                            experience_min=exp_min, experience_max=exp_max, 
                            salary=salary or None, location=location or None, 
                            job_type="Full-time", company_name=default_company or None, 
                            interview_enabled=1 if int_enabled else 0, 
                            interview_mode=int_mode)
            
            if jid:
                st.session_state.job_created = True
                st.session_state.created_job_id = jid
                st.session_state.created_job_title = title
                st.session_state.created_job_mode = int_mode
                toast_success("Job created successfully! Now configure the interview.")
                st.rerun()
            else:
                toast_error("Failed to create job.")

    else:
        # STEP 2: INTERVIEW CONFIGURATION (Read-only Job Summary + Manual Questions if needed)
        st.success(f"🎉 Job Created: **{st.session_state.created_job_title}** (ID: {st.session_state.created_job_id})")
        
        if st.session_state.created_job_mode == "Manual":
            section_header("📝 Manual Interview Questions", f"Add questions for {st.session_state.created_job_title}")
            st.info("Since you chose Manual mode, please provide the questions now. These will be shown to candidates during their interview.")
            
            with st.form("manual_questions_form"):
                questions_data = []
                for i in range(5):
                    q_text = st.text_area(f"Question {i+1}", key=f"q_{i}", height=100, placeholder="Enter a technical or domain-specific question...")
                    if q_text:
                        questions_data.append({"text": q_text, "difficulty": "Intermediate"})
                
                q_submitted = st.form_submit_button("Save Questions", type="primary")
                
            if q_submitted:
                if not questions_data:
                    st.warning("Please add at least one question.")
                else:
                    add_manual_questions(st.session_state.created_job_id, questions_data)
                    toast_success("Questions saved successfully!")
        else:
            st.info("AI Interview mode is active. Questions will be generated automatically based on the job requirements.")

        vertical_space(40)
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("📁 Go to My Jobs", use_container_width=True):
                st.session_state.active_page = "My Jobs"
                st.session_state.job_created = False # Reset for next use
                st.rerun()
        with c2:
            if st.button("➕ Post Another Job", use_container_width=True):
                st.session_state.job_created = False
                st.session_state.created_job_id = None
                st.rerun()
        with c3:
            if st.button("📊 View Dashboard", use_container_width=True):
                st.session_state.active_page = "Recruiter Dashboard"
                st.session_state.job_created = False # Reset for next use
                st.rerun()


def render_my_jobs():
    uid = st.session_state.user["id"]
    page_header("My Jobs", "Manage your job postings.")
    vertical_space(20)
    jobs = list_jobs_by_recruiter(uid, active_only=False)
    if not jobs:
        st.info("No jobs posted yet. Go to **Post Job** to create one.")
        return
    for j in jobs:
        with st.expander(f"{j['title']} @ {j.get('company_name') or 'Company'} · {j.get('salary') or '—'}"):
            ca, cb = st.columns([4, 1])
            with ca:
                st.write(f"**Location:** {j.get('location') or 'Not specified'}")
                st.write(f"**Skills:** {j.get('skills')}")
                st.write(f"**Description:** {j.get('description')[:200]}...")
            with cb:
                if st.button("👥 View Candidates", key=f"view_{j['id']}", use_container_width=True):
                    st.session_state.selected_job_id = j["id"]
                    st.session_state.active_page = "Recruiter Dashboard"
                    st.rerun()
                
                if st.button("🗑️ Delete Job", key=f"del_{j['id']}", use_container_width=True):
                    with get_connection() as conn:
                        conn.cursor().execute("DELETE FROM jobs WHERE id = ? AND recruiter_id = ?", (j["id"], uid))
                    toast_success("Job deleted.")
                    st.rerun()


def render_recruiter_profile():
    uid = st.session_state.user["id"]
    data = get_recruiter_profile(uid) or {}
    page_header("Recruiter & Company Profile", "What candidates see on your postings.")
    vertical_space(20)

    col_l, col_r = st.columns([2, 1])
    with col_l:
        section_header("🏢 Company", "")
        if data.get("company_name"):
            st.markdown(f"**{data['company_name']}**")
            st.caption(data.get("company_location") or "Location not set")
            if data.get("company_website"):
                st.caption(data["company_website"])
            if data.get("company_description"):
                st.write(data["company_description"])
        else:
            st.info("Fill the form below to create your company profile.")
    with col_r:
        section_header("👤 Recruiter", "")
        st.caption(data.get("recruiter_name") or st.session_state.user.get("name", ""))
        st.caption(data.get("recruiter_email") or st.session_state.user.get("email", ""))
        if data.get("designation"):
            st.caption(f"Role: {data['designation']}")
        if data.get("profile_photo_path") and os.path.isfile(data["profile_photo_path"]):
            st.image(data["profile_photo_path"], width=100)

    vertical_space(20)
    section_header("✏️ Edit Profile", "")
    with st.form("recruiter_form"):
        company_name_in = st.text_input("Company name", value=data.get("company_name") or "")
        company_website_in = st.text_input("Company website", value=data.get("company_website") or "", placeholder="https://company.com")
        company_description_in = st.text_area("Company description", value=data.get("company_description") or "")
        current_phone = st.session_state.user.get("phone") or ""
        codes = ["+91", "+1", "+44", "+61", "+81", "+49", "+33", "+86", "+971", "+65"]
        def_code = "+91"
        def_num = current_phone
        if " " in current_phone:
            parts = current_phone.split(" ", 1)
            if parts[0] in codes:
                def_code = parts[0]
                def_num = parts[1]

        col_p1, col_p2 = st.columns([1, 3])
        with col_p1:
            country_code = st.selectbox("Code", codes, index=codes.index(def_code) if def_code in codes else 0, key="rec_code")
        with col_p2:
            phone_num = st.text_input("Phone", value=def_num, placeholder="1234567890", key="rec_phone")
        phone = f"{country_code} {phone_num}" if phone_num else ""
        
        designation = st.text_input("Your role", value=data.get("designation") or "", placeholder="e.g. Talent Lead")
        about = st.text_area("About you", value=data.get("about") or "", placeholder="Brief intro about yourself")
        submitted = st.form_submit_button("Save", type="primary")
    if submitted:
        if phone:
            update_user_phone(uid, phone)
            st.session_state.user["phone"] = phone
        upsert_company_and_recruiter(uid, company_name=company_name_in or None, company_website=company_website_in or None, company_description=company_description_in or None, designation=designation or None, about=about or None)
        toast_success("Saved.")
        st.rerun()

    vertical_space(20)
    section_header("📸 Photo & Resume", "")
    data = get_recruiter_profile(uid) or {}

    # Upload photo (save-first pattern so photo shows immediately)
    photo = st.file_uploader("Upload photo (JPG/PNG, max 10 MB)", type=["jpg", "jpeg", "png"], key="recruiter_photo")
    if photo is not None:
        err = _validate_upload(photo, ["jpg", "jpeg", "png"])
        if err:
            toast_error(err)
        else:
            try:
                path = _unique_upload_path(uid, "recruiter_photos", photo.name)
                _save_upload(photo, path)
                upsert_company_and_recruiter(uid, profile_photo_path=path)
                st.session_state["_recruiter_photo_path"] = path
                st.session_state.pop("recruiter_photo", None)
                toast_success("✅ Photo saved.")
            except Exception as e:
                toast_error(f"Photo upload failed: {e}")

    # Display photo from cache or DB
    _rcached = st.session_state.get("_recruiter_photo_path")
    if _rcached and os.path.isfile(_rcached):
        rec_photo = _rcached
    else:
        data = get_recruiter_profile(uid) or {}
        rec_photo = data.get("profile_photo_path")
        if rec_photo:
            st.session_state["_recruiter_photo_path"] = rec_photo
    if rec_photo and os.path.isfile(rec_photo):
        st.image(rec_photo, width=120, caption="✅ Current photo")
    else:
        st.caption("No photo uploaded yet.")

    if data.get("resume_path") and os.path.isfile(data["resume_path"]):
        st.caption(f"Resume: {os.path.basename(data['resume_path'])}")
        with open(data["resume_path"], "rb") as f:
            st.download_button("⬇️ Download", f, file_name=os.path.basename(data["resume_path"]), use_container_width=True)
    rec_resume = st.file_uploader("Upload resume (PDF)", type=["pdf"], key="recruiter_resume")
    if rec_resume:
        err = _validate_upload(rec_resume, ["pdf"])
        if err:
            toast_error(err)
        else:
            path = _unique_upload_path(uid, "recruiter_resumes", rec_resume.name)
            _save_upload(rec_resume, path, clear_key="recruiter_resume")
            upsert_company_and_recruiter(uid, resume_path=path)
            toast_success("Resume saved.")
            st.rerun()



def _render_candidate_row(c, job_id, recruiter_id, is_applicant=True):
    app_status = get_application_status(c["user_id"], job_id)
    with st.container():
        ca, cb = st.columns([3, 1])
        with ca:
            score = c.get("score") or c.get("match_score")
            score_label = f"{score}% match" if score else "Match N/A"
            st.markdown(f"**{c['name']}** · {score_label} · {c.get('location') or '—'} · {c.get('experience_years') or '—'} yrs")
            if c.get("skills"):
                render_skill_cards([s.strip() for s in c["skills"].split(",") if s.strip()][:8])
        with cb:
            prob = predict_hire_probability(job_id, c["user_id"], score)
            fit = _ai_fit_label(score or 0, prob)
            st.caption(f"**{fit}**")
            
            # Check for pending review
            sessions = get_interview_sessions_for_candidate(c["user_id"], job_id)
            if sessions and sessions[0]["session"].get("recruiter_score") is None:
                st.warning("⚠️ Review Pending")
            
            if prob is not None:
                st.caption(f"Hire prob: {prob*100:.0f}%")

            sc_col, rj_col = st.columns(2)
            with sc_col:
                if st.button("✅ Shortlist", key=f"short_{job_id}_{c['user_id']}_{is_applicant}"):
                    set_application_status(c["user_id"], job_id, "shortlisted", recruiter_id)
                    st.rerun()
            with rj_col:
                if st.button("❌ Reject", key=f"rej_{job_id}_{c['user_id']}_{is_applicant}"):
                    set_application_status(c["user_id"], job_id, "rejected", recruiter_id)
                    st.rerun()

        with st.expander("👤 Full Profile · Resume · Interview · Contact"):
            full = get_candidate_full_profile(c["user_id"])
            if full:
                p = full["profile"]
                if p.get("visibility") is not None and int(p.get("visibility")) == 0:
                    st.warning("Profile hidden by candidate.")
                else:
                    st.markdown(f"**{p.get('name')}** · {p.get('email')}")
                    if p.get("user_phone") or p.get("phone"):
                        st.caption(f"📞 {p.get('user_phone') or p.get('phone')}")
                    st.markdown(f"*Skills:* {p.get('skills') or '—'}")
                    st.markdown(f"*Experience:* {p.get('experience_description') or '—'}")
                    st.markdown(f"*Education:* {p.get('education') or '—'}")

                    # Resume download
                    if p.get("resume_path") and os.path.isfile(p["resume_path"]):
                        with open(p["resume_path"], "rb") as f:
                            st.download_button("⬇️ Download Resume", f, file_name=os.path.basename(p["resume_path"]), key=f"dl_res_{c['user_id']}_{job_id}_{is_applicant}", use_container_width=True)

                    # Photo
                    if p.get("profile_photo_path") and os.path.isfile(p["profile_photo_path"]):
                        st.image(p["profile_photo_path"], width=100)

                    # Certificates
                    certs = full.get("certificates", [])
                    if certs:
                        st.markdown("**📜 Certificates:**")
                        for cert in certs:
                            verified = "✅" if cert.get("is_verified") else "❌"
                            st.caption(f"{cert.get('original_filename')} — {verified}")
                            if cert.get("file_path") and os.path.isfile(cert["file_path"]):
                                with open(cert["file_path"], "rb") as f:
                                    st.download_button(f"⬇️ {cert.get('original_filename')}", f, file_name=cert.get("original_filename", "cert"), key=f"dl_cert_{cert['id']}_{job_id}_{is_applicant}", use_container_width=True)

                    # Interview performance
                    sessions = get_interview_sessions_for_candidate(c["user_id"], job_id)
                    if sessions:
                        st.markdown("**🤖 AI Interview:**")
                        latest = sessions[0]["session"]
                        overall = float(latest.get("recruiter_score") or latest.get("overall_score") or 0)
                        technical = float(latest.get("technical_score") or overall)
                        aptitude = float(latest.get("communication_score") or overall)
                        
                        verified_tag = "✅ Recruiter Verified" if latest.get("recruiter_score") else "🤖 AI Evaluated"
                        st.caption(f"**{verified_tag}**")
                        st.caption(f"Overall {overall:.1f}/10 · Technical {technical:.1f}/10 · Aptitude {aptitude:.1f}/10 · Difficulty: {latest.get('difficulty', 'Intermediate')}")

                        # Recruiter Evaluation Section
                        vertical_space(10)
                        st.markdown("**📝 Interview Evaluation (Recruiter)**")
                        answers = sessions[0]["answers"]
                        total_recruiter_score = 0
                        with st.form(f"eval_form_{c['user_id']}_{job_id}"):
                            for i, ans in enumerate(answers):
                                st.markdown(f"**Q{i+1}: {ans['question_text']}**")
                                st.info(f"Answer: {ans['answer_text']}")
                                st.caption(f"AI Score: {ans['score']}/10 · Feedback: {ans['feedback']}")
                                
                                col_sc, col_rem = st.columns([1, 3])
                                with col_sc:
                                    r_score = st.number_input(f"Marks (1-10)", min_value=0.0, max_value=10.0, value=float(ans.get("recruiter_score") or ans["score"]), key=f"r_sc_{ans['question_order']}_{c['user_id']}")
                                with col_rem:
                                    r_rem = st.text_input(f"Remarks", value=ans.get("recruiter_remarks") or "", key=f"r_rem_{ans['question_order']}_{c['user_id']}")
                                
                                total_recruiter_score += r_score
                                # We'll need a way to save these individual scores. 
                                # For simplicity in this UI, we'll collect them and save on form submit.
                            
                            eval_feedback = st.text_area("Overall Feedback", value=latest.get("recruiter_feedback") or "")
                            submit_eval = st.form_submit_button("Submit Evaluation", type="primary")
                        
                        if submit_eval:
                            with get_connection() as conn:
                                cur = conn.cursor()
                                tech_m = []
                                apt_m = []
                                all_m = []
                                for ans in answers:
                                    # Retrieve values from session state using the keys defined in number_input/text_input
                                    m = st.session_state.get(f"r_sc_{ans['question_order']}_{c['user_id']}") or ans["score"]
                                    rem = st.session_state.get(f"r_rem_{ans['question_order']}_{c['user_id']}") or ""
                                    cur.execute("UPDATE interview_answers SET recruiter_score = ?, recruiter_remarks = ? WHERE session_id = ? AND question_order = ?", (m, rem, latest["id"], ans["question_order"]))
                                    
                                    all_m.append(float(m))
                                    if ans.get("question_type") == "technical":
                                        tech_m.append(float(m))
                                    else:
                                        apt_m.append(float(m))
                                
                                r_overall = sum(all_m) / len(all_m) if all_m else 0
                                r_technical = sum(tech_m) / len(tech_m) if tech_m else r_overall
                                r_aptitude = sum(apt_m) / len(apt_m) if apt_m else r_overall
                                
                                cur.execute("""
                                    UPDATE interview_sessions 
                                    SET recruiter_score = ?, 
                                        recruiter_feedback = ?,
                                        overall_score = ?,
                                        technical_score = ?,
                                        communication_score = ?
                                    WHERE id = ?
                                """, (r_overall, eval_feedback, r_overall, r_technical, r_aptitude, latest["id"]))
                                
                            toast_success("Candidate evaluation finalized.")
                            st.rerun()

                        if latest.get("recruiter_score") is not None:
                            st.success(f"Final Recruiter Score: **{latest['recruiter_score']:.1f}/10**")

                        if HAS_PLOTLY:
                            try:
                                sg = get_candidate_skill_gap(job_id, c["user_id"])
                                match_pct = float(sg.get("match_pct", 0))
                            except Exception:
                                match_pct = 0
                            cats = ["Skill Match", "Overall", "Technical", "Aptitude"]
                            vals = [min(100, match_pct), min(100, overall*10), min(100, technical*10), min(100, aptitude*10)]
                            fig = go.Figure(data=go.Scatterpolar(r=vals+[vals[0]], theta=cats+[cats[0]], fill="toself", name="Profile"))
                            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])), showlegend=False, margin=dict(l=0,r=0,t=20,b=10))
                            st.plotly_chart(fig, use_container_width=True)

                    # Email contact
                    candidate_email = p.get("email")
                    if candidate_email:
                        job_data = get_job_by_id(job_id)
                        recruiter_name = st.session_state.user.get("name", "")
                        company = job_data.get("company_name") if job_data else ""
                        role_title = job_data.get("title") if job_data else "an open role"
                        subject = f"Opportunity at {company or 'our company'}: {role_title}"
                        body = f"Hi {p.get('name') or 'there'},\r\n\r\nMy name is {recruiter_name} from {company or 'our team'}.\r\nWe reviewed your profile on JobBridge AI and would like to speak with you about {role_title}.\r\n\r\nPlease reply with available time slots for a call.\r\n\r\nBest regards,\r\n{recruiter_name}"
                        mailto = f"mailto:{quote(candidate_email)}?subject={quote(subject)}&body={quote(body)}"
                        st.link_button("📧 Contact via email", mailto, use_container_width=True)

            st.caption(f"Application status: **{app_status.upper() if app_status else 'PENDING'}**")
        st.markdown("---")


def render_recruiter_dashboard():
    uid = st.session_state.user["id"]
    page_header("Recruiter Dashboard", "Discover and contact top candidates.")
    vertical_space(20)

    rec = get_recruiter_profile(uid) or {}
    jobs_all = list_jobs_by_recruiter(uid, active_only=False)
    active_jobs = [j for j in jobs_all if int(j.get("is_active", 1) or 1) == 1]
    total_apps = 0
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM applications a JOIN jobs j ON j.id = a.job_id WHERE j.recruiter_id = ?", (uid,))
            row = cur.fetchone()
            total_apps = int(row["c"]) if row else 0
    except Exception:
        pass

    c1, c2, c3 = st.columns(3)
    with c1:
        render_stat_card(rec.get("company_name") or "Not set", "Company", "🏢")
    with c2:
        render_stat_card(str(len(active_jobs)), "Active Jobs", "📌")
    with c3:
        render_stat_card(str(total_apps), "Total Applicants", "📨")

    vertical_space(16)
    jobs = list_jobs_by_recruiter(uid)
    if not jobs:
        st.info("Post your first job from **➕ Post Job**.")
        return

    # Pre-selection logic
    selected_jid = st.session_state.get("selected_job_id")
    job_ids = [j["id"] for j in jobs]
    default_idx = 0
    if selected_jid and selected_jid in job_ids:
        default_idx = job_ids.index(selected_jid)

    job_id = st.selectbox("Select role", options=job_ids, index=default_idx, format_func=lambda x: next((j["title"] for j in jobs if j["id"] == x), str(x)))
    if not job_id:
        return

    vertical_space(16)

    section_header("📨 Applicants", "Only candidates who applied for this job.")
    applicants = get_applicants_for_job(job_id)
    if not applicants:
        st.caption("No applicants yet for this role.")
    else:
        for a in applicants:
            _render_candidate_row(a, job_id, uid, is_applicant=True)


# ---- Admin ----
def render_admin():
    page_header("Admin Dashboard", "Platform analytics.")
    vertical_space(20)
    stats = get_platform_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_stat_card(str(stats["users"]), "Users", "👥")
    with c2:
        render_stat_card(str(stats["job_seekers"]), "Job Seekers", "👤")
    with c3:
        render_stat_card(str(stats["recruiters"]), "Recruiters", "🏢")
    with c4:
        render_stat_card(str(stats["jobs"]), "Active Jobs", "💼")
    vertical_space(12)
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        render_stat_card(str(stats["profiles"]), "Profiles", "📝")
    with c6:
        render_stat_card(str(stats["interviews_completed"]), "Interviews", "🤖")
    with c7:
        render_stat_card(str(stats["certificates"]), "Certificates", "📜")
    with c8:
        render_stat_card(str(stats["applications"]), "Applications", "📄")
    vertical_space(24)
    section_header("📊 Interview Statistics", "")
    istats = get_interview_statistics()
    st.caption(f"Total: {istats['total_completed']} · Avg Overall: {istats['avg_overall_score']}/10 · Technical: {istats['avg_technical_score']}/10 · Communication: {istats['avg_communication_score']}/10")
    vertical_space(20)
    section_header("🔥 Skill Demand (Top 15)", "")
    for skill, count in get_skill_demand(15):
        st.caption(f"{skill.title()}: **{count}** jobs")
    vertical_space(20)
    section_header("👥 All Users", "")
    st.dataframe(get_all_users(), use_container_width=True)
    vertical_space(16)
    section_header("📋 All Jobs", "")
    st.dataframe(get_all_jobs(active_only=False), use_container_width=True)


# ---- Main ----
def main():
    if st.session_state.init_error:
        st.error("**Application could not start** — " + st.session_state.init_error)
        st.markdown("Check dependencies (`pip install -r requirements.txt`) and that the app has write access.")
        if st.button("Retry startup"):
            st.session_state.init_error = None
            st.rerun()
        return

    render_sidebar()
    st.markdown("<div class='main-block'>", unsafe_allow_html=True)
    page = st.session_state.active_page

    if page == "Login":
        render_login()
    elif page == "Register":
        render_register()
    elif st.session_state.user is None:
        st.info("Please log in.")
    else:
        try:
            role_db = st.session_state.user.get("role_db", "")
            if page == "Dashboard":
                render_dashboard()
            elif page == "Profile":
                render_profile()
            elif page == "Jobs":
                render_jobs()
            elif page == "My Applications":
                render_my_applications()
            elif page == "AI Interview":
                render_ai_interview()
            elif page == "Certificates":
                render_certificates()
            elif page == "Recruiter Dashboard":
                if not is_recruiter(role_db):
                    st.warning("Recruiter only.")
                else:
                    render_recruiter_dashboard()
            elif page == "Recruiter Profile":
                if not is_recruiter(role_db):
                    st.warning("Recruiter only.")
                else:
                    render_recruiter_profile()
            elif page == "Post Job":
                if not is_recruiter(role_db):
                    st.warning("Recruiter only.")
                else:
                    render_post_job()
            elif page == "My Jobs":
                if not is_recruiter(role_db):
                    st.warning("Recruiter only.")
                else:
                    render_my_jobs()
            elif page == "Admin Dashboard":
                if not is_admin(role_db):
                    st.warning("Admin only.")
                else:
                    render_admin()
            else:
                render_dashboard()
        except Exception as e:
            st.error(f"**Something went wrong:** {e}")
            st.caption("If this persists, try refreshing or contact support.")
            logger.exception("Page render failed: %s", page)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
