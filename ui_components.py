"""
JobBridge AI - Design system & UI components.
Meta-inspired SaaS design: Meta Blue (#1877F2), card layouts, progress bars, status badges.
"""

import streamlit as st

# —— Color system (Meta-inspired) ——
BG_PAGE = "#FFFFFF"
BG_CARD = "#FFFFFF"
BG_SECONDARY = "#F0F2F5"
BG_SIDEBAR = "#FFFFFF"
TEXT_HEADING = "#0A1F44"
TEXT_BODY = "#1B2A4E"
ACCENT = "#1877F2"            # Meta Blue — primary
ACCENT_2 = "#1565D8"          # Darker Meta Blue for hover
SUCCESS = "#42B72A"           # Meta Green — accent
WARNING = "#F5A623"
DANGER = "#DC3545"

# Legacy aliases
PRIMARY = ACCENT
PRIMARY_COLOR = ACCENT
ACCENT_COLOR = SUCCESS
BG_MAIN = BG_PAGE
TEXT_PRIMARY = TEXT_HEADING
TEXT_SECONDARY = TEXT_BODY

SPACE_SECTION = "28px"
SPACE_CARD_PADDING = "24px"


def inject_css():
    """Inject full Meta-inspired theme."""
    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            :root {{
                --jb-primary: {ACCENT};
                --jb-secondary: {ACCENT_2};
                --jb-bg: {BG_PAGE};
                --jb-card: {BG_CARD};
                --jb-sidebar: {BG_SIDEBAR};
                --jb-text: {TEXT_HEADING};
                --jb-muted: {TEXT_BODY};
                --jb-success: {SUCCESS};
                --jb-warning: {WARNING};
                --jb-danger: {DANGER};
                --jb-bg2: {BG_SECONDARY};
                --jb-focus: 0 0 0 4px rgba(24, 119, 242, 0.18);
            }}

            /* —— Force light mode —— */
            html {{ color-scheme: light !important; }}
            body {{
                background: {BG_PAGE} !important;
                color: {TEXT_BODY} !important;
            }}
            .stApp,
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"],
            section.main {{
                background: {BG_PAGE} !important;
                color: {TEXT_BODY} !important;
            }}
            header[data-testid="stHeader"] {{ background: transparent !important; }}
            [data-testid="stToolbar"] {{ background: transparent !important; }}

            /* —— Spacing —— */
            .main .block-container {{
                padding-top: 2rem;
                padding-bottom: 3rem;
                padding-left: 2rem;
                padding-right: 2rem;
                max-width: 100%;
            }}
            .stApp {{ background-color: {BG_PAGE} !important; }}
            html, body, [class*="css"] {{
                font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
                color: {TEXT_BODY} !important;
                background-color: {BG_PAGE} !important;
            }}
            .main-block {{
                padding: 0 0 3rem 0;
                background-color: {BG_PAGE} !important;
            }}

            /* —— Background accents —— */
            .stApp::before {{
                content: "";
                position: fixed;
                inset: 0;
                pointer-events: none;
                background:
                    radial-gradient(820px 420px at 82% 0%, rgba(24, 119, 242, 0.12), rgba(24, 119, 242, 0) 60%),
                    radial-gradient(780px 420px at 8% 14%, rgba(24, 119, 242, 0.10), rgba(24, 119, 242, 0) 55%);
                z-index: 0;
            }}
            section.main > div {{ position: relative; z-index: 1; }}

            /* —— Typography —— */
            .main-block .page-title {{
                font-size: 32px;
                font-weight: 700;
                color: {TEXT_HEADING};
                margin-bottom: 0.25rem;
                letter-spacing: -0.02em;
                line-height: 1.2;
            }}
            .main-block .page-subtitle {{
                font-size: 16px;
                font-weight: 500;
                color: {TEXT_BODY};
                margin-bottom: {SPACE_SECTION};
            }}
            .main-block .section-title {{
                font-size: 20px;
                font-weight: 600;
                color: {TEXT_HEADING};
                margin-top: 0;
                margin-bottom: 0.75rem;
            }}
            .main-block .section-subtitle {{
                font-size: 14px;
                font-weight: 500;
                color: {TEXT_BODY};
                margin-bottom: 1rem;
            }}
            .main-block h1 {{ font-size: 32px !important; font-weight: 700 !important; color: {TEXT_HEADING} !important; margin-bottom: 0.25rem !important; }}
            .main-block h2 {{ font-size: 20px !important; font-weight: 600 !important; color: {TEXT_HEADING} !important; margin-top: 1.5rem !important; margin-bottom: 0.5rem !important; }}
            .main-block h3 {{ font-size: 18px !important; font-weight: 600 !important; color: {TEXT_HEADING} !important; }}
            .main-block p, .stMarkdown p {{ font-size: 15px !important; font-weight: 500 !important; color: {TEXT_BODY} !important; line-height: 1.5 !important; }}
            .stMarkdown strong {{ color: {TEXT_HEADING} !important; }}

            /* —— Sidebar —— */
            section[data-testid="stSidebar"] {{
                min-width: 280px !important;
                width: 280px !important;
            }}
            section[data-testid="stSidebar"] > div {{
                background: linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(240,242,245,0.98) 100%);
                border-right: 1px solid rgba(15, 23, 42, 0.08);
                padding: 1.5rem 1rem 2rem 1rem;
                backdrop-filter: blur(10px);
            }}
            .sidebar-brand {{
                font-size: 1.35rem;
                font-weight: 700;
                color: {ACCENT};
                margin-bottom: 0.15rem;
                letter-spacing: -0.01em;
            }}
            .sidebar-tagline {{
                font-size: 0.8rem;
                color: {TEXT_BODY};
                margin-bottom: 1.5rem;
            }}
            section[data-testid="stSidebar"] [role="radiogroup"] {{
                gap: 0.25rem;
            }}
            section[data-testid="stSidebar"] [role="radiogroup"] label {{
                border-radius: 10px;
                padding: 0.6rem 0.85rem;
                font-weight: 600;
                font-size: 1.25rem !important;
                transition: background 0.2s ease, color 0.2s ease;
                color: {TEXT_HEADING};
            }}
            section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
                background: rgba(24, 119, 242, 0.08);
            }}
            section[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] {{
                background: {ACCENT} !important;
                color: #FFFFFF !important;
                box-shadow: 0 6px 18px rgba(24, 119, 242, 0.22);
            }}
            section[data-testid="stSidebar"] .stCaption {{ color: {TEXT_BODY}; font-size: 13px; }}
            section[data-testid="stSidebar"] hr {{ margin: 1rem 0; border-color: rgba(15, 23, 42, 0.08); }}

            /* —— Cards —— */
            .jb-card {{
                background: {BG_CARD};
                border-radius: 16px;
                padding: {SPACE_CARD_PADDING};
                box-shadow: 0 10px 30px rgba(28, 30, 33, 0.08), 0 1px 0 rgba(28, 30, 33, 0.04);
                border: 1px solid rgba(15, 23, 42, 0.08);
                margin-bottom: {SPACE_SECTION};
            }}
            .main [data-testid="column"] {{
                background: {BG_CARD};
                border-radius: 16px;
                padding: {SPACE_CARD_PADDING};
                box-shadow: 0 10px 30px rgba(28, 30, 33, 0.08), 0 1px 0 rgba(28, 30, 33, 0.04);
                border: 1px solid rgba(15, 23, 42, 0.08);
                margin-bottom: {SPACE_SECTION};
            }}

            /* —— Stat Card —— */
            .stat-card {{
                background: {BG_CARD};
                border-radius: 14px;
                padding: 20px;
                text-align: center;
                border: 1px solid rgba(15, 23, 42, 0.08);
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .stat-card .stat-value {{
                font-size: 2rem;
                font-weight: 700;
                color: {ACCENT};
                margin-bottom: 4px;
            }}
            .stat-card .stat-label {{
                font-size: 13px;
                font-weight: 600;
                color: {TEXT_BODY};
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }}

            /* —— Metrics —— */
            [data-testid="stMetricValue"] {{
                font-size: 1.5rem !important;
                font-weight: 700 !important;
                color: {ACCENT} !important;
            }}
            [data-testid="stMetricLabel"] {{
                font-size: 14px !important;
                font-weight: 500 !important;
                color: {TEXT_BODY} !important;
            }}

            /* —— Buttons —— */
            .stButton > button {{
                border-radius: 12px;
                font-weight: 600;
                font-size: 14px;
                padding: 0.55rem 1.1rem;
                transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
            }}
            .stButton > button[kind="primary"] {{
                background: {ACCENT} !important;
                color: #FFFFFF !important;
                border: none !important;
            }}
            .stButton > button[kind="primary"]:hover {{
                background: {ACCENT_2} !important;
                box-shadow: 0 10px 24px rgba(24, 119, 242, 0.28);
                transform: translateY(-1px);
            }}
            .stButton > button:not([kind="primary"]) {{
                background: {BG_CARD} !important;
                color: {TEXT_HEADING} !important;
                border: 1px solid rgba(15, 23, 42, 0.14) !important;
            }}
            .stButton > button:not([kind="primary"]):hover {{
                background: #F9FAFB !important;
                border-color: {ACCENT} !important;
                color: {ACCENT} !important;
            }}

            /* —— Inputs —— */
            .stTextInput > div > div > input, .stTextArea > div > div > textarea {{
                background: {BG_CARD} !important;
                border: 1px solid rgba(15, 23, 42, 0.14) !important;
                border-radius: 12px !important;
                color: {TEXT_HEADING} !important;
                font-size: 15px !important;
            }}
            .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {{
                border-color: {ACCENT} !important;
                box-shadow: var(--jb-focus) !important;
            }}
            .stTextInput label, .stTextArea label, .stSelectbox label, .stNumberInput label {{
                color: {TEXT_HEADING} !important;
                font-weight: 600 !important;
                font-size: 14px !important;
            }}
            .stSelectbox > div > div, .stMultiSelect > div > div {{
                background: {BG_CARD} !important;
                border-radius: 12px !important;
                border: 1px solid rgba(15, 23, 42, 0.14) !important;
            }}

            /* —— Expanders —— */
            .streamlit-expanderHeader {{
                background: {BG_CARD} !important;
                border-radius: 12px !important;
                border: 1px solid rgba(15, 23, 42, 0.12) !important;
            }}
            .streamlit-expanderContent {{
                background: {BG_CARD} !important;
                border: 1px solid rgba(15, 23, 42, 0.12) !important;
                border-top: none !important;
                border-radius: 0 0 12px 12px !important;
            }}

            /* —— Progress bars —— */
            .jb-progress-wrapper {{
                background: {BG_SECONDARY};
                border-radius: 999px;
                overflow: hidden;
                height: 10px;
            }}
            .jb-progress-inner {{
                height: 10px;
                border-radius: 999px;
                background: linear-gradient(90deg, {ACCENT}, {SUCCESS});
                transition: width 0.4s ease;
            }}

            /* —— Completion ring —— */
            .circular-progress {{
                width: 120px; height: 120px;
                border-radius: 50%;
                background: conic-gradient({ACCENT} var(--value), {BG_SECONDARY} 0);
                display: flex; align-items: center; justify-content: center;
                position: relative;
            }}
            .circular-progress::before {{
                content: "";
                position: absolute;
                width: 84px; height: 84px;
                background: {BG_CARD};
                border-radius: 50%;
            }}
            .circular-progress-value {{
                position: relative;
                font-size: 1.4rem;
                font-weight: 700;
                color: {ACCENT};
            }}

            /* —— Skill chips —— */
            .skill-chip {{
                display: inline-flex;
                padding: 0.25rem 0.65rem;
                border-radius: 999px;
                background: rgba(24, 119, 242, 0.10);
                color: {ACCENT};
                font-size: 0.8rem;
                font-weight: 600;
                margin: 2px 3px;
            }}

            /* —— Status badges —— */
            .status-badge {{
                display: inline-flex;
                padding: 0.2rem 0.6rem;
                border-radius: 999px;
                font-size: 0.75rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }}
            .status-applied {{ background: rgba(24, 119, 242, 0.12); color: {ACCENT}; }}
            .status-reviewed {{ background: rgba(245, 166, 35, 0.12); color: {WARNING}; }}
            .status-shortlisted {{ background: rgba(66, 183, 42, 0.12); color: {SUCCESS}; }}
            .status-rejected {{ background: rgba(220, 53, 69, 0.12); color: {DANGER}; }}

            /* —— Match badge —— */
            .match-badge {{
                padding: 0.25rem 0.6rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 600;
                background: rgba(66, 183, 42, 0.12);
                color: #166534;
            }}

            /* —— Chat bubbles —— */
            .chat-bubble {{
                max-width: 80%;
                padding: 0.9rem 1.1rem;
                border-radius: 12px;
                margin-bottom: 0.75rem;
                font-size: 15px;
                line-height: 1.55;
            }}
            .chat-bubble.user {{
                margin-left: auto;
                background: linear-gradient(135deg, {ACCENT} 0%, {ACCENT_2} 100%);
                color: #FFFFFF;
                border-bottom-right-radius: 4px;
            }}
            .chat-bubble.ai {{
                margin-right: auto;
                background: rgba(255, 255, 255, 0.75);
                color: {TEXT_HEADING};
                border: 1px solid rgba(15, 23, 42, 0.10);
                border-bottom-left-radius: 4px;
                backdrop-filter: blur(10px);
            }}

            /* —— DataFrames —— */
            [data-testid="stDataFrame"] {{
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid rgba(15, 23, 42, 0.10);
            }}

            /* —— Alerts —— */
            .stSuccess {{ background: rgba(66, 183, 42, 0.1); border: 1px solid rgba(66, 183, 42, 0.25); border-radius: 12px; color: #166534; }}
            .stError {{ background: rgba(220, 53, 69, 0.08); border: 1px solid rgba(220, 53, 69, 0.2); border-radius: 10px; color: #B91C1C; }}
            .stWarning {{ background: rgba(245, 166, 35, 0.1); border: 1px solid rgba(245, 166, 35, 0.25); border-radius: 10px; color: #B45309; }}
            .stInfo {{ background: rgba(24, 119, 242, 0.08); border: 1px solid rgba(24, 119, 242, 0.2); border-radius: 12px; color: {ACCENT}; }}

            hr {{ border-color: rgba(15, 23, 42, 0.10); margin: 1.5rem 0; }}

            /* —— Auth centered card —— */
            .jb-auth-marker {{ display: none; }}
            .jb-auth-marker ~ div div[data-testid="stForm"] {{
                max-width: 460px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(15, 23, 42, 0.10);
                border-radius: 18px;
                padding: 22px 22px 16px 22px;
                box-shadow: 0 18px 50px rgba(28, 30, 33, 0.14), 0 1px 0 rgba(28, 30, 33, 0.04);
                backdrop-filter: blur(12px);
            }}
            .jb-auth-marker ~ div div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button {{
                width: 100%;
            }}
            .jb-auth-hint {{
                font-size: 13px;
                color: {TEXT_BODY};
                margin-top: 8px;
                text-align: center;
            }}
            .jb-auth-kicker {{
                display: inline-flex;
                align-items: center;
                gap: 10px;
                padding: 10px 12px;
                border-radius: 14px;
                background: rgba(24, 119, 242, 0.08);
                border: 1px solid rgba(24, 119, 242, 0.12);
                color: {TEXT_HEADING};
                font-weight: 600;
                margin-bottom: 10px;
            }}

            /* —— New Auth Card targeting —— */
            .auth-card-marker {{ height: 0; margin: 0; padding: 0; }}
            .auth-card-marker + div [data-testid="stVerticalBlockBorder"] {{
                background: rgba(255, 255, 255, 0.95) !important;
                border: 1px solid rgba(15, 23, 42, 0.12) !important;
                border-radius: 20px !important;
                padding: 30px !important;
                box-shadow: 0 20px 60px rgba(28, 30, 33, 0.15), 0 1px 0 rgba(28, 30, 33, 0.05) !important;
                backdrop-filter: blur(14px);
                max-width: 480px;
                margin: 0 auto !important;
            }}
            .auth-card-marker + div [data-testid="stVerticalBlockBorder"] > div {{
                padding: 0 !important;
            }}

            /* —— Cross-validation flags —— */
            .cv-match {{ color: {SUCCESS}; font-weight: 600; }}
            .cv-mismatch {{ color: {DANGER}; font-weight: 600; }}
            .cv-info {{ color: {ACCENT}; font-weight: 500; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---- Component helpers ----

def page_header(title: str, subtitle: str = ""):
    sub = f'<p class="page-subtitle">{subtitle}</p>' if subtitle else ''
    st.markdown(f'<h1 class="page-title">{title}</h1>{sub}', unsafe_allow_html=True)


def section_header(title: str, subtitle: str = ""):
    sub = f'<p class="section-subtitle">{subtitle}</p>' if subtitle else ''
    st.markdown(f'<h2 class="section-title">{title}</h2>{sub}', unsafe_allow_html=True)


def vertical_space(px: int = 28):
    st.markdown(f'<div style="height:{px}px"></div>', unsafe_allow_html=True)


def render_profile_completion_bar(value: int):
    value = max(0, min(100, value))
    st.markdown(
        f'<div class="jb-progress-wrapper"><div class="jb-progress-inner" style="width: {value}%"></div></div>',
        unsafe_allow_html=True,
    )


def render_circular_progress(label: str, value: int):
    value = max(0, min(100, value))
    angle = int(3.6 * value)
    st.markdown(
        f"""
        <div style="display:flex;flex-direction:column;align-items:center;">
            <div class="circular-progress" style="--value:{angle}deg;">
                <div class="circular-progress-value">{value}%</div>
            </div>
            <div style="margin-top:0.5rem;font-size:14px;font-weight:500;color:{TEXT_BODY};">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stat_card(value: str, label: str, icon: str = ""):
    """Render a standalone stat card with value and label."""
    icon_html = f'<div style="font-size:1.5rem;margin-bottom:6px;">{icon}</div>' if icon else ''
    st.markdown(
        f"""<div class="stat-card">
            {icon_html}
            <div class="stat-value">{value}</div>
            <div class="stat-label">{label}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_skill_cards(skills: list, max_show: int = 20):
    """Render skill chips in a flow layout."""
    if not skills:
        st.caption("No skills extracted yet.")
        return
    chips_html = " ".join(f"<span class='skill-chip'>{s}</span>" for s in skills[:max_show])
    st.markdown(f'<div style="line-height:2.2;">{chips_html}</div>', unsafe_allow_html=True)
    if len(skills) > max_show:
        st.caption(f"+ {len(skills) - max_show} more")


def render_status_badge(status: str):
    """Render a colored status badge."""
    css_class = f"status-{status.lower()}" if status else "status-applied"
    label = status.replace("_", " ").title() if status else "Unknown"
    st.markdown(f'<span class="status-badge {css_class}">{label}</span>', unsafe_allow_html=True)


def render_cross_validation(flags: list):
    """Render cross-validation flags from resume parser."""
    for f in flags:
        css_class = f"cv-{f['status']}"
        icon = "✅" if f["status"] == "match" else ("⚠️" if f["status"] == "mismatch" else "ℹ️")
        st.markdown(f'<span class="{css_class}">{icon} {f["message"]}</span>', unsafe_allow_html=True)


def render_interview_question_card(question: str, category: str = "Technical Question"):
    """Render a premium Meta-style card for interview questions."""
    st.markdown(f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 2rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">
            <div style="color: #1877F2; font-size: 0.8rem; font-weight: 700; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em;">{category}</div>
            <div style="color: #0A1F44; font-size: 1.25rem; font-weight: 600; line-height: 1.6;">{question}</div>
        </div>
    """, unsafe_allow_html=True)


def toast_success(message: str):
    try:
        st.toast(message, icon="✅")
    except Exception:
        st.success(message)


def toast_error(message: str):
    try:
        st.toast(message, icon="❌")
    except Exception:
        st.error(message)
