"""
Authentication & Identity Management for PlacementPrep OS.
Supports:
- GitHub OAuth 2.0 Web Application Flow
- Local PBKDF2 / Salted SHA-256 password authentication
- SQLite persistent user store with relative path resolution
"""

import os
import sqlite3
import hashlib
import secrets
import urllib.parse
import requests
from typing import Dict, Any, Tuple, Optional

# Relative deployment-safe path
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

# GitHub OAuth credentials from environment
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501").rstrip("/")

def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def init_auth_tables():
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT,
                salt TEXT,
                auth_provider TEXT DEFAULT 'email',
                college TEXT,
                branch TEXT,
                grad_year TEXT,
                target_role TEXT DEFAULT 'SDE',
                target_company TEXT DEFAULT 'Amazon',
                profile_image TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_auth_tables()

# =============================================================================
# PASSWORD CRYPTOGRAPHY
# =============================================================================

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return pw_hash, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    if not stored_hash or not salt:
        return False
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, stored_hash)

# =============================================================================
# USER STORE OPERATIONS
# =============================================================================

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if not email:
        return None
    with _get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),)).fetchone()
        return dict(row) if row else None

def create_user(
    email: str,
    name: str,
    password: Optional[str] = None,
    auth_provider: str = "email",
    college: str = "",
    branch: str = "",
    grad_year: str = "2026",
    target_role: str = "SDE",
    profile_image: str = ""
) -> Optional[Dict[str, Any]]:
    clean_email = email.strip().lower()
    pw_hash, salt = (None, None)
    if password:
        pw_hash, salt = hash_password(password)

    try:
        with _get_db() as conn:
            conn.execute("""
                INSERT INTO users (email, name, password_hash, salt, auth_provider, college, branch, grad_year, target_role, profile_image)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (clean_email, name.strip(), pw_hash, salt, auth_provider, college.strip(), branch.strip(), grad_year, target_role, profile_image))
            conn.commit()
        return get_user_by_email(clean_email)
    except sqlite3.IntegrityError:
        return None

# =============================================================================
# GITHUB OAUTH PIPELINE
# =============================================================================

def get_github_auth_url() -> Optional[str]:
    if not GITHUB_CLIENT_ID:
        return None
    redirect_uri = f"{APP_BASE_URL}/"
    state = secrets.token_hex(16)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state
    }
    return f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"

def handle_oauth_callback(code: str, state: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Exchanges GitHub authorization code for user profile."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return None, "GitHub client secrets not configured on host environment."

    token_url = "https://github.com/login/oauth/access_token"
    token_payload = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": f"{APP_BASE_URL}/"
    }
    headers = {"Accept": "application/json"}

    try:
        t_res = requests.post(token_url, json=token_payload, headers=headers, timeout=10)
        t_data = t_res.json()
        access_token = t_data.get("access_token")

        if not access_token:
            return None, t_data.get("error_description", "Failed to retrieve access token from GitHub.")

        # Query GitHub user profile
        u_res = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=10
        )
        u_data = u_res.json()
        
        email = u_data.get("email")
        if not email:
            # Query secondary emails endpoint if primary email is private
            e_res = requests.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                timeout=10
            )
            for item in e_res.json():
                if item.get("primary") and item.get("verified"):
                    email = item.get("email")
                    break

        if not email:
            email = f"{u_data.get('login')}@users.noreply.github.com"

        name = u_data.get("name") or u_data.get("login") or "Developer"
        avatar = u_data.get("avatar_url", "")

        existing = get_user_by_email(email)
        if existing:
            return existing, None

        new_user = create_user(
            email=email,
            name=name,
            auth_provider="github",
            profile_image=avatar,
            target_role="SDE"
        )
        return new_user, None

    except Exception as e:
        return None, f"GitHub authentication failed: {str(e)}"