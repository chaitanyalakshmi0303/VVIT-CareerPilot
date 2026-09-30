import os
import sys
import json
import re
import time
import uuid
import textwrap
import hashlib
import html as html_lib
import streamlit as st
import streamlit.components.v1 as components
import pypdf
import plotly.graph_objects as go
from company_db import (
    COMPANY_DATABASE,
    DSA_TOPIC_CURRICULUM,
    get_all_company_names,
    get_company_data,
    get_data_freshness_badge,
    filter_companies_by_intent,
    get_company_comparison_view_model
)
from language_config import (
    get_language_names,
    detect_script_language
)
from ai_service import check_ai_health
from interview_engine import (
    generate_conversational_response,
    get_user_memories,
    add_user_memory,
    clear_all_memories,
    save_conversation_session,
    get_user_conversation_sessions
)
from voice_agent_component import render_voice_agent_console
from assessment_engine import (
    CS_MCQ_BANK,
    SQL_QUESTION_BANK,
    ROLE_TECHNICAL_BANK,
    generate_multi_section_blueprint,
    select_smart_question,
    record_problem_status,
    select_next_dynamic_question,
    select_cs_questions,
    execute_code_tests,
    execute_sql_query,
    get_supported_languages
)
from auth_manager import (
    get_user_by_email,
    create_user,
    verify_password,
    get_github_auth_url,
    handle_oauth_callback
)

