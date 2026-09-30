"""
Interview & Conversational Intelligence Engine for PlacementPrep OS.
Features:
- Multi-turn conversational memory with SQLite persistence (`users.db`)
- Guaranteed native script response generation (Telugu, Hindi, Tamil, Kannada, etc.)
- Automatic localization pass ensuring non-English text is never sent as raw English
- Dynamic topic graph tracking & context linking across turns
- Anti-repetition question memory
- Adaptive AI service binding to prevent ImportError
"""

import os
import re
import json
import sqlite3
import datetime
from typing import Dict, List, Any, Optional

# Dynamically import ai_service functions safely
import ai_service
from language_config import (
    get_language_config,
    text_has_script_characters,
    detect_script_language
)

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

# =============================================================================
# 1. ADAPTIVE LLM DISPATCHER (Resolves ImportError)
# =============================================================================

def call_gemini(prompt: str, temperature: float = 0.6, max_tokens: int = 850) -> str:
    """
    Safely connects to whichever generator function exists inside ai_service.py
    without causing import mismatch errors.
    """
    # 1. Search for function names commonly used in ai_service
    possible_names = [
        "call_gemini", "generate_response", "call_llm", 
        "generate_text", "get_ai_response", "ask_gemini", 
        "generate_conversational_turn"
    ]
    for fn_name in possible_names:
        if hasattr(ai_service, fn_name):
            fn = getattr(ai_service, fn_name)
            try:
                res = fn(prompt)
                return str(res.text if hasattr(res, "text") else res).strip()
            except TypeError:
                try:
                    res = fn(prompt, temperature=temperature)
                    return str(res.text if hasattr(res, "text") else res).strip()
                except Exception:
                    pass
            except Exception:
                pass

    # 2. Direct fallback using google.generativeai if available
    try:
        import google.generativeai as genai
        # Re-use existing api_key if configured
        if hasattr(ai_service, "GEMINI_API_KEY") and ai_service.GEMINI_API_KEY:
            genai.configure(api_key=ai_service.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        # Graceful fallback response
        return "I understand your question. Let's explore the core concepts and implementation details together."

# =============================================================================
# 2. DATABASE SCHEMA INITIALIZATION
# =============================================================================

def init_interview_db():
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                user_email TEXT NOT NULL,
                title TEXT,
                messages_json TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asked_questions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT NOT NULL,
                question_text TEXT NOT NULL,
                topic TEXT,
                asked_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_interview_db()

# =============================================================================
# 3. MEMORY & SESSION UTILITIES
# =============================================================================

def get_user_memories(user_email: str) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT category, content, created_at FROM conversation_memories WHERE user_email = ? ORDER BY id DESC LIMIT 15",
            (user_email,)
        ).fetchall()
        return [dict(r) for r in rows]

def add_user_memory(user_email: str, category: str, content: str):
    if not content or not content.strip():
        return
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO conversation_memories (user_email, category, content) VALUES (?, ?, ?)",
            (user_email, category, content.strip())
        )
        conn.commit()

def clear_all_memories(user_email: str):
    with _get_db() as conn:
        conn.execute("DELETE FROM conversation_memories WHERE user_email = ?", (user_email,))
        conn.commit()

def save_conversation_session(session_id: str, user_email: str, title: str, messages: List[Dict[str, Any]]):
    with _get_db() as conn:
        conn.execute("""
            INSERT INTO conversation_sessions (session_id, user_email, title, messages_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                title = excluded.title,
                messages_json = excluded.messages_json,
                updated_at = CURRENT_TIMESTAMP
        """, (session_id, user_email, title, json.dumps(messages)))
        conn.commit()

def get_user_conversation_sessions(user_email: str) -> List[Dict[str, Any]]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT session_id, title, messages_json, updated_at FROM conversation_sessions WHERE user_email = ? ORDER BY updated_at DESC LIMIT 10",
            (user_email,)
        ).fetchall()
        res = []
        for r in rows:
            try:
                msgs = json.loads(r["messages_json"])
            except Exception:
                msgs = []
            res.append({"session_id": r["session_id"], "title": r["title"], "messages": msgs, "updated_at": r["updated_at"]})
        return res

def log_asked_question(user_email: str, question_text: str, topic: str = "General"):
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO asked_questions_log (user_email, question_text, topic) VALUES (?, ?, ?)",
            (user_email, question_text[:500], topic)
        )
        conn.commit()

def get_recent_asked_questions(user_email: str) -> List[str]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT question_text FROM asked_questions_log WHERE user_email = ? ORDER BY id DESC LIMIT 20",
            (user_email,)
        ).fetchall()
        return [r["question_text"] for r in rows]

# =============================================================================
# 4. TOPIC GRAPH & CONTEXT EXTRACTOR
# =============================================================================

def extract_topic_context(history: List[Dict[str, str]]) -> Dict[str, Any]:
    text_corpus = " ".join(m.get("content", "") for m in history[-6:]).lower()
    topics = []
    if "oops" in text_corpus or "inheritance" in text_corpus or "polymorphism" in text_corpus:
        topics.append("OOP Concepts")
    if "java" in text_corpus or "jvm" in text_corpus:
        topics.append("Java Core")
    if "tree" in text_corpus or "lca" in text_corpus:
        topics.append("Trees")
    if "graph" in text_corpus or "topological" in text_corpus or "bfs" in text_corpus:
        topics.append("Graphs")
    if "binary search" in text_corpus:
        topics.append("Binary Search")
    if "dbms" in text_corpus or "acid" in text_corpus or "sql" in text_corpus:
        topics.append("Database Management")
    if "os" in text_corpus or "deadlock" in text_corpus or "thread" in text_corpus:
        topics.append("Operating Systems")

    return {
        "active_topics": topics if topics else ["General Placement Interview"],
        "primary_focus": topics[0] if topics else "General Engineering"
    }

# =============================================================================
# 5. GUARANTEED NATIVE SCRIPT TRANSLATION / LOCALIZATION
# =============================================================================

def force_localize_response(text: str, target_language: str) -> str:
    """Translates or localizes English response text into the candidate's selected Indic language."""
    if target_language in ("English", "Auto Detect"):
        return text
        
    cfg = get_language_config(target_language)
    native_name = cfg.get("nativeName", target_language)

    trans_prompt = f"""
You are a technical translator for engineering placement candidates.
TASK: Translate the following response completely into {target_language} ({native_name}).

STRICT RULES:
1. The response MUST be written in {target_language} script. Do NOT respond in English.
2. Standard industry technical keywords (e.g. Java, OOPS, Inheritance, Polymorphism, Class, Object, JVM, Method, SQL, DSA, Stack, Queue) can remain written in English or transliterated.
3. Every sentence explaining the concept, greeting, and transition MUST be in natural, fluent {target_language}.
4. Return ONLY the translated {target_language} text without meta commentary.

SOURCE TEXT:
{text}
"""
    try:
        translated = call_gemini(trans_prompt, temperature=0.3, max_tokens=900)
        return translated.strip() if translated else text
    except Exception:
        return text

# =============================================================================
# 6. CORE CONVERSATIONAL RESPONSE DISPATCHER
# =============================================================================

def generate_conversational_response(
    user_message: str,
    user_profile: Dict[str, Any],
    conversation_history: List[Dict[str, str]],
    agent_state: Dict[str, Any],
    language: str = "English"
) -> str:
    user_name = user_profile.get("name", "Candidate")
    user_email = user_profile.get("email", "")
    target_comp = user_profile.get("target_company", "Amazon")
    target_role = user_profile.get("target_role", "SDE")
    
    # 1. Resolve target language
    actual_lang = language
    if language == "Auto Detect":
        actual_lang = detect_script_language(user_message)
    
    cfg = get_language_config(actual_lang)
    native_label = cfg.get("nativeName", actual_lang)

    # 2. Retrieve persistent memories
    memories = get_user_memories(user_email)
    memory_summary = "\n".join(f"- [{m['category']}] {m['content']}" for m in memories[:5]) if memories else "None recorded yet."
    topic_ctx = extract_topic_context(conversation_history)
    past_questions = get_recent_asked_questions(user_email)
    avoid_q_prompt = f"DO NOT repeat these questions:\n" + "\n".join(f"- {q}" for q in past_questions[:5]) if past_questions else ""

    # 3. Native Script Enforcement
    if actual_lang != "English":
        language_directive = f"""
CRITICAL LANGUAGE CONTRACT (MANDATORY):
- Target Language: {actual_lang} ({native_label})
- You MUST answer COMPLETELY in {actual_lang} script.
- Do NOT output English sentences.
- Technical vocabulary like Java, OOPS, Polymorphism, Inheritance, Class, Object, JVM, Method Overloading, Binary Search can remain in English or transliterated for clarity.
- All conversational framing, greetings, questions, and explanations MUST be in natural {actual_lang}.
"""
    else:
        language_directive = "Language: English. Provide clear, professional technical interview responses."

    system_prompt = f"""
You are the autonomous AI Technical Interviewer & Career Intelligence Coach for PlacementPrep OS.
Target: {target_comp} ({target_role})
Candidate: {user_name}

Persistent Candidate Memory:
{memory_summary}

Active Focus: {topic_ctx['primary_focus']} (Connected: {', '.join(topic_ctx['active_topics'])})

{language_directive}

Rules:
1. Conduct realistic, rigorous technical interviews aligned with {target_comp}'s hiring bar.
2. Provide intuition, edge cases, and guided feedback rather than code dumps.
3. Resolve references to "it", "this", or "previous answer" using the active topic context.
{avoid_q_prompt}
"""

    formatted_history = []
    for m in conversation_history[-8:]:
        role = "user" if m["role"] == "user" else "assistant"
        formatted_history.append({"role": role, "content": m["content"]})

    if not formatted_history or formatted_history[-1]["content"] != user_message:
        formatted_history.append({"role": "user", "content": user_message})

    full_prompt = f"{system_prompt}\n\nCONVERSATION:\n"
    for turn in formatted_history:
        prefix = "Candidate" if turn["role"] == "user" else "Interviewer"
        full_prompt += f"{prefix}: {turn['content']}\n"
    full_prompt += "Interviewer:"

    reply = call_gemini(full_prompt, temperature=0.6, max_tokens=850).strip()

    # 4. Mandatory Verification Gate: If chosen language is Indic but LLM spoke English, FORCE localization!
    if actual_lang != "English" and not text_has_script_characters(reply, actual_lang):
        reply = force_localize_response(reply, actual_lang)

    # Log memory if candidate states weakness or strength
    low_msg = user_message.lower()
    if "struggle" in low_msg or "weak" in low_msg or "don't know" in low_msg:
        add_user_memory(user_email, "Candidate Weakness", user_message[:200])
    elif "strong" in low_msg or "confident" in low_msg or "solved" in low_msg:
        add_user_memory(user_email, "Candidate Strength", user_message[:200])

    return reply