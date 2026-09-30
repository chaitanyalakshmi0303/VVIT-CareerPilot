"""
Centralized AI Service & Health-Check Layer for PlacementPrep OS.
Provides multi-model failover, API key verification, structured health checks,
and GenAI SDK integration with REST fallbacks.
"""

import os
import re
import time
import json
import logging
import requests
from typing import Dict, List, Any, Tuple, Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8-sig")
load_dotenv(encoding="utf-8-sig")

logger = logging.getLogger("PlacementPrep.AIService")

# Primary & Fallback Models
AI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
AI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")

MODEL_FALLBACK_CHAIN = [
    AI_TEXT_MODEL,
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite"
]

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
REQUEST_TIMEOUT = 25
TOTAL_DEADLINE = 55
MAX_OUTPUT_TOKENS = 4096

class AIServiceError(Exception):
    """Custom exception containing sanitized, user-safe error messages."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

def get_api_key() -> str:
    """Safely retrieves the Gemini API key from environment or secrets."""
    key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        try:
            import streamlit as st
            if "GEMINI_API_KEY" in st.secrets:
                key = str(st.secrets["GEMINI_API_KEY"]).strip()
        except Exception:
            pass
    return key

def scrub_sensitive_info(text: str, key: str = "") -> str:
    """Removes API keys from logs and output text."""
    txt = str(text or "")
    if key:
        txt = txt.replace(key, "******")
    return re.sub(r"(key=)[^&\s\"']+", r"\1******", txt)[:400]

def check_ai_health() -> Dict[str, Any]:
    """
    Performs startup verification of the AI layer.
    Returns: {status: str, model: str, latency_ms: int, message: str}
    Statuses: READY, INVALID_API_KEY, MODEL_NOT_FOUND, QUOTA_EXCEEDED, RATE_LIMITED, NETWORK_ERROR, UNKNOWN_ERROR
    """
    key = get_api_key()
    if not key:
        return {
            "status": "INVALID_API_KEY",
            "model": AI_TEXT_MODEL,
            "latency_ms": 0,
            "message": "Gemini API key is missing. Add GEMINI_API_KEY to your .env file."
        }

    url = f"{API_BASE}/{AI_TEXT_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 5}
    }

    t0 = time.time()
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        latency = int((time.time() - t0) * 1000)

        if res.status_code == 200:
            return {
                "status": "READY",
                "model": AI_TEXT_MODEL,
                "latency_ms": latency,
                "message": f"AI service operational on {AI_TEXT_MODEL}."
            }

        body = res.json().get("error", {}) if res.content else {}
        err_msg = body.get("message", res.text).lower()

        if res.status_code == 404 or "not found" in err_msg:
            return {
                "status": "MODEL_NOT_FOUND",
                "model": AI_TEXT_MODEL,
                "latency_ms": latency,
                "message": f"Configured model '{AI_TEXT_MODEL}' was not found. Using fallback chain."
            }
        elif res.status_code in (401, 403) or "api key" in err_msg:
            return {
                "status": "INVALID_API_KEY",
                "model": AI_TEXT_MODEL,
                "latency_ms": latency,
                "message": "Gemini API key is invalid or lacks necessary permissions."
            }
        elif res.status_code == 429 or "quota" in err_msg:
            return {
                "status": "QUOTA_EXCEEDED",
                "model": AI_TEXT_MODEL,
                "latency_ms": latency,
                "message": "Gemini rate limit or quota exceeded. Please try again shortly."
            }
        else:
            return {
                "status": "UNKNOWN_ERROR",
                "model": AI_TEXT_MODEL,
                "latency_ms": latency,
                "message": f"API check returned code {res.status_code}: {scrub_sensitive_info(err_msg, key)}"
            }

    except requests.exceptions.RequestException as e:
        return {
            "status": "NETWORK_ERROR",
            "model": AI_TEXT_MODEL,
            "latency_ms": int((time.time() - t0) * 1000),
            "message": f"Network error connecting to Google AI servers: {type(e).__name__}"
        }

def format_gemini_turns(history_payload: list, user_message: str) -> list:
    """Formats conversation into standard user/model alternating turns."""
    turns: List[Dict[str, Any]] = []
    for h in history_payload or []:
        content = str(h.get("content") or "").strip()
        if not content:
            continue
        role = "user" if h.get("role") == "user" else "model"
        if turns and turns[-1]["role"] == role:
            turns[-1]["parts"][0]["text"] += "\n\n" + content
        else:
            turns.append({"role": role, "parts": [{"text": content}]})

    while turns and turns[0]["role"] != "user":
        turns.pop(0)

    clean_msg = str(user_message).strip()
    if turns and turns[-1]["role"] == "user":
        turns[-1]["parts"][0]["text"] += "\n\n" + clean_msg
    else:
        turns.append({"role": "user", "parts": [{"text": clean_msg}]})

    return turns

def generate_text_content(
    system_prompt: str,
    history_payload: list,
    user_message: str,
    temperature: float = 0.65,
    max_tokens: int = MAX_OUTPUT_TOKENS
) -> Tuple[str, str]:
    """
    Executes content generation across the active fallback chain.
    Returns: (generated_text, model_name_used)
    Raises: AIServiceError on complete failure.
    """
    key = get_api_key()
    if not key:
        raise AIServiceError("INVALID_API_KEY", "Gemini API key is missing. Add GEMINI_API_KEY to your .env file.")

    formatted_contents = format_gemini_turns(history_payload, user_message)

    # 1. Primary path: Official Google GenAI SDK
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)

        sdk_contents = []
        for turn in formatted_contents:
            role = turn["role"]
            txt = turn["parts"][0]["text"]
            sdk_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=txt)]))

        for model_name in MODEL_FALLBACK_CHAIN:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=sdk_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                        max_output_tokens=max_tokens
                    )
                )
                if resp and resp.text:
                    return resp.text.strip(), model_name
            except Exception as sdk_err:
                err_str = str(sdk_err).lower()
                logger.warning(f"SDK failure on {model_name}: {err_str[:120]}")
                if "404" in err_str or "not found" in err_str:
                    continue  # Try next model in chain
                if "401" in err_str or "403" in err_str:
                    raise AIServiceError("INVALID_API_KEY", "Gemini rejected the API key or its permissions.")
    except ImportError:
        pass  # Fall back directly to REST

    # 2. REST Fallback Pipeline
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": formatted_contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}

    deadline = time.time() + TOTAL_DEADLINE
    last_err_code = "UNKNOWN_ERROR"
    last_err_msg = "No response from AI models."

    for model_name in MODEL_FALLBACK_CHAIN:
        remaining_time = deadline - time.time()
        if remaining_time <= 2:
            break

        url = f"{API_BASE}/{model_name}:generateContent"
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=min(REQUEST_TIMEOUT, remaining_time))
            if resp.status_code == 200:
                data = resp.json()
                cands = data.get("candidates", [])
                if cands:
                    parts = (cands[0].get("content") or {}).get("parts", [])
                    txt = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
                    if txt:
                        return txt, model_name

            # Evaluate HTTP failures
            if resp.status_code in (404,):
                last_err_code = "MODEL_NOT_FOUND"
                last_err_msg = f"Model {model_name} not available on current endpoint."
                continue
            elif resp.status_code in (401, 403):
                raise AIServiceError("INVALID_API_KEY", "Gemini API key is invalid or expired.")
            elif resp.status_code == 429:
                last_err_code = "RATE_LIMITED"
                last_err_msg = "API quota exceeded. Retrying alternate model tier..."
                continue
            else:
                last_err_code = f"HTTP_{resp.status_code}"
                last_err_msg = scrub_sensitive_info(resp.text, key)

        except requests.exceptions.RequestException as net_err:
            last_err_code = "NETWORK_ERROR"
            last_err_msg = f"Network connection error: {type(net_err).__name__}"
            continue

    raise AIServiceError(last_err_code, f"Unable to generate response ({last_err_code}: {last_err_msg})")