# ----------------- PAGE CONFIGURATION -----------------
st.set_page_config(
    page_title="VVIT CareerPilot | AI-Powered Placement & Career Preparation Platform",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def esc(value):
    return html_lib.escape("" if value is None else str(value))

SENSITIVE_FIELDS = {"password_hash", "salt"}

def safe_profile(record):
    return {k: v for k, v in (record or {}).items() if k not in SENSITIVE_FIELDS}

def parse_pct(value):
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else 0

_parse_pct = parse_pct

def compute_source_hash(code: str) -> str:
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()[:16]

# ----------------- STREAMLIT POLISH & RESPONSIVE CSS -----------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 2.5rem !important;
        z-index: 99 !important;
    }
    footer { visibility: hidden !important; }
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .block-container {
        max-width: 100% !important;
        padding-top: 0.5rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-bottom: 4rem !important;
        margin: auto;
    }
    
    .stApp {
        background: radial-gradient(circle at 10% 10%, #0d1527 0%, #030712 100%);
        color: #F8FAFC;
    }
    
    .top-nav {
        position: sticky;
        top: 0.5rem;
        z-index: 999;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: rgba(15, 23, 42, 0.88);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 0.75rem 1.4rem;
        margin-bottom: 1.2rem;
        backdrop-filter: blur(16px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    
    .nav-brand {
        font-size: 1.25rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .user-pill {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.12);
        padding: 0.35rem 0.85rem;
        border-radius: 30px;
        font-size: 0.84rem;
        color: #E2E8F0;
    }
    
    .glass-card {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.2rem;
        backdrop-filter: blur(8px);
        margin-bottom: 1rem;
    }
    
    .btn-github {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.65rem;
        width: 100%;
        padding: 0.7rem 1.2rem;
        margin-bottom: 0.8rem;
        border-radius: 8px;
        font-size: 0.95rem;
        font-weight: 600;
        text-decoration: none;
        transition: all 0.2s ease;
        border: 1px solid rgba(255, 255, 255, 0.18);
        background: #24292e;
        color: #FFFFFF !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }
    .btn-github:hover {
        background: #2f363d;
        border-color: #58a6ff;
        transform: translateY(-1px);
    }
    
    .task-box {
        background: rgba(30, 41, 59, 0.45);
        border-left: 3px solid #38BDF8;
        padding: 0.7rem 1rem;
        margin-bottom: 0.5rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.9rem;
    }
    
    @media (max-width: 900px) {
        .block-container {
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }
        .top-nav {
            flex-direction: column;
            gap: 0.5rem;
            align-items: flex-start;
        }
        .user-pill {
            font-size: 0.78rem;
        }
    }
    
    @media (max-width: 600px) {
        .nav-brand {
            font-size: 1.1rem;
        }
        .glass-card {
            padding: 0.9rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE MANAGEMENT -----------------
DEFAULT_DSA_TRACKER = {
    "Arrays & Hashing": {"status": "Practicing", "solved": 24, "accuracy": "82%", "weak": "Prefix Sum"},
    "Two Pointers & Sliding Window": {"status": "Practicing", "solved": 15, "accuracy": "75%", "weak": "Dynamic Window"},
    "Binary Search": {"status": "Learning", "solved": 8, "accuracy": "60%", "weak": "Binary Search on Monotonic Answer Range"},
    "Trees & Binary Search Trees": {"status": "Practicing", "solved": 18, "accuracy": "78%", "weak": "Lowest Common Ancestor (LCA)"},
    "Graphs": {"status": "Learning", "solved": 4, "accuracy": "45%", "weak": "Topological Sort (Kahn's)"},
    "Dynamic Programming": {"status": "Learning", "solved": 7, "accuracy": "50%", "weak": "2D Grid States"},
}

def init_session_state(force_reset=False):
    defaults = {
        "authenticated": False,
        "user_profile": None,
        "auth_mode": "signin",
        "pending_email": "",
        "audit_result": None,
        "oa_engine_state": None,
        "last_oa_scores": None,
        "selected_company": None,
        "selected_interaction_language": "Telugu",
        "company_watchlist": ["Amazon", "Google", "Microsoft"],
        "dsa_tracker": json.loads(json.dumps(DEFAULT_DSA_TRACKER))
    }
    for k, v in defaults.items():
        if force_reset or k not in st.session_state:
            st.session_state[k] = v

init_session_state()

if "ai_health" not in st.session_state:
    st.session_state.ai_health = check_ai_health()

# ----------------- OAUTH CALLBACK LISTENER -----------------
query_params = st.query_params

if "error" in query_params:
    err_type = query_params["error"]
    err_desc = query_params.get("error_description", "GitHub authorization was canceled or denied.")
    st.query_params.clear()
    st.error(f"Authentication Error ({err_type}): {err_desc}")

elif "code" in query_params and "state" in query_params:
    oauth_code = query_params["code"]
    oauth_state = query_params["state"]
    with st.spinner("Authorizing secure handshake with GitHub..."):
        user_cb, err = handle_oauth_callback(oauth_code, oauth_state)
        st.query_params.clear()
        if user_cb:
            st.session_state.authenticated = True
            st.session_state.user_profile = safe_profile(user_cb)
            st.toast(f"Welcome to VVIT CareerPilot, {user_cb.get('name', 'Candidate')}!", icon="👋")
            st.rerun()
        else:
            st.error(f"GitHub Authentication Failed: {err}")

# ----------------- AUTHENTICATION GATEWAY -----------------
if not st.session_state.authenticated:
    st.markdown("<br>", unsafe_allow_html=True)
    
    _, c_auth, _ = st.columns([1, 1.8 if st.session_state.auth_mode == "register" else 1.2, 1])
    with c_auth:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 1.5rem;">
            <div style="font-size: 2.4rem; margin-bottom: 0.3rem;">💼</div>
            <h2 style="margin: 0; font-weight: 800; color: #F8FAFC;">VVIT CareerPilot</h2>
            <p style="color: #94A3B8; font-size: 0.92rem; margin-top: 0.25rem;">
                AI-Powered Placement & Career Preparation Platform
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("⚡ Instant Workspace Login (Chaitanya - Amazon SDE)", type="primary", use_container_width=True):
            st.session_state.authenticated = True
            st.session_state.user_profile = {
                "name": "Chaitanya lakshmi dasari",
                "email": "chaitanya@placementprep.ai",
                "college": "KL University",
                "branch": "Computer Science & Engineering",
                "grad_year": "2026",
                "target_role": "SDE",
                "target_company": "Amazon",
                "auth_provider": "local_dev"
            }
            st.toast("Welcome back Chaitanya! Entering VVIT CareerPilot...", icon="👋")
            st.rerun()

        st.markdown("<div style='text-align: center; color: #64748B; margin: 0.8rem 0; font-size: 0.85rem;'>─────────── OR CONTINUE WITH ───────────</div>", unsafe_allow_html=True)

        github_url = get_github_auth_url()
        github_icon_svg = """<svg height="20" width="20" viewBox="0 0 16 16" fill="#FFFFFF" style="vertical-align: middle;"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>"""
        
        if github_url:
            st.markdown(
                f'<a href="{esc(github_url)}" target="_self" class="btn-github">{github_icon_svg} Continue with GitHub</a>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="btn-github" style="opacity: 0.6; cursor: not-allowed;">{github_icon_svg} GitHub OAuth (Set GITHUB_CLIENT_ID in .env)</div>',
                unsafe_allow_html=True
            )

        if st.session_state.auth_mode == "signin":
            st.markdown("<div style='font-size: 0.88rem; font-weight: 600; color: #E2E8F0; margin-bottom: 0.35rem;'>Email Address</div>", unsafe_allow_html=True)
            email_input = st.text_input("Email", value="", placeholder="name@college.edu", label_visibility="collapsed")

            if st.button("Continue with Email", use_container_width=True):
                email_clean = email_input.strip().lower()
                if not email_clean or "@" not in email_clean:
                    st.error("Please enter a valid email address.")
                else:
                    existing = get_user_by_email(email_clean)
                    st.session_state.pending_email = email_clean
                    st.session_state.auth_mode = "password" if existing else "register"
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            col_l, col_r = st.columns([1.6, 1])
            with col_l:
                st.caption("New to VVIT CareerPilot?")
            with col_r:
                if st.button("Create Account", key="btn_to_reg", use_container_width=True):
                    st.session_state.auth_mode = "register"
                    st.rerun()

        elif st.session_state.auth_mode == "password":
            st.markdown(f"**Enter Password** for `{st.session_state.pending_email}`")
            pw_input = st.text_input("Password", type="password", placeholder="Enter your password")

            c_back, c_sub = st.columns([1, 1.5])
            with c_back:
                if st.button("← Back", use_container_width=True):
                    st.session_state.auth_mode = "signin"
                    st.rerun()
            with c_sub:
                if st.button("Sign In", use_container_width=True, type="primary"):
                    user_record = get_user_by_email(st.session_state.pending_email)
                    if not user_record:
                        st.error("Account not found. Please register first.")
                    elif user_record.get("password_hash"):
                        if verify_password(pw_input, user_record["password_hash"], user_record["salt"]):
                            st.session_state.authenticated = True
                            st.session_state.user_profile = safe_profile(user_record)
                            st.rerun()
                        else:
                            st.error("Incorrect password. Please verify your credentials.")
                    else:
                        st.info(f"This account was created via GitHub OAuth. Please sign in with GitHub.")

        elif st.session_state.auth_mode == "register":
            st.markdown("#### Create Candidate Profile")
            with st.form("reg_form"):
                reg_name = st.text_input("Full Name", placeholder="e.g. Alex Morgan")
                reg_email = st.text_input("Email", value=st.session_state.pending_email, placeholder="name@college.edu")
                reg_college = st.text_input("College / University", placeholder="e.g. VVIT")

                rc1, rc2 = st.columns(2)
                with rc1:
                    reg_branch = st.text_input("Branch / Major", placeholder="e.g. Computer Science")
                with rc2:
                    reg_grad = st.selectbox("Graduation Year", ["2025", "2026", "2027", "2028"], index=1)

                reg_role = st.selectbox("Target Role Track", ["SDE", "AI/ML Engineer", "Data Scientist", "System Engineer"])
                reg_pw = st.text_input("Password", type="password", placeholder="Minimum 6 characters")

                submit_reg = st.form_submit_button("Complete Registration", use_container_width=True)
                if submit_reg:
                    reg_email_clean = reg_email.strip().lower()
                    if not reg_name.strip() or "@" not in reg_email_clean or len(reg_pw) < 6:
                        st.error("Please fill all required fields with a valid email (password minimum 6 characters).")
                    else:
                        new_user = create_user(
                            email=reg_email_clean,
                            name=reg_name.strip(),
                            password=reg_pw,
                            college=reg_college.strip(),
                            branch=reg_branch.strip(),
                            grad_year=reg_grad,
                            target_role=reg_role,
                            auth_provider="email"
                        )
                        if new_user:
                            st.session_state.authenticated = True
                            st.session_state.user_profile = safe_profile(new_user)
                            st.rerun()
                        else:
                            st.error("An account with this email already exists.")

            if st.button("← Back to Sign In", use_container_width=True):
                st.session_state.auth_mode = "signin"
                st.rerun()

    st.stop()

# ----------------- LOGGED-IN CONTEXT -----------------
user = st.session_state.user_profile or {}
user_email = user.get("email") or "candidate@vvitcareerpilot.ai"
company_keys = get_all_company_names()
target_company = (
    st.session_state.selected_company
    or (user.get("target_company") if user.get("target_company") in COMPANY_DATABASE else None)
    or (company_keys[0] if company_keys else "Amazon")
)
target_role_track = user.get("target_role") or "SDE"

# ----------------- AI AGENT CONVERSATIONAL LOOP -----------------
def fresh_chat(greeting=None):
    if not greeting:
        greeting = f"నమస్కారం {user.get('name', 'Candidate')}! నేను మీ VVIT CareerPilot AI ఇంటర్వ్యూయర్. {target_company} ({target_role_track}) ప్లేస్‌మెంట్ కోసం మీరు సిద్ధంగా ఉన్నారా? DSA, OS, DBMS, లేదా మాక్ ఇంటర్వ్యూతో ప్రారంభిద్దామా?"
    st.session_state.chat_messages = [{"role": "assistant", "content": greeting}]
    st.session_state.agent_dialogue_state = {"mode": "general", "round": 0}
    st.session_state.active_session_id = f"session_{uuid.uuid4().hex}"
    st.session_state.session_title = None

if "chat_messages" not in st.session_state:
    fresh_chat()

def build_agent_profile():
    parts = []
    tracker = st.session_state.get("dsa_tracker") or {}
    if tracker:
        weakest = sorted(tracker.items(), key=lambda kv: parse_pct(kv[1].get("accuracy", 0)))[:2]
        parts.append("Weakest DSA topics: " + "; ".join(
            f"{t} ({d.get('accuracy', '0%')} accuracy, focus: {d.get('weak', 'General')})" for t, d in weakest))
    audit = st.session_state.get("audit_result")
    if audit:
        parts.append(f"Resume ATS score {audit['ats']}/100 for {audit['company']}; missing keywords: "
                     + ", ".join(audit["missing"][:6]))
    oa_scores = st.session_state.get("last_oa_scores")
    if oa_scores:
        parts.append(f"Last OA: coding {oa_scores.get('coding', 0)}%, core CS {oa_scores.get('cs', 0)}%, "
                     f"SQL {oa_scores.get('sql', 0)}%, role technical {oa_scores.get('role', 0)}%")
    return {
        **user,
        "email": user_email,
        "target_company": target_company,
        "target_role": target_role_track,
        "progress_summary": " | ".join(parts)
    }

def run_agent_turn(prompt, lang="English"):
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return
        
    actual_lang = lang
    if lang == "Auto Detect":
        actual_lang = detect_script_language(clean_prompt)
        
    st.session_state.chat_messages.append({"role": "user", "content": clean_prompt})
    try:
        with st.spinner("Interviewer is thinking..."):
            reply = generate_conversational_response(
                user_message=clean_prompt,
                user_profile=build_agent_profile(),
                conversation_history=st.session_state.chat_messages,
                agent_state=st.session_state.agent_dialogue_state,
                language=actual_lang
            )
    except Exception as exc:
        st.session_state.chat_messages.pop()
        st.session_state.agent_error = f"{exc} (Message not sent; please try again.)"
        return

    st.session_state.chat_messages.append({"role": "assistant", "content": reply or "I could not generate a response. Please rephrase."})

    if not st.session_state.get("session_title"):
        st.session_state.session_title = clean_prompt[:30]
    try:
        save_conversation_session(
            session_id=st.session_state.active_session_id,
            user_email=user_email,
            title=st.session_state.session_title,
            messages=st.session_state.chat_messages
        )
    except Exception as exc:
        st.toast(f"Session sync failed: {exc}", icon="⚠️")

# Live Voice URL parameter listener
if "voice_input" in st.query_params:
    _voice_prompt = st.query_params["voice_input"]
    st.query_params.clear()
    if _voice_prompt and _voice_prompt.strip():
        run_agent_turn(_voice_prompt[:2000], lang=st.session_state.selected_interaction_language)
        st.rerun()

# ----------------- STICKY TOP NAVBAR -----------------
user_img_html = (
    f'<img src="{esc(user.get("profile_image"))}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;">'
    if user.get("profile_image") else '🎓'
)

st.markdown(f"""
<div class="top-nav">
    <div class="nav-brand">💼 VVIT CareerPilot <span style="font-size: 0.8rem; color: #94A3B8; font-weight: 500;">AI-Powered Placement & Career Preparation Platform</span></div>
    <div class="user-pill">
        {user_img_html} <b>{esc(user.get('name', 'Candidate'))}</b> &nbsp;|&nbsp; Target: <span style="color: #38BDF8; font-weight: 700;">{esc(target_company)} ({esc(target_role_track)})</span>
    </div>
</div>
""", unsafe_allow_html=True)

health = st.session_state.get("ai_health", {})
if health.get("status") in ("INVALID_API_KEY", "MODEL_NOT_FOUND"):
    st.warning(f"⚠️ **AI Configuration Alert ({health.get('status')}):** {health.get('message')}")

tabs = st.tabs([
    "🚀 Placement Auditor & Agent",
    "📊 Readiness Dashboard",
    "🎙️ AI Interview Simulator",
    "🧠 DSA Preparation Tracker",
    "🏢 Company Intelligence",
    "⚖️ Company Comparison Matrix",
    "👤 Candidate Profile"
])

# ----------------- TAB 1: PLACEMENT AUDITOR -----------------
TRACK_KEYWORDS = {
    "SDE": ["data structures", "algorithms", "java", "python", "c++", "sql", "git", "api", "oop",
            "operating system", "dbms", "system design", "docker", "aws", "spring", "react"],
    "AI/ML Engineer": ["machine learning", "deep learning", "pytorch", "tensorflow", "scikit-learn", "nlp",
                       "llm", "pandas", "numpy", "python", "mlops", "docker", "sql", "transformers"],
    "Data Scientist": ["statistics", "python", "pandas", "numpy", "sql", "machine learning", "visualization",
                       "tableau", "power bi", "regression", "hypothesis", "scikit-learn"],
    "System Engineer": ["linux", "networking", "shell", "bash", "sql", "java", "python", "cloud",
                        "monitoring", "troubleshooting", "git", "ci/cd", "docker"],
}
SECTION_HINTS = {
    "Education": ["education", "b.tech", "b.e", "bachelor", "university", "college"],
    "Projects": ["project"],
    "Experience": ["experience", "internship", "intern "],
    "Skills": ["skills", "technologies", "tech stack"],
}

def extract_resume_text(uploaded):
    try:
        reader = pypdf.PdfReader(uploaded)
        if reader.is_encrypted:
            reader.decrypt("")
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""

def score_resume(text, track):
    low = text.lower()
    keywords = TRACK_KEYWORDS.get(track, TRACK_KEYWORDS["SDE"])
    found = [k for k in keywords if k in low]
    missing = [k for k in keywords if k not in low]
    sections = {name: any(h in low for h in hints) for name, hints in SECTION_HINTS.items()}
    sections["Contact"] = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text))
    kw_cov = len(found) / len(keywords) if keywords else 0
    sec_cov = sum(sections.values()) / len(sections) if sections else 0
    return int(round((0.6 * kw_cov + 0.4 * sec_cov) * 100)), found, missing, sections

with tabs[0]:
    st.markdown("### 🚀 Autonomous Placement Auditor & Decision Pipeline")
    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        st.markdown("#### 📄 1. Candidate Resume")
        uploaded_file = st.file_uploader("Upload PDF Resume", type=["pdf"])
        if uploaded_file:
            st.caption(f"✓ File: `{uploaded_file.name}` ({round(uploaded_file.size / 1024, 1)} KB)")

    with c2:
        st.markdown("#### 🏢 2. Company & Role Selection")
        cat_filter = st.selectbox("Company Category", ["All", "Product", "Service", "Consulting", "E-commerce"], index=0)
        comps = company_keys if cat_filter == "All" else [c for c, d in COMPANY_DATABASE.items() if d.get("company_type") == cat_filter]
        comp_choice = role_choice = None
        if not comps:
            st.warning("No companies found matching this category filter.")
        else:
            comp_choice = st.selectbox("Select Target Company", comps)
            roles = list(COMPANY_DATABASE[comp_choice].get("roles", {}).keys())
            if roles:
                role_choice = st.selectbox("Select Target Role", roles)
            else:
                st.info("No explicit roles listed for this enterprise.")

            if st.session_state.selected_company != comp_choice:
                st.session_state.selected_company = comp_choice

    if st.button("⚡ Run Full Placement Audit & Launch Career Readiness Agent", use_container_width=True):
        if not uploaded_file:
            st.warning("Please upload your PDF resume first.")
        elif not comp_choice:
            st.warning("Please select a target company.")
        else:
            resume_text = extract_resume_text(uploaded_file)
            if len(resume_text) < 100:
                st.error("Insufficient text extracted from PDF (file may be image-only). Please upload a text-readable PDF.")
            else:
                ats, found, missing, sections = score_resume(resume_text, target_role_track)
                ai_feedback = None
                try:
                    with st.spinner("Placement AI is auditing resume against enterprise rubric..."):
                        audit_msg = (
                            f"Audit my resume for {comp_choice} - {role_choice or target_role_track}. "
                            "Give 5 concise, actionable bullet points and prioritize technical gaps.\n\n"
                            f"RESUME TEXT:\n{resume_text[:6000]}"
                        )
                        ai_feedback = generate_conversational_response(
                            user_message=audit_msg,
                            user_profile={**build_agent_profile(), "target_company": comp_choice},
                            conversation_history=[{"role": "user", "content": audit_msg}],
                            agent_state={"mode": "general", "round": 0}
                        )
                except Exception as exc:
                    ai_feedback = f"AI review unavailable: {exc}"

                st.session_state.audit_result = {
                    "company": comp_choice, "role": role_choice or target_role_track,
                    "ats": ats, "found": found, "missing": missing,
                    "sections": sections, "ai_feedback": ai_feedback,
                }

    audit = st.session_state.audit_result
    if audit:
        st.success(f"Audit completed for {audit['company']} ({audit['role']}).")
        a1, a2 = st.columns([1, 2])
        with a1:
            st.metric("Resume ATS Score", f"{audit['ats']}/100")
            for name, ok in audit["sections"].items():
                st.markdown(f"{'✅' if ok else '❌'} {name}")
        with a2:
            st.markdown("**Keywords found:** " + (", ".join(f"`{k}`" for k in audit["found"]) or "None identified"))
            st.markdown("**Missing critical keywords:** " + (", ".join(f"`{k}`" for k in audit["missing"]) or "None missing"))
            if audit.get("ai_feedback"):
                with st.expander("🤖 AI Placement Auditor Diagnostic", expanded=True):
                    st.markdown(audit["ai_feedback"])

# ----------------- TAB 2: READINESS DASHBOARD 2.0 (RESPONSIVE GRID) -----------------
with tabs[1]:
    from readiness_engine import (
        calculate_dsa_readiness,
        calculate_core_cs_readiness,
        calculate_aiml_readiness,
        calculate_overall_readiness,
        generate_dynamic_action_plan
    )

    st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem;">
        <div>
            <h2 style="margin: 0; color: #F8FAFC; font-weight: 800; font-size: 1.5rem;">📊 Placement Readiness Center</h2>
            <span style="color: #94A3B8; font-size: 0.86rem;">Multi-dimensional placement telemetry, gap diagnostics, and preparation roadmap.</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tb_c1, tb_c2, tb_c3 = st.columns([1.5, 1.5, 3])
    with tb_c1:
        comp_choices = get_all_company_names()
        cur_comp_idx = comp_choices.index(target_company) if target_company in comp_choices else 0
        active_target_company = st.selectbox("Benchmark Enterprise", comp_choices, index=cur_comp_idx, key="dashboard_comp_picker")
        if active_target_company != st.session_state.selected_company:
            st.session_state.selected_company = active_target_company
            target_company = active_target_company
    with tb_c2:
        roles_available = ["SDE", "AI/ML Engineer", "Data Scientist", "System Engineer"]
        cur_role_idx = roles_available.index(target_role_track) if target_role_track in roles_available else 0
        active_target_role = st.selectbox("Target Career Track", roles_available, index=cur_role_idx, key="dashboard_role_picker")
        if active_target_role != target_role_track:
            st.session_state.user_profile["target_role"] = active_target_role
            target_role_track = active_target_role
    with tb_c3:
        st.markdown(f"""
        <div style="padding-top: 1.6rem; font-size: 0.88rem; color: #CBD5E1;">
            Targeting: <b style="color: #38BDF8;">{esc(target_company)}</b> &nbsp;|&nbsp; Role: <b style="color: #818CF8;">{esc(target_role_track)}</b>
        </div>
        """, unsafe_allow_html=True)

    tracker = st.session_state.get("dsa_tracker", {})
    dsa_score, total_solved_count, dsa_telemetry = calculate_dsa_readiness(tracker, user_email=user_email)
    
    oa_scores = st.session_state.get("last_oa_scores") or {}
    core_cs_score = calculate_core_cs_readiness(oa_scores, tracker)
    sql_score = oa_scores.get("sql", 52)
    oa_score = oa_scores.get("coding", (70 if oa_scores else 40))
    
    chat_turns = len(st.session_state.get("chat_messages", []))
    interview_score = min(88, max(45, 45 + (chat_turns // 4) * 5))
    
    audit_data = st.session_state.get("audit_result")
    resume_score = audit_data.get("ats", 0) if audit_data else 0
    
    user_stack = user.get("primary_stack", "Java, Python, SQL, Operating Systems, DBMS")
    aiml_score, aiml_modules = calculate_aiml_readiness(target_role_track, user_stack)

    readiness_metrics = {
        "DSA": dsa_score,
        "Core CS": core_cs_score,
        "SQL": sql_score,
        "AI/ML": aiml_score,
        "Interview": interview_score,
        "OA": oa_score,
        "Resume": resume_score,
        "Role Skills": int(round((core_cs_score + dsa_score + sql_score) / 3))
    }

    overall_score, readiness_stage, stage_color = calculate_overall_readiness(readiness_metrics)

    st.markdown("<hr style='margin: 0.4rem 0 0.8rem 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    
    kpi_grid_html = f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 1rem;">
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid {stage_color}; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">OVERALL</span>
            <h3 style="margin: 0.2rem 0; color: {stage_color}; font-size: 1.35rem;">{overall_score}%</h3>
            <span style="font-size: 0.65rem; color: #34D399;">Active Prepared</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #38BDF8; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">DSA</span>
            <h3 style="margin: 0.2rem 0; color: #38BDF8; font-size: 1.35rem;">{dsa_score}%</h3>
            <span style="font-size: 0.65rem; color: #CBD5E1;">{total_solved_count} solved</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #818CF8; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">CORE CS</span>
            <h3 style="margin: 0.2rem 0; color: #818CF8; font-size: 1.35rem;">{core_cs_score}%</h3>
            <span style="font-size: 0.65rem; color: #CBD5E1;">OS/DBMS/CN</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #A855F7; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">AI / ML</span>
            <h3 style="margin: 0.2rem 0; color: #A855F7; font-size: 1.35rem;">{aiml_score}%</h3>
            <span style="font-size: 0.65rem; color: #CBD5E1;">ML & Math</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #F59E0B; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">OA SCORE</span>
            <h3 style="margin: 0.2rem 0; color: #F59E0B; font-size: 1.35rem;">{oa_score}%</h3>
            <span style="font-size: 0.65rem; color: #CBD5E1;">Timed Runs</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #EC4899; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">INTERVIEW</span>
            <h3 style="margin: 0.2rem 0; color: #EC4899; font-size: 1.35rem;">{interview_score}%</h3>
            <span style="font-size: 0.65rem; color: #CBD5E1;">AI Simulator</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #10B981; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">RESUME</span>
            <h3 style="margin: 0.2rem 0; color: #10B981; font-size: 1.35rem;">{f'{resume_score}%' if resume_score > 0 else 'Audit'}</h3>
            <span style="font-size: 0.65rem; color: #CBD5E1;">ATS Rating</span>
        </div>
        <div class="glass-card" style="padding: 0.7rem 0.5rem; text-align: center; border-top: 3px solid #EF4444; margin: 0;">
            <span style="font-size: 0.7rem; color: #94A3B8; font-weight: 700;">STREAK</span>
            <h3 style="margin: 0.2rem 0; color: #EF4444; font-size: 1.35rem;">7 Days</h3>
            <span style="font-size: 0.65rem; color: #EF4444;">🔥 Active</span>
        </div>
    </div>
    """
    st.markdown(kpi_grid_html, unsafe_allow_html=True)

    c_radar, c_breakdown = st.columns([1.2, 1.2], gap="large")
    with c_radar:
        chart_keys = ["DSA", "Core CS", "SQL", "AI/ML", "Role Skills", "OA", "Interview", "Resume"]
        chart_vals = [readiness_metrics[k] for k in chart_keys]
        r_plot = chart_vals + [chart_vals[0]]
        theta_plot = chart_keys + [chart_keys[0]]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=r_plot,
            theta=theta_plot,
            fill='toself',
            fillcolor='rgba(56, 189, 248, 0.20)',
            line=dict(color='#38BDF8', width=2),
            marker=dict(size=5, color='#818CF8')
        ))
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], gridcolor='rgba(255,255,255,0.1)', tickfont=dict(size=9, color="#64748B")),
                angularaxis=dict(gridcolor='rgba(255,255,255,0.08)', tickfont=dict(size=11, color="#CBD5E1"))
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            height=330,
            margin=dict(l=35, r=35, t=20, b=25),
            showlegend=False
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with c_breakdown:
        st.markdown("<h4 style='margin: 0 0 0.6rem 0; color: #F8FAFC;'>Readiness Dimension Breakdown</h4>", unsafe_allow_html=True)
        for dim_name in chart_keys:
            val = readiness_metrics[dim_name]
            b_color = "#34D399" if val >= 70 else ("#38BDF8" if val >= 50 else "#F59E0B")
            st.markdown(f"""
            <div style="margin-bottom: 0.45rem;">
                <div style="display: flex; justify-content: space-between; font-size: 0.83rem; margin-bottom: 0.15rem;">
                    <span style="color: #CBD5E1; font-weight: 600;">{esc(dim_name)}</span>
                    <span style="color: {b_color}; font-weight: 700;">{val}%</span>
                </div>
                <div style="background: rgba(255,255,255,0.07); border-radius: 4px; height: 6px; overflow: hidden;">
                    <div style="background: {b_color}; width: {val}%; height: 100%;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<hr style='margin: 1.2rem 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    c_gap, c_plan = st.columns([1, 1.2], gap="large")

    with c_gap:
        st.markdown(f"#### 🎯 Skill Gap Analysis: `{target_company}` ({target_role_track})")
        comp_info = get_company_data(target_company) or {}
        role_profile = comp_info.get("roles", {}).get(target_role_track, comp_info.get("roles", {}).get("SDE", {}))
        
        mandatory = role_profile.get("mandatory_skills", ["Java", "DSA", "DBMS", "Operating Systems", "SQL"])
        preferred = role_profile.get("preferred_skills", ["System Design", "Microservices", "REST APIs"])

        user_stack_lower = user_stack.lower()
        matched_m = [s for s in mandatory if s.lower() in user_stack_lower]
        missing_m = [s for s in mandatory if s.lower() not in user_stack_lower]

        st.markdown(f"""
        <div class="glass-card" style="padding: 1.1rem; margin-bottom: 0.8rem;">
            <b style="color: #38BDF8; font-size: 0.9rem;">Verified Mandatory Competencies ({len(matched_m)}/{len(mandatory)} Acquired):</b>
            <div style="margin-top: 0.4rem; font-size: 0.84rem; line-height: 1.8;">
                {' '.join(f'<span style="background: rgba(52, 211, 153, 0.15); color: #34D399; padding: 2px 8px; border-radius: 4px; margin-right: 4px;">✓ {esc(m)}</span>' for m in matched_m)}
                {' '.join(f'<span style="background: rgba(239, 68, 68, 0.15); color: #EF4444; padding: 2px 8px; border-radius: 4px; margin-right: 4px;">✗ {esc(m)}</span>' for m in missing_m)}
            </div>
            <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 0.7rem 0;">
            <b style="color: #818CF8; font-size: 0.9rem;">High-Yield Architecture Skills to Target:</b>
            <div style="margin-top: 0.3rem; font-size: 0.84rem; color: #CBD5E1;">
                {', '.join(f'<code>{esc(p)}</code>' for p in preferred)}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c_plan:
        st.markdown("#### ⚡ Today's Dynamic Placement Action Plan")
        action_plan = generate_dynamic_action_plan(dsa_telemetry, readiness_metrics, target_company, target_role_track)

        for idx, item in enumerate(action_plan, 1):
            st.markdown(f"""
            <div class="task-box" style="margin-bottom: 0.5rem; padding: 0.65rem 0.9rem;">
                <div style="display: flex; justify-content: space-between; font-size: 0.76rem;">
                    <b style="color: #38BDF8;">{item['category']}</b>
                    <span style="color: #94A3B8;">⏱️ {item['time']}</span>
                </div>
                <div style="font-size: 0.85rem; color: #E2E8F0; margin-top: 0.2rem;">
                    {item['task']}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ----------------- TAB 3: AI INTERVIEW SIMULATOR & OA CHAMBER -----------------
def finish_oa(oa):
    oa["completed"] = True
    oa["active"] = False
    pct = lambda a, b: int(round(100 * a / b)) if b else 0
    st.session_state.last_oa_scores = {
        "cs": pct(oa["cs_score"], oa["total_cs"]),
        "sql": pct(oa["sql_solved"], oa["total_sql"]),
        "role": pct(sum(oa["role_answers"].values()), max(len(oa["role_answers"]), 1)) if oa["role_answers"] else 0,
        "coding": pct(oa["dsa_solved"], oa["total_dsa"]),
    }

def render_oa_timer(oa):
    if not oa.get("start_time"):
        return
    elapsed = int(time.time() - oa["start_time"])
    remaining = max(0, oa["duration_mins"] * 60 - elapsed)
    m, s = divmod(remaining, 60)
    st.markdown(f"⏱ **Time Left:** `{m:02d}:{s:02d}`")
    if remaining == 0 and oa["active"]:
        finish_oa(oa)
        st.rerun()

try:
    render_oa_timer = st.fragment(run_every=1)(render_oa_timer)
except Exception:
    pass

with tabs[2]:
    st.markdown("### 🎙️️ AI Live Interview Simulator & Assessment Chamber")
    st.caption("Turn-by-turn conversational interviewer with persistent memory, and a locked Online Assessment (OA) coding chamber.")

    mode_switch = st.radio("Chamber Mode Selection:", ["🎙️ Conversational Technical Interview", "📝 Timed Online Assessment (OA) Simulation"], horizontal=True)

    # ================= SUB-MODE A: FULL CONVERSATIONAL AGENT =================
    if mode_switch == "🎙️ Conversational Technical Interview":
        st.markdown("""
        <div class="glass-card" style="border-left: 4px solid #38BDF8; margin-bottom: 1rem;">
            <h3 style="margin: 0; color: #38BDF8; font-size: 1.35rem;">🎙️ VVIT CareerPilot AI Conversational Interviewer</h3>
            <span style="font-size: 0.85rem; color: #94A3B8;">Real-Time Voice & Text Placement Preparation Companion • Memory-Aware & Adaptive</span>
        </div>
        """, unsafe_allow_html=True)

        col_chat, col_sidebar = st.columns([2.2, 1], gap="medium")

        with col_sidebar:
            st.markdown("#### 🌐 Interaction Language")
            all_langs = get_language_names()
            cur_lang_idx = all_langs.index(st.session_state.selected_interaction_language) if st.session_state.selected_interaction_language in all_langs else 0
            
            selected_lang = st.selectbox(
                "Preferred Communication Language",
                all_langs,
                index=cur_lang_idx,
                key="chat_lang_picker"
            )
            if selected_lang != st.session_state.selected_interaction_language:
                st.session_state.selected_interaction_language = selected_lang

            st.markdown("#### 🧠 Agent Placement Memory")
            st.caption("Information the AI retains across your sessions.")

            memories = get_user_memories(user_email)
            if memories:
                for mem in memories[:4]:
                    st.markdown(f"""
                    <div style="background: rgba(30, 41, 59, 0.45); border-left: 3px solid #818CF8; padding: 0.45rem 0.75rem; border-radius: 4px; margin-bottom: 0.4rem; font-size: 0.8rem;">
                        <b style="color: #818CF8;">{esc(mem.get('category'))}:</b> {esc(mem.get('content'))}<br>
                        <span style="font-size: 0.72rem; color: #64748B;">{esc(mem.get('created_at'))}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No long-term memories saved yet. State: *'I struggle with graph topological sort'* to evaluate memory retention.")

            with st.expander("⚙️ Manage Memories"):
                new_mem_text = st.text_input("Add Custom Memory", placeholder="e.g. Strong in Trees, weak in Graphs", key="custom_mem_in")
                if st.button("Save to Memory", use_container_width=True):
                    if new_mem_text.strip():
                        add_user_memory(user_email, "Candidate Preference", new_mem_text.strip())
                        st.rerun()
                    else:
                        st.warning("Input required before saving.")
                if memories and st.button("🗑️ Clear All Memories", use_container_width=True):
                    clear_all_memories(user_email)
                    st.rerun()

            st.markdown("---")
            st.markdown("#### 🗂 Recent Sessions")
            if st.button("➕ New Conversation", use_container_width=True):
                fresh_chat()
                st.rerun()

            for sess in (get_user_conversation_sessions(user_email) or [])[:3]:
                title = str(sess.get("title") or "Untitled Session")
                label = f"💬 {title[:25]}{'...' if len(title) > 25 else ''}"
                if st.button(label, key=f"sess_{sess['session_id']}", use_container_width=True):
                    st.session_state.active_session_id = sess["session_id"]
                    st.session_state.chat_messages = sess["messages"]
                    st.session_state.session_title = title
                    st.session_state.agent_dialogue_state = {"mode": "general", "round": 0}
                    st.rerun()

        with col_chat:
            st.markdown("<div style='font-size: 0.82rem; color: #94A3B8; margin-bottom: 0.3rem;'>⚡ Quick Conversational Actions:</div>", unsafe_allow_html=True)
            qa1, qa2, qa3, qa4, qa5 = st.columns(5)

            user_quick_input = None
            with qa1:
                if st.button("🎤 Start Interview", use_container_width=True):
                    user_quick_input = f"Start a mock interview for {target_company} {target_role_track}."
            with qa2:
                if st.button("💻 Practice DSA", use_container_width=True):
                    user_quick_input = "Give me a medium DSA problem on Binary Search without giving away the solution."
            with qa3:
                if st.button("🤖 AIML Discussion", use_container_width=True):
                    user_quick_input = "Explain overfitting and how to mitigate it in production ML."
            with qa4:
                if st.button("📚 CS Core", use_container_width=True):
                    user_quick_input = "What is the difference between a process and a thread in OS?"
            with qa5:
                if st.button("📋 Study Plan", use_container_width=True):
                    user_quick_input = "What should I study today based on my weak topics and target role?"

            _agent_err = st.session_state.pop("agent_error", None)
            if _agent_err:
                st.error(_agent_err)

            chat_container = st.container()
            with chat_container:
                for msg in st.session_state.chat_messages:
                    if msg["role"] == "user":
                        st.chat_message("user").markdown(msg["content"])
                    else:
                        st.chat_message("assistant", avatar="🎙️").markdown(msg["content"])

            last_msg = st.session_state.chat_messages[-1] if st.session_state.chat_messages else None
            latest_assistant_text = last_msg["content"] if last_msg and last_msg["role"] == "assistant" else ""
            
            render_voice_agent_console(
                latest_reply_text=latest_assistant_text,
                selected_language=st.session_state.selected_interaction_language,
                autoplay=True
            )

            prompt = st.chat_input("Ask about DSA, AIML, CS Core, or say 'interview me'...") or user_quick_input
            if prompt:
                run_agent_turn(prompt, lang=st.session_state.selected_interaction_language)
                st.rerun()

    # ================= SUB-MODE B: TIMED ONLINE ASSESSMENT CHAMBER =================
    else:
        st.markdown("""
        <div class="glass-card" style="border-left: 4px solid #818CF8;">
            <h4 style="margin: 0; color: #818CF8;">📝 Verified Online Assessment (OA) Simulation Center</h4>
            <span style="font-size: 0.85rem; color: #94A3B8;">Multi-section corporate assessment chamber. Balance across Coding, Core CS Fundamentals (OS, CN, DBMS, OOP), Interactive SQL, and Role-Specific Technical tracks.</span>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.oa_engine_state is None:
            st.session_state.oa_engine_state = {
                "active": False, "completed": False,
                "company": target_company, "role": target_role_track,
                "start_time": None, "duration_mins": 60,
                "seen_ids": set(), "solved_ids": set(), "current_q": None,
                "dsa_solved": 0, "total_dsa": 1,
                "cs_score": 0, "total_cs": 2, "cs_answers": {}, "cs_questions": [],
                "sql_solved": 0, "total_sql": 1,
                "role_answers": {},
                "last_result": None,
            }

        oa = st.session_state.oa_engine_state
        ROLE_TRACKS = ["SDE", "AI/ML Engineer", "Data Scientist", "System Design"]

        if not oa["active"] and not oa["completed"]:
            col_cfg1, col_cfg2 = st.columns(2)
            with col_cfg1:
                comp_idx = company_keys.index(target_company) if target_company in company_keys else 0
                target_comp_oa = st.selectbox("Target Enterprise Assessment", company_keys, index=comp_idx, key="oa_comp_sel")
            with col_cfg2:
                role_idx = ROLE_TRACKS.index(target_role_track) if target_role_track in ROLE_TRACKS else 0
                target_role_oa = st.selectbox("Target Role Track", ROLE_TRACKS, index=role_idx, key="oa_role_sel")

            bp = generate_multi_section_blueprint(target_comp_oa, target_role_oa)
            st.markdown(f"""
            <div class="glass-card">
                <b>Verified Assessment Blueprint:</b> {esc(target_comp_oa)} ({esc(target_role_oa)})<br>
                • Coding Section: <b>{bp['dsa_count']} Problem(s) (Clean Boilerplate Only)</b><br>
                • CS Fundamentals: <b>{bp['cs_mcq_count']} Questions (OS, CN, DBMS, OOP)</b><br>
                • Relational Database: <b>{bp['sql_count']} Interactive SQL Task(s)</b><br>
                • Total Assessment Window: <b>{bp['duration_mins']} Minutes</b>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🚀 Enter Multi-Section Assessment Chamber", use_container_width=True):
                oa.update({
                    "active": True, "company": target_comp_oa, "role": target_role_oa,
                    "start_time": time.time(), "duration_mins": bp["duration_mins"],
                    "total_dsa": bp["dsa_count"], "total_cs": bp["cs_mcq_count"], "total_sql": bp["sql_count"],
                    "last_result": None,
                })
                oa["current_q"] = select_smart_question(user_email, company=target_comp_oa)
                if oa["current_q"]:
                    oa["seen_ids"].add(oa["current_q"]["id"])
                oa["cs_questions"] = select_cs_questions(bp["cs_mcq_count"])
                oa["total_cs"] = len(oa["cs_questions"])
                st.rerun()

        elif oa["active"] and not oa["completed"]:
            if time.time() - oa["start_time"] >= oa["duration_mins"] * 60:
                finish_oa(oa)
                st.rerun()

            t1, t2, t3 = st.columns([1.5, 1.5, 1])
            with t1:
                st.markdown(f"**Enterprise:** `{oa['company']}` ({oa['role']})")
            with t2:
                st.markdown(f"📊 **Progress:** Coding: `{oa['dsa_solved']}/{oa['total_dsa']}` | CS: `{oa['cs_score']}/{oa['total_cs']}` | SQL: `{oa['sql_solved']}/{oa['total_sql']}`")
            with t3:
                render_oa_timer(oa)

            st.markdown("<hr style='margin: 0.5rem 0 1rem 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)

            oa_sec_tabs = st.tabs([
                "💻 Technical Coding",
                "🧠 CS Fundamentals (OS/CN/DBMS/OOP)",
                "🗄️ Relational SQL Sandbox",
                "🎯 Role-Specific Technical"
            ])

            # ---------------- CODING SECTION ----------------
            with oa_sec_tabs[0]:
                curr_q = oa.get("current_q")
                if not curr_q:
                    st.info("No coding question available.")
                else:
                    p_left, p_right = st.columns([1, 1.4], gap="medium")

                    with p_left:
                        examples_html = "".join(
                            f"<div style='background: rgba(0,0,0,0.25); padding: 0.5rem 0.7rem; border-radius: 6px; margin-bottom: 0.4rem; font-size: 0.82rem;'>"
                            f"<b>Input:</b> <code>{esc(ex.get('input'))}</code><br><b>Output:</b> <code>{esc(ex.get('output'))}</code><br>"
                            f"<span style='color: #64748B;'>{esc(ex.get('explanation', ''))}</span></div>"
                            for ex in curr_q.get("examples", [])
                        )
                        st.markdown(f"""
                        <div class="glass-card" style="min-height: 580px; padding: 1.2rem;">
                            <div style="font-size: 0.8rem; color: #38BDF8; font-weight: 700; text-transform: uppercase;">
                                {esc(curr_q.get('topic'))} • {esc(curr_q.get('difficulty'))}
                            </div>
                            <h3 style="margin: 0.3rem 0; font-size: 1.3rem;">{esc(curr_q.get('title'))}</h3>
                            <span style="font-size: 0.78rem; color: #94A3B8;">📌 Pattern: <i>{esc(curr_q.get('pattern', 'Algorithmic Search'))}</i></span>
                            <hr style="border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;">
                            <p style="font-size: 0.92rem; line-height: 1.6; color: #E2E8F0;">{esc(curr_q.get('description')).replace(chr(10), '<br>')}</p>
                            <h5 style="margin-top: 1rem; color: #CBD5E1;">Constraints</h5>
                            <pre style="background: rgba(0,0,0,0.3); padding: 0.6rem; border-radius: 6px; font-size: 0.82rem; color: #94A3B8;">{esc(curr_q.get('constraints'))}</pre>
                            <h5 style="margin-top: 0.8rem; color: #CBD5E1;">Examples</h5>
                            {examples_html}
                        </div>
                        """, unsafe_allow_html=True)

                    with p_right:
                        col_lang, col_reset = st.columns([2, 1])
                        with col_lang:
                            lang_selected = st.selectbox(
                                "Programming Language", get_supported_languages(),
                                key=f"lang_{curr_q['id']}"
                            )
                        with col_reset:
                            st.write("")
                            st.write("")
                            if st.button("↺ Reset to Starter Code", use_container_width=True):
                                starter = curr_q["starter_templates"].get(lang_selected, "// Write solution\n")
                                st.session_state[f"active_code_{curr_q['id']}_{lang_selected}"] = starter
                                oa["last_result"] = None
                                st.rerun()

                        starter_code = curr_q["starter_templates"].get(lang_selected, "// Write solution\n")
                        state_code_key = f"active_code_{curr_q['id']}_{lang_selected}"
                        if state_code_key not in st.session_state:
                            st.session_state[state_code_key] = starter_code

                        current_active_code = st.text_area(
                            label=f"Solution Editor ({lang_selected})",
                            value=st.session_state[state_code_key],
                            height=380,
                            key=f"editor_{curr_q['id']}_{lang_selected}"
                        )

                        if current_active_code != st.session_state[state_code_key]:
                            st.session_state[state_code_key] = current_active_code
                            if oa.get("last_result"):
                                oa["last_result"]["is_stale"] = True

                        btn_c1, btn_c2, btn_c3 = st.columns(3)
                        with btn_c1:
                            if st.button("▶️ Run Code", use_container_width=True):
                                cur_hash = compute_source_hash(current_active_code)
                                res = execute_code_tests(
                                    lang_selected,
                                    current_active_code,
                                    curr_q,
                                    run_hidden=False
                                )
                                oa["last_result"] = {
                                    "kind": "run",
                                    "qid": curr_q["id"],
                                    "res": res,
                                    "source_hash": cur_hash,
                                    "is_stale": False
                                }
                                st.rerun()

                        with btn_c2:
                            if st.button("🚀 Submit", use_container_width=True, type="primary"):
                                cur_hash = compute_source_hash(current_active_code)
                                sub_res = execute_code_tests(
                                    lang_selected,
                                    current_active_code,
                                    curr_q,
                                    run_hidden=True
                                )
                                oa["last_result"] = {
                                    "kind": "submit",
                                    "qid": curr_q["id"],
                                    "res": sub_res,
                                    "source_hash": cur_hash,
                                    "is_stale": False
                                }
                                if sub_res.get("passed"):
                                    record_problem_status(user_email, curr_q["id"], "SOLVED", company=oa['company'], topic=curr_q.get('topic'))
                                    oa["solved_ids"].add(curr_q["id"])
                                    oa["dsa_solved"] = len(oa["solved_ids"])
                                    if oa["dsa_solved"] < oa["total_dsa"]:
                                        next_q = select_smart_question(user_email, company=oa['company'], topic=curr_q.get('topic'))
                                        if next_q and next_q["id"] not in oa["seen_ids"]:
                                            oa["seen_ids"].add(next_q["id"])
                                            oa["current_q"] = next_q
                                            oa["last_result"] = None
                                            st.toast(f"✅ Accepted! Passed all {sub_res['total_count']} test cases.", icon="🎉")
                                            st.rerun()
                                st.rerun()

                        with btn_c3:
                            if st.button("⏭️ Skip", use_container_width=True):
                                record_problem_status(user_email, curr_q["id"], "SKIPPED", company=oa['company'], topic=curr_q.get('topic'))
                                next_q = select_smart_question(user_email, company=oa['company'])
                                if next_q:
                                    oa["seen_ids"].add(next_q["id"])
                                    oa["current_q"] = next_q
                                    oa["last_result"] = None
                                    st.rerun()
                                else:
                                    st.info("No further practice questions available.")

                        # DIAGNOSTIC TEST CONSOLE
                        lr = oa.get("last_result")
                        if lr and lr["qid"] == curr_q["id"]:
                            r = lr["res"]
                            is_submit = (lr["kind"] == "submit")
                            status = r.get("status", "Failed")
                            passed_cnt = r.get("passed_count", 0)
                            total_cnt = r.get("total_count", 0)

                            if lr.get("is_stale"):
                                st.warning("⚠ **Code Modified**: Editor was updated after last run. Click **Run Code** to evaluate.")

                            if status == "No Code Submitted":
                                st.error(f"⚠ **No Code Submitted**: {r.get('error')}")
                            elif r.get("passed"):
                                st.success(f"✓ **All Test Cases Passed!** ({passed_cnt}/{total_cnt} passed) • Runtime: {r.get('runtime_ms', 1)} ms")
                            elif status == "Compilation Error":
                                st.error("⚠ **Compilation Error** — Code failed to build.")
                            elif status == "Runtime Error":
                                st.error(f"⚠ **Runtime Error** ({passed_cnt}/{total_cnt} test cases passed)")
                            elif status == "Time Limit Exceeded":
                                st.error(f"⏱ **Time Limit Exceeded** — Execution took longer than 4.0s.")
                            elif status == "Judge Error":
                                st.warning(f"⚙️ **Judge Environment Notice:** {r.get('error')}")
                            else:
                                st.error(f"✗ **Wrong Answer** ({passed_cnt}/{total_cnt} test cases passed)")

                            if r.get("error") and status not in ("No Code Submitted", "Judge Error"):
                                st.code(str(r["error"]), language="text")

                            for cr in r.get("case_results", []):
                                if not cr.get("is_hidden"):
                                    c_idx = cr.get("case_idx", 1)
                                    if cr.get("passed"):
                                        st.markdown(f"""
                                        <div style="background: rgba(52, 211, 153, 0.1); border-left: 3px solid #34D399; padding: 0.4rem 0.8rem; border-radius: 4px; margin-bottom: 0.4rem; font-size: 0.82rem;">
                                            <b style="color: #34D399;">✓ Case {c_idx} Passed</b> &nbsp;|&nbsp; 
                                            Input: <code>{esc(cr.get('input'))}</code> &nbsp;|&nbsp; 
                                            Expected: <code>{esc(cr.get('expected'))}</code> &nbsp;|&nbsp; 
                                            Got: <code>{esc(cr.get('actual'))}</code>
                                        </div>
                                        """, unsafe_allow_html=True)
                                    else:
                                        err_txt = f" (Error: {esc(cr.get('error'))})" if cr.get('error') else ""
                                        err_info = f"<br><span style='color: #FCA5A5;'>{esc(cr.get('error'))}</span>" if cr.get('error') else ""
                                        actual_val = cr.get('actual')
                                        actual_display = "None / Error" if actual_val is None else str(actual_val)
                                        st.markdown(f"""
                                        <div style="background: rgba(239, 68, 68, 0.1); border-left: 3px solid #EF4444; padding: 0.4rem 0.8rem; border-radius: 4px; margin-bottom: 0.4rem; font-size: 0.82rem;">
                                            <b style="color: #EF4444;">✗ Case {c_idx} Failed{err_txt}</b><br>
                                            Input: <code>{esc(cr.get('input'))}</code><br>
                                            Expected: <code>{esc(cr.get('expected'))}</code> &nbsp;|&nbsp; 
                                            Got: <code style="color: #F87171;">{esc(actual_display)}</code>{err_info}
                                        </div>
                                        """, unsafe_allow_html=True)

            # ---------------- CS FUNDAMENTALS SECTION ----------------
            with oa_sec_tabs[1]:
                st.markdown("#### Core CS Screening Component")
                for idx, mcq in enumerate(oa["cs_questions"]):
                    st.markdown(f"**Question {idx + 1} ({mcq['category']}):** {mcq['question']}")
                    opt = st.radio(f"Select Answer for Q{idx + 1}:", mcq["options"], index=None, key=f"cs_mcq_{mcq['id']}")
                    if st.button(f"Save Answer Q{idx + 1}", key=f"btn_cs_{mcq['id']}"):
                        if opt is None:
                            st.warning("Please select an option before saving.")
                        else:
                            oa["cs_answers"][mcq["id"]] = (opt == mcq["answer"])
                            oa["cs_score"] = sum(oa["cs_answers"].values())
                            if opt == mcq["answer"]:
                                st.success("✓ Answer recorded.")
                            else:
                                st.error("Answer recorded. Incorrect.")
                    if mcq["id"] in oa["cs_answers"]:
                        st.caption("Saved ✔")

            # ---------------- SQL SANDBOX SECTION ----------------
            with oa_sec_tabs[2]:
                sql_q = SQL_QUESTION_BANK[0]
                st.markdown(f"#### SQL Engineering Task: {sql_q['title']} (`{sql_q['difficulty']}`)")
                st.markdown(f"**Target Schema:** ` {sql_q['schema']} `")
                st.markdown(f"**Task Description:** {sql_q['description']}")
                user_sql = st.text_area("Write SQL Query:", height=120, placeholder="SELECT ... FROM ...", key="sql_oa_editor")
                if st.button("Run & Validate SQL Query", use_container_width=True):
                    sql_res = execute_sql_query(user_sql, sql_q, run_hidden=True)
                    if sql_res["passed"]:
                        oa["sql_solved"] = min(1, oa["total_sql"])
                        st.success(f"✅ Accepted. Passed {sql_res['passed_count']}/{sql_res['total_count']} datasets.")
                        with st.expander("Reference solution"):
                            st.code(sql_q["solution"], language="sql")
                    else:
                        st.error(f"❌ {sql_res['status']}. Passed {sql_res['passed_count']}/{sql_res['total_count']} datasets.")
                        if sql_res.get("error"):
                            st.code(str(sql_res["error"]))
                        for cr in sql_res.get("case_results", []):
                            if not cr.get("passed") and not cr.get("is_hidden") and cr.get("expected"):
                                st.caption(f"Dataset {cr['case_idx']}: expected {cr['expected']}, got {cr.get('actual')}")

            # ---------------- ROLE TECHNICAL SECTION ----------------
            with oa_sec_tabs[3]:
                if oa["role"] in ("AI/ML Engineer", "Data Scientist"):
                    track_name = oa["role"]
                else:
                    track_name = "System Design"
                role_qs = ROLE_TECHNICAL_BANK.get(track_name, ROLE_TECHNICAL_BANK.get("System Design", []))
                st.markdown(f"#### Role-Specific Evaluation: `{track_name}`")
                for r_idx, rq in enumerate(role_qs):
                    st.markdown(f"**Topic: {rq['topic']}**")
                    st.markdown(rq["question"])
                    r_opt = st.radio("Select Response:", rq["options"], index=None, key=f"role_q_{rq['id']}")
                    if st.button(f"Submit Technical Response {r_idx + 1}", key=f"btn_role_{rq['id']}"):
                        if r_opt is None:
                            st.warning("Please choose an answer before submitting.")
                        else:
                            oa["role_answers"][rq["id"]] = (r_opt == rq["answer"])
                            if r_opt == rq["answer"]:
                                st.success("✓ Conceptually correct answer verified.")
                            else:
                                st.error(f"Incorrect. {rq['explanation']}")

            st.markdown("---")
            if st.button("🏁 Conclude Full Assessment & Generate Official Report", use_container_width=True):
                finish_oa(oa)
                st.rerun()

        elif oa["completed"]:
            st.success("🎉 Multi-Section Assessment Concluded! Here is your Comprehensive Performance Diagnostic.")
            rc1, rc2, rc3, rc4 = st.columns(4)
            with rc1:
                st.metric("Coding Tasks", f"{oa['dsa_solved']}/{oa['total_dsa']}")
            with rc2:
                st.metric("Core CS", f"{oa['cs_score']}/{oa['total_cs']}")
            with rc3:
                st.metric("SQL Engineering", f"{oa['sql_solved']}/{oa['total_sql']}")
            with rc4:
                st.metric("Role Technical", f"{sum(oa['role_answers'].values())}/{len(oa['role_answers'])}")
            if st.button("Start Fresh Multi-Section Session"):
                st.session_state.oa_engine_state = None
                for k in list(st.session_state.keys()):
                    if str(k).startswith(("cs_mcq_", "role_q_", "lang_", "active_code_", "sql_oa_editor")):
                        del st.session_state[k]
                st.rerun()

# ----------------- TAB 4: DSA PREPARATION TRACKER -----------------
with tabs[3]:
    st.markdown("### 🧠 Pattern-Based DSA Preparation Tracker")
    st.caption("Avoid arbitrary problem solving. Focus on company-verified patterns and identified weak areas.")

    dt1, dt2 = st.columns([1, 1], gap="medium")
    with dt1:
        st.markdown("#### Topic Mastery & Accuracy Matrix")
        for topic, d in st.session_state.dsa_tracker.items():
            scolor = "#34D399" if d["status"] == "Practicing" else "#FBBF24" if d["status"] == "Learning" else "#94A3B8"
            st.markdown(f"""
            <div class="glass-card" style="padding: 0.8rem 1.1rem; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <b>{esc(topic)}</b><br>
                    <span style="font-size: 0.8rem; color: #94A3B8;">Solved: {esc(d['solved'])} | Accuracy: {esc(d['accuracy'])} | Focus: <i>{esc(d['weak'])}</i></span>
                </div>
                <span style="background: rgba(255,255,255,0.06); padding: 0.3rem 0.7rem; border-radius: 6px; color: {scolor}; font-size: 0.85rem; font-weight: 600;">
                    {esc(d['status'])}
                </span>
            </div>
            """, unsafe_allow_html=True)

        with st.expander("✏️ Update my progress"):
            with st.form("dsa_update_form"):
                upd_topic = st.selectbox("Topic", list(st.session_state.dsa_tracker.keys()))
                upd_status = st.selectbox("Status", ["Not Started", "Learning", "Practicing"])
                upd_solved = st.number_input("Problems solved", min_value=0, step=1)
                upd_acc = st.slider("Accuracy (%)", 0, 100, 50)
                upd_weak = st.text_input("Weak sub-topic (optional)")
                if st.form_submit_button("Save progress"):
                    entry = st.session_state.dsa_tracker[upd_topic]
                    entry.update({"status": upd_status, "solved": int(upd_solved), "accuracy": f"{upd_acc}%"})
                    if upd_weak.strip():
                        entry["weak"] = upd_weak.strip()
                    st.rerun()

    with dt2:
        curriculum_topics = list(DSA_TOPIC_CURRICULUM.keys())
        if curriculum_topics:
            default_idx = curriculum_topics.index("Binary Search") if "Binary Search" in curriculum_topics else 0
            cur_topic = st.selectbox("Curated Pattern Progression", curriculum_topics, index=default_idx)
            curr_p = DSA_TOPIC_CURRICULUM.get(cur_topic, {})
            problems = curr_p.get("recommended_problems", [])
            if not problems:
                st.info("No recommended problems for this topic yet.")
            for p in problems:
                st.markdown(f"""
                <div class="glass-card" style="padding: 0.8rem; margin-bottom: 0.5rem;">
                    <div style="display: flex; justify-content: space-between;">
                        <b>{esc(p.get('title'))}</b>
                        <span style="color: #38BDF8; font-size: 0.8rem;">{esc(p.get('difficulty'))}</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #94A3B8; margin-top: 0.2rem;">
                        Pattern: <code>{esc(p.get('pattern'))}</code> • Importance: <i>{esc(p.get('importance'))}</i>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No curriculum data available.")

# ----------------- TAB 5: COMPANY INTELLIGENCE (140+ ENTERPRISES) -----------------
with tabs[4]:
    st.markdown("### 🏢 Enterprise Hiring Intelligence & Placement Tracker")
    st.caption("Verified recruitment pipelines, live opportunities, recurring hiring windows, and syllabus requirements.")

    all_names = get_all_company_names()
    total_tracked = len(all_names)
    prod_count = sum(1 for c in COMPANY_DATABASE.values() if c.get("primary_category") == "Product")
    serv_count = sum(1 for c in COMPANY_DATABASE.values() if c.get("primary_category") in ("Service", "Consulting"))
    startup_count = sum(1 for c in COMPANY_DATABASE.values() if c.get("primary_category") in ("Startup", "E-Commerce", "FinTech"))
    semi_count = sum(1 for c in COMPANY_DATABASE.values() if c.get("primary_category") == "Semiconductor")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        st.metric("Total Enterprises", f"{total_tracked}")
    with m2:
        st.metric("Product Hubs", f"{prod_count}")
    with m3:
        st.metric("Service / Consulting", f"{serv_count}")
    with m4:
        st.metric("Startups & FinTech", f"{startup_count}")
    with m5:
        st.metric("Core Tech & Silicon", f"{semi_count}")
    with m6:
        st.metric("My Watchlist", f"{len(st.session_state.company_watchlist)}")

    st.markdown("<hr style='margin: 0.8rem 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)

    s_col1, s_col2, s_col3, s_col4 = st.columns([2.2, 1.2, 1.2, 1.2])
    with s_col1:
        search_query = st.text_input(
            "🔍 Smart Search",
            placeholder="Search by company, role (e.g. AI/ML, SDE), tech stack (Java, Python, CUDA), or city..."
        )
    with s_col2:
        categories_available = ["All", "Product", "Service", "Consulting", "Startup", "FinTech", "E-Commerce", "Semiconductor", "Banking Tech"]
        selected_cat = st.selectbox("Category", categories_available, index=0)
    with s_col3:
        selected_role = st.selectbox("Target Role", ["All", "SDE", "AI/ML Engineer"], index=0)
    with s_col4:
        selected_city = st.selectbox("Engineering Hub", ["All", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Delhi NCR", "Noida", "Mumbai"], index=0)

    filtered_company_list = filter_companies_by_intent(
        query=search_query,
        category=selected_cat,
        role_filter=selected_role,
        location_filter=selected_city
    )

    v_mode = st.radio("Directory Display Mode:", ["🏢 Selected Enterprise Profile", "📋 Interactive Company Directory Cards"], horizontal=True)

    if v_mode == "🏢 Selected Enterprise Profile":
        if not filtered_company_list:
            st.warning("No enterprises match your active filter criteria. Try adjusting the category or search keywords.")
        else:
            default_index = 0
            if target_company in filtered_company_list:
                default_index = filtered_company_list.index(target_company)

            ci_comp = st.selectbox(f"Select Company Profile ({len(filtered_company_list)} Available)", filtered_company_list, index=default_index)
            c_info = get_company_data(ci_comp)

            freshness_badge = get_data_freshness_badge(c_info.get("last_verified", "2026-09-30"))
            is_watched = ci_comp in st.session_state.company_watchlist

            st.markdown(f"""
            <div class="glass-card" style="border-left: 4px solid #38BDF8; margin-top: 0.6rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin: 0; color: #38BDF8; font-size: 1.6rem;">{esc(c_info.get('name'))}</h2>
                    <span style="font-size: 0.85rem; font-weight: 700; padding: 4px 12px; border-radius: 20px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.3); color: #38BDF8;">
                        {esc(c_info.get('hiring_status'))}
                    </span>
                </div>
                <p style="margin: 0.4rem 0; color: #94A3B8; font-size: 0.9rem;">
                    <b>Primary Category:</b> {esc(c_info.get('primary_category'))} &nbsp;|&nbsp; 
                    <b>Tags:</b> {', '.join(esc(t) for t in c_info.get('secondary_categories', []))} &nbsp;|&nbsp; 
                    <b>HQ:</b> {esc(c_info.get('headquarters'))}
                </p>
                <p style="margin: 0.2rem 0; color: #E2E8F0; font-size: 0.88rem;">
                    📍 <b>Major India Tech Hubs:</b> {esc(c_info.get('india_presence'))}
                </p>
                <div style="margin-top: 0.6rem; font-size: 0.8rem; color: #64748B;">
                    📅 <i>{esc(freshness_badge)}</i> &nbsp;•&nbsp; Verification Source: <u>{esc(c_info.get('verification_source'))}</u>
                </div>
            </div>
            """, unsafe_allow_html=True)

            w_col1, w_col2 = st.columns([1.2, 3])
            with w_col1:
                if is_watched:
                    if st.button("⭐ In Watchlist (Remove)", key=f"btn_w_{ci_comp}", use_container_width=True):
                        st.session_state.company_watchlist.remove(ci_comp)
                        st.rerun()
                else:
                    if st.button("☆ Add to Placement Watchlist", key=f"btn_w_{ci_comp}", use_container_width=True):
                        st.session_state.company_watchlist.append(ci_comp)
                        st.toast(f"{ci_comp} added to your placement watchlist!", icon="⭐")
                        st.rerun()
            with w_col2:
                st.caption(f"🔔 In-app hiring updates configured for **{ci_comp}**. When verified off-campus links are detected, alerts will surface on your dashboard.")

            p_sub1, p_sub2, p_sub3, p_sub4, p_sub5, p_sub6 = st.tabs([
                "💼 Verified Openings",
                "🎓 Internships & Freshers",
                "📅 Seasonal Calendar",
                "🧠 Role & Skill Match",
                "🎯 OA & Interview Stages",
                "🔗 Verified Career Portals"
            ])

            with p_sub1:
                st.markdown("#### 💼 Active & Upcoming Recruitment Openings")
                st.info(f"**Live Status:** {c_info.get('hiring_status')} — {c_info.get('hiring_status_details')}")

                fresher_jobs = c_info.get("fresher_jobs", [])
                if fresher_jobs:
                    for f in fresher_jobs:
                        st.markdown(f"""
                        <div class="glass-card" style="padding: 1rem; margin-bottom: 0.6rem;">
                            <div style="display: flex; justify-content: space-between;">
                                <b>{esc(f['role'])}</b>
                                <span style="color: #34D399; font-weight: 700;">{esc(f['status'])}</span>
                            </div>
                            <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 0.3rem;">
                                <b>Eligibility:</b> {esc(f['eligibility'])}<br>
                                <b>Batch:</b> {esc(f['grad_year'])} &nbsp;|&nbsp; <b>Experience:</b> {esc(f['experience'])} &nbsp;|&nbsp; <b>Location:</b> {esc(f['location'])}<br>
                                <span style="font-size: 0.78rem; color: #64748B;">Verified on {esc(f['verified_date'])} via {esc(f['source_type'])}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("No standalone off-campus fresher postings detected today. Check university placement cells or student internship pathways.")

            with p_sub2:
                st.markdown("#### 🎓 Student Internships & Graduate Pipelines")
                intern_jobs = c_info.get("internships", [])
                if intern_jobs:
                    for i in intern_jobs:
                        st.markdown(f"""
                        <div class="glass-card" style="padding: 1rem; margin-bottom: 0.6rem; border-left: 3px solid #818CF8;">
                            <div style="display: flex; justify-content: space-between;">
                                <b>{esc(i['role'])}</b>
                                <span style="color: #38BDF8; font-weight: 600;">{esc(i['status'])}</span>
                            </div>
                            <div style="font-size: 0.85rem; color: #E2E8F0; margin-top: 0.3rem;">
                                <b>Eligibility:</b> {esc(i['eligibility'])}<br>
                                <b>Target Batch:</b> {esc(i['grad_year'])} &nbsp;|&nbsp; <b>Duration:</b> {esc(i['duration'])}<br>
                                <b>Stipend:</b> <span style="color: #34D399;">{esc(i['stipend'])}</span> &nbsp;|&nbsp; <b>Location:</b> {esc(i['location'])}<br>
                                <b>Application Window:</b> {esc(i['deadline'])}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("Dedicated student internship portal openings are unlisted at this moment.")

            with p_sub3:
                st.markdown("#### 📅 Seasonal Recruitment Calendar (India Hubs)")
                st.caption("Highlights historical recurring campus & off-campus hiring cycles.")
                cal = c_info.get("seasonal_calendar", {})
                months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                cal_cols = st.columns(3)
                for idx, m in enumerate(months):
                    events = cal.get(m, ["Standard lateral & off-campus pipelines"])
                    with cal_cols[idx % 3]:
                        st.markdown(f"""
                        <div class="task-box" style="margin-bottom: 0.6rem; min-height: 85px;">
                            <b style="color: #38BDF8;">{m}</b><br>
                            <span style="font-size: 0.8rem; color: #CBD5E1;">
                                {'<br>'.join(f'• {esc(ev)}' for ev in events)}
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

            with p_sub4:
                st.markdown("#### 🧠 Role Skill Matcher & Syllabus Requirements")
                roles_dict = c_info.get("roles", {})
                sel_role = st.selectbox("Select Role Profile", list(roles_dict.keys()), key="psub_role_select")
                role_spec = roles_dict[sel_role]

                user_stack = (user.get("primary_stack") or "Java, Python, C++, SQL, Operating Systems, DBMS").lower()
                mandatory = role_spec.get("mandatory_skills", [])
                preferred = role_spec.get("preferred_skills", [])
                matched = [s for s in mandatory if s.lower() in user_stack]
                missing = [s for s in mandatory if s.lower() not in user_stack]

                sm1, sm2 = st.columns(2)
                with sm1:
                    st.markdown(f"**Mandatory Technical Skills ({len(matched)}/{len(mandatory)} Matched):**")
                    for m in mandatory:
                        st.markdown(f"{'✅' if m in matched else '❌'} `{m}`")
                with sm2:
                    st.markdown("**Preferred & Architectural Skills:**")
                    for p in preferred:
                        st.markdown(f"⭐ `{p}`")
                    if missing:
                        st.markdown("**Actionable Learning Gaps:**")
                        st.warning(", ".join(f"`{x}`" for x in missing))

            with p_sub5:
                st.markdown("#### 🎯 Verified Assessment & Interview Stages")
                stages = role_spec.get("interview_stages", [])
                for s_idx, stg in enumerate(stages, 1):
                    st.markdown(f"""
                    <div class="glass-card" style="padding: 0.8rem 1.1rem; margin-bottom: 0.5rem;">
                        <div style="display: flex; justify-content: space-between;">
                            <b>Round {s_idx}: {esc(stg.get('round'))}</b>
                            <span style="font-size: 0.78rem; color: #818CF8;">{esc(stg.get('type'))}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: #CBD5E1; margin-top: 0.3rem;">
                            {esc(stg.get('focus'))}
                        </div>
                        <div style="font-size: 0.75rem; color: #64748B; margin-top: 0.2rem;">
                            Source: <i>{esc(stg.get('source'))}</i>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            with p_sub6:
                st.markdown("#### 🔗 Verified Official Portals (No Third-Party Links)")
                p_main = c_info.get("official_career_url")
                p_int = c_info.get("internship_url")
                p_grad = c_info.get("graduate_url")

                st.markdown(f"- 🌐 **Official Careers Portal:** [{esc(p_main)}]({esc(p_main)})")
                if p_int and p_int != p_main:
                    st.markdown(f"- 🎓 **Student & Internship Opportunities:** [{esc(p_int)}]({esc(p_int)})")
                else:
                    st.markdown("- 🎓 **Student & Internship Opportunities:** *Not separately verified (apply via main careers portal)*")

                if p_grad and p_grad != p_main:
                    st.markdown(f"- 🚀 **University Graduate Programs:** [{esc(p_grad)}]({esc(p_grad)})")
                else:
                    st.markdown("- 🚀 **University Graduate Programs:** *Not separately verified (apply via main careers portal)*")

    else:
        st.markdown(f"#### 📋 Enterprise Directory ({len(filtered_company_list)} Companies Matching Filters)")

        ITEMS_PER_PAGE = 9
        if "dir_page" not in st.session_state:
            st.session_state.dir_page = 0

        max_pages = max(1, (len(filtered_company_list) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        st.session_state.dir_page = min(st.session_state.dir_page, max_pages - 1)

        start_idx = st.session_state.dir_page * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        current_page_companies = filtered_company_list[start_idx:end_idx]

        grid_cols = st.columns(3)
        for idx, cname in enumerate(current_page_companies):
            cd = COMPANY_DATABASE[cname]
            with grid_cols[idx % 3]:
                st.markdown(f"""
                <div class="glass-card" style="min-height: 195px; border-top: 3px solid #38BDF8; margin-bottom: 0.8rem;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <h4 style="margin: 0; color: #38BDF8;">{esc(cname)}</h4>
                        <span style="font-size: 0.72rem; padding: 2px 8px; border-radius: 12px; background: rgba(56, 189, 248, 0.15); color: #38BDF8;">
                            {esc(cd.get('primary_category'))}
                        </span>
                    </div>
                    <div style="font-size: 0.8rem; color: #94A3B8; margin: 0.4rem 0;">
                        <b>HQ:</b> {esc(cd.get('headquarters', 'USA'))}<br>
                        <b>Hubs:</b> {esc(cd.get('india_presence', 'India'))[:35]}...
                    </div>
                    <div style="font-size: 0.78rem; color: #CBD5E1;">
                        <b>Status:</b> {esc(cd.get('hiring_status'))}<br>
                        <b>Roles:</b> {', '.join(esc(r) for r in list(cd.get('roles', {}).keys())[:2])}
                    </div>
                    <div style="margin-top: 0.6rem;">
                        <a href="{esc(cd.get('official_career_url'))}" target="_blank" style="color: #38BDF8; font-size: 0.8rem; text-decoration: none; font-weight: 600;">Open Portal ↗</a>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        pg_c1, pg_c2, pg_c3 = st.columns([1, 2, 1])
        with pg_c1:
            if st.button("◀ Previous Page", disabled=(st.session_state.dir_page == 0), use_container_width=True):
                st.session_state.dir_page -= 1
                st.rerun()
        with pg_c2:
            st.markdown(f"<div style='text-align: center; color: #94A3B8; font-size: 0.9rem; padding-top: 0.4rem;'>Page <b>{st.session_state.dir_page + 1}</b> of <b>{max_pages}</b> ({len(filtered_company_list)} enterprises)</div>", unsafe_allow_html=True)
        with pg_c3:
            if st.button("Next Page ▶", disabled=(st.session_state.dir_page >= max_pages - 1), use_container_width=True):
                st.session_state.dir_page += 1
                st.rerun()

# ----------------- TAB 6: COMPANY COMPARISON MATRIX -----------------
with tabs[5]:
    st.markdown("### ⚖️ Multi-Company Placement Comparison Matrix")
    st.caption("Factual, side-by-side comparison across recruitment standards, compensation ranges, and DSA intensity.")

    comp_options = get_all_company_names()
    default_sel = [c for c in ["Amazon", "Google", "Microsoft", "TCS"] if c in comp_options]

    selected_for_comp = st.multiselect(
        "Select up to 4 Companies to Compare:",
        comp_options,
        default=default_sel,
        max_selections=4,
        key="comp_multiselect_matrix"
    )

    if not selected_for_comp:
        st.info("Select at least one enterprise from the dropdown above to render the comparison view.")
    else:
        num_selected = len(selected_for_comp)
        cols = st.columns(num_selected)

        for idx, cname in enumerate(selected_for_comp):
            vm = get_company_comparison_view_model(cname, target_role=target_role_track)

            core_cs_str = " • ".join(esc(c) for c in vm["core_cs"][:3])
            if len(vm["core_cs"]) > 3:
                core_cs_str += f" +{len(vm['core_cs']) - 3} more"

            hubs_str = " • ".join(esc(h) for h in vm["major_hubs"][:3])
            if len(vm["major_hubs"]) > 3:
                hubs_str += f" +{len(vm['major_hubs']) - 3} more"

            dsa_color = "#34D399" if "Low" in vm["dsa_intensity"] else ("#F87171" if "Extreme" in vm["dsa_intensity"] else "#FBBF24")

            if vm["careers_url"]:
                portal_html = f'<a href="{esc(vm["careers_url"])}" target="_blank" rel="noopener noreferrer" style="color: #38BDF8; font-weight: 600; text-decoration: none;">🔗 Official Careers Portal ↗</a>'
            else:
                portal_html = '<span style="color: #94A3B8;">Career portal not verified</span>'

            card_html = textwrap.dedent(f"""
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-top: 4px solid #38BDF8; border-radius: 12px; padding: 1.1rem; margin-bottom: 0.6rem; backdrop-filter: blur(10px);">
                <div style="margin-bottom: 0.4rem;">
                    <h3 style="margin: 0; color: #38BDF8; font-size: 1.25rem; font-weight: 700;">{esc(vm['name'])}</h3>
                    <span style="font-size: 0.78rem; color: #94A3B8; text-transform: uppercase; font-weight: 600;">{esc(vm['category'])} Sector</span>
                </div>
                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 0.6rem 0 0.8rem 0;">
                <div style="font-size: 0.84rem; line-height: 1.6; color: #E2E8F0;">
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">Hiring Status</span><br>
                        <span>{esc(vm['hiring_status'])}</span>
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">DSA Intensity</span><br>
                        <span style="color: {dsa_color}; font-weight: 700;">{esc(vm['dsa_intensity'])}</span>
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">Evaluated Track</span><br>
                        <span>{esc(vm['role'])}</span>
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">Compensation Package</span><br>
                        <span style="color: #34D399; font-weight: 700;">{esc(vm['comp_range'])}</span>
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">Core CS Focus</span><br>
                        <span style="color: #CBD5E1;">{core_cs_str}</span>
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">Major India Hubs</span><br>
                        <span style="color: #CBD5E1;">{hubs_str}</span>
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <span style="color: #94A3B8; font-size: 0.76rem; text-transform: uppercase; font-weight: 700;">Career Gateway</span><br>
                        {portal_html}
                    </div>
                    <div style="margin-top: 0.8rem; font-size: 0.74rem; color: #64748B;">
                        🕒 Verified: {esc(vm['last_verified'])}
                    </div>
                </div>
            </div>
            """).strip()

            with cols[idx]:
                st.markdown(card_html, unsafe_allow_html=True)
                
                if vm["interview_stages"]:
                    with st.expander("🎯 Rounds & OA Pattern"):
                        for s_num, stg in enumerate(vm["interview_stages"], 1):
                            st.markdown(f"**R{s_num} ({esc(stg.get('type'))}):** {esc(stg.get('round'))}")
                            st.caption(f"Focus: {esc(stg.get('focus'))}")

# ----------------- TAB 7: CANDIDATE PROFILE -----------------
with tabs[6]:
    st.markdown("### 👤 Candidate Profile & Authentication Verification")

    p1, p2 = st.columns([1, 1.8], gap="large")

    with p1:
        avatar_html = (
            f'<img src="{esc(user.get("profile_image"))}" style="width: 90px; height: 90px; border-radius: 50%; object-fit: cover; border: 3px solid #38BDF8; margin-bottom: 0.8rem;">'
            if user.get("profile_image")
            else '<div style="font-size: 3.8rem; margin-bottom: 0.4rem;">🎓</div>'
        )
        provider_badge = str(user.get("auth_provider", "email")).upper()

        st.markdown(f"""
        <div class="glass-card" style="text-align: center; padding: 1.8rem 1.2rem;">
            {avatar_html}
            <h3 style="margin: 0.2rem 0; color: #F8FAFC;">{esc(user.get('name', 'Candidate'))}</h3>
            <p style="color: #94A3B8; font-size: 0.88rem; margin-bottom: 0.6rem;">{esc(user.get('email', 'No email provided'))}</p>
            <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.78rem; font-weight: 600;">
                Verified via {esc(provider_badge)}
            </span>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚪 Sign Out of VVIT CareerPilot", use_container_width=True, type="primary"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            init_session_state(force_reset=True)
            st.rerun()

    with p2:
        st.markdown("#### 🎓 Academic & Placement Target Data")

        c_meta1, c_meta2 = st.columns(2)
        with c_meta1:
            st.markdown(f"**College / University:**\n`{user.get('college') or 'Not Specified'}`")
            st.markdown(f"**Graduation Batch:**\n`Class of {user.get('grad_year') or '2026'}`")
        with c_meta2:
            st.markdown(f"**Engineering Branch:**\n`{user.get('branch') or 'Computer Science & Engineering'}`")
            st.markdown(f"**Target Role Track:**\n`{user.get('target_role') or 'SDE'}`")

        st.markdown("<hr style='margin: 1rem 0; border-color: rgba(255,255,255,0.08);'>", unsafe_allow_html=True)

        st.markdown("#### 🛠 Verified Technical Stack & Readiness Profile")
        st.code(user.get("primary_stack") or "C++, Java, Python, SQL, Operating Systems, DBMS, Computer Networks")
        st.caption("Identity record stored in the local SQLite database (`users.db`).")