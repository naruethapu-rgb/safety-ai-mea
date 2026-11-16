"""API Usage & Cost Tracker for SafetyAI.
Tracks tokens, calculates costs in Thai Baht (THB), and stores monthly usage statistics
in SQLite database for 100% transparency.
"""

import datetime
from pathlib import Path
from typing import Dict, Any, List
from src.config import DB_PATH
from src.database import get_connection

# Official OpenAI Pricing (USD per 1M tokens)
PRICING = {
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
}
USD_TO_THB = 35.0  # Exchange rate approx


def init_usage_table(db_path: Path = DB_PATH):
    """Initializes the API usage log table if it doesn't exist."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                month_key TEXT,
                feature TEXT,
                model_name TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                cost_thb REAL,
                incident_title TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int):
    """Calculates cost in USD and THB based on model pricing."""
    rates = PRICING.get(model_name, PRICING["gpt-4o-mini"])
    cost_usd = (prompt_tokens / 1_000_000.0 * rates["prompt"]) + (completion_tokens / 1_000_000.0 * rates["completion"])
    cost_thb = cost_usd * USD_TO_THB
    return cost_usd, cost_thb


def record_api_usage(
    feature: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    incident_title: str = "",
    db_path: Path = DB_PATH
) -> Dict[str, Any]:
    """Records an API transaction into database and returns the cost breakdown."""
    init_usage_table(db_path)
    now = datetime.datetime.now()
    month_key = now.strftime("%Y-%m")
    total_tokens = prompt_tokens + completion_tokens
    cost_usd, cost_thb = calculate_cost(model_name, prompt_tokens, completion_tokens)

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO api_usage_logs (
                month_key, feature, model_name, prompt_tokens,
                completion_tokens, total_tokens, cost_usd, cost_thb, incident_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            month_key, feature, model_name, prompt_tokens,
            completion_tokens, total_tokens, cost_usd, cost_thb, incident_title
        ))
        conn.commit()
    finally:
        conn.close()

    return {
        "feature": feature,
        "model": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "cost_thb": cost_thb
    }


def get_usage_summary(db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Retrieves current month and all-time usage totals and recent history."""
    init_usage_table(db_path)
    current_month = datetime.datetime.now().strftime("%Y-%m")

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        # Monthly total
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_tokens), 0), COALESCE(SUM(cost_thb), 0), COALESCE(SUM(cost_usd), 0)
            FROM api_usage_logs
            WHERE month_key = ?
        """, (current_month,))
        m_row = cursor.fetchone()
        monthly_calls = m_row[0] or 0
        monthly_tokens = m_row[1] or 0
        monthly_cost_thb = m_row[2] or 0.0
        monthly_cost_usd = m_row[3] or 0.0

        # All-time total
        cursor.execute("SELECT COALESCE(SUM(cost_thb), 0) FROM api_usage_logs")
        all_time_thb = cursor.fetchone()[0] or 0.0

        # Recent 5 calls
        cursor.execute("""
            SELECT created_at, feature, model_name, total_tokens, cost_thb, incident_title
            FROM api_usage_logs
            ORDER BY id DESC
            LIMIT 5
        """)
        recent_logs = [
            {
                "time": r[0],
                "feature": r[1],
                "model": r[2],
                "tokens": r[3],
                "cost_thb": r[4],
                "title": r[5] or "-"
            }
            for r in cursor.fetchall()
        ]

        return {
            "current_month": current_month,
            "monthly_calls": monthly_calls,
            "monthly_tokens": monthly_tokens,
            "monthly_cost_thb": monthly_cost_thb,
            "monthly_cost_usd": monthly_cost_usd,
            "all_time_thb": all_time_thb,
            "recent_logs": recent_logs
        }
    finally:
        conn.close()
