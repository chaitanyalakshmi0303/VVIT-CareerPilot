"""
Placement Readiness Calculation & Analytics Engine for PlacementPrep OS.
Provides centralized scoring, telemetry aggregation, and deterministic readiness formulas.
No external network dependencies — failsafe and fully offline-capable.
"""

import re
import json
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

def _parse_pct(val: Any) -> int:
    if val is None:
        return 0
    digits = re.sub(r"[^\d]", "", str(val))
    return int(digits) if digits else 0

def get_db_user_problem_counts(user_email: str) -> Dict[str, int]:
    """Queries real problem activity from user_problem_history in users.db."""
    counts = {"SOLVED": 0, "ATTEMPTED": 0, "SKIPPED": 0}
    if not os.path.exists(DB_PATH):
        return counts
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT status, COUNT(*) FROM user_problem_history WHERE user_email = ? GROUP BY status",
            (user_email,)
        ).fetchall()
        for status, cnt in rows:
            if status in counts:
                counts[status] = cnt
        conn.close()
    except Exception:
        pass
    return counts

def calculate_dsa_readiness(dsa_tracker: Dict[str, Any], user_email: str = "") -> Tuple[int, int, Dict[str, Any]]:
    """
    Computes DSA Readiness score based on:
    - Topic accuracy & progression
    - Total solved counts in session tracker and SQLite database
    """
    if not dsa_tracker:
        return 0, 0, {}
    
    accuracies = []
    total_solved_tracker = 0
    weakest_topics = []

    for topic, meta in dsa_tracker.items():
        acc = _parse_pct(meta.get("accuracy", 0))
        accuracies.append(acc)
        solved = int(meta.get("solved", 0))
        total_solved_tracker += solved
        if acc < 60:
            weakest_topics.append((topic, acc, meta.get("weak", "General")))

    db_counts = get_db_user_problem_counts(user_email)
    total_solved = max(total_solved_tracker, db_counts["SOLVED"])
    
    avg_accuracy = sum(accuracies) / max(len(accuracies), 1)
    volume_score = min(100.0, (total_solved / 50.0) * 100.0)
    score = int(round(0.70 * avg_accuracy + 0.30 * volume_score))

    weakest_sorted = sorted(weakest_topics, key=lambda x: x[1])
    return max(0, min(100, score)), total_solved, {
        "avg_accuracy": int(avg_accuracy),
        "weakest": weakest_sorted[:3],
        "total_solved": total_solved
    }

def calculate_core_cs_readiness(last_oa_scores: Optional[Dict[str, int]], dsa_tracker: Dict[str, Any]) -> int:
    """Calculates Core CS readiness based on OA performance and fundamentals."""
    if last_oa_scores and "cs" in last_oa_scores:
        return last_oa_scores["cs"]
    return 40

def calculate_aiml_readiness(target_role: str, user_stack: str) -> Tuple[int, Dict[str, str]]:
    """Calculates AI/ML readiness based on technical stack verification."""
    modules = {
        "Python Fundamentals": "NOT_STARTED",
        "NumPy & Vectorized Math": "NOT_STARTED",
        "Pandas & Data Wrangling": "NOT_STARTED",
        "Scikit-Learn & Classical ML": "NOT_STARTED",
        "Deep Learning (PyTorch/TF)": "NOT_STARTED",
        "Transformers & LLM / RAG": "NOT_STARTED",
        "Model Optimization & MLOps": "NOT_STARTED"
    }
    
    low_stack = (user_stack or "").lower()
    
    if "python" in low_stack:
        modules["Python Fundamentals"] = "COMPLETED"
    if "numpy" in low_stack or "pandas" in low_stack:
        modules["NumPy & Vectorized Math"] = "COMPLETED"
        modules["Pandas & Data Wrangling"] = "COMPLETED"
    if "machine learning" in low_stack or "scikit" in low_stack:
        modules["Scikit-Learn & Classical ML"] = "COMPLETED"
    if "pytorch" in low_stack or "tensorflow" in low_stack:
        modules["Deep Learning (PyTorch/TF)"] = "IN_PROGRESS"
    if "llm" in low_stack or "rag" in low_stack or "transformer" in low_stack:
        modules["Transformers & LLM / RAG"] = "IN_PROGRESS"

    completed = sum(1 for status in modules.values() if status == "COMPLETED")
    in_prog = sum(1 for status in modules.values() if status == "IN_PROGRESS")
    
    score = int(round(((completed * 1.0 + in_prog * 0.5) / len(modules)) * 100))
    if "ai" not in target_role.lower() and "data" not in target_role.lower():
        score = max(score, 35)
    return min(100, score), modules

def calculate_overall_readiness(metrics: Dict[str, int]) -> Tuple[int, str, str]:
    """Computes weighted readiness and assigns standard placement stages."""
    weights = {
        "DSA": 0.25,
        "Core CS": 0.15,
        "SQL": 0.10,
        "AI/ML": 0.15,
        "Interview": 0.15,
        "OA": 0.10,
        "Resume": 0.10
    }
    
    total = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        val = metrics.get(key, 0)
        total += val * weight
        weight_sum += weight

    score = int(round(total / max(weight_sum, 0.01)))
    
    if score <= 30:
        stage = "Getting Started"
        color = "#94A3B8"
    elif score <= 50:
        stage = "Building Foundation"
        color = "#F59E0B"
    elif score <= 70:
        stage = "Developing Competency"
        color = "#38BDF8"
    elif score <= 85:
        stage = "Interview Ready"
        color = "#34D399"
    else:
        stage = "Highly Prepared"
        color = "#A855F7"

    return score, stage, color

def generate_dynamic_action_plan(
    dsa_info: Dict[str, Any],
    metrics: Dict[str, int],
    target_company: str,
    target_role: str
) -> List[Dict[str, str]]:
    """Generates 4 structured, priority-ranked daily tasks based on actual weaknesses."""
    plan = []
    
    weakest_dsa = dsa_info.get("weakest", [])
    if weakest_dsa:
        top_weak = weakest_dsa[0]
        plan.append({
            "category": "DSA DRILL",
            "time": "60 mins",
            "task": f"Solve 2 problems on **{top_weak[2]}** ({top_weak[0]} — current accuracy: {top_weak[1]}%).",
            "action_tab": "🧠 DSA Preparation Tracker"
        })
    else:
        plan.append({
            "category": "DSA DRILL",
            "time": "45 mins",
            "task": f"Solve 2 medium problems on **Binary Search on Monotonic Answer** targeted at {target_company}.",
            "action_tab": "🧠 DSA Preparation Tracker"
        })

    if metrics.get("Core CS", 0) <= metrics.get("SQL", 0):
        plan.append({
            "category": "CORE CS",
            "time": "45 mins",
            "task": f"Review **Operating Systems (Virtual Memory & Thrashing)** and **DBMS ACID transactions**.",
            "action_tab": "🎙️ AI Interview Simulator"
        })
    else:
        plan.append({
            "category": "SQL SANDBOX",
            "time": "30 mins",
            "task": "Practice 2 multi-table **Aggregation & Window Function** queries in the OA SQL sandbox.",
            "action_tab": "🎙️ AI Interview Simulator"
        })

    plan.append({
        "category": "SYSTEM / ML ARCHITECTURE",
        "time": "45 mins",
        "task": f"Deep dive into **Inference Latency, Distributed Caching & Microservice Design Patterns** for {target_company}.",
        "action_tab": "🎙️ AI Interview Simulator"
    })

    plan.append({
        "category": "PLACEMENT STRATEGY",
        "time": "20 mins",
        "task": f"Review verified interview rounds and syllabus criteria for **{target_company} ({target_role})**.",
        "action_tab": "🏢 Company Intelligence"
    })

    return plan