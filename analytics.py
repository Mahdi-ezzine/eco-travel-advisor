"""
analytics.py

"""

import pandas as pd

from db import create_connection


def _read(query, params=None):
    conn = create_connection()
    if not conn:
        return pd.DataFrame()
    try:
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def most_common_intents():
    """Count user intents recorded in ChatMessage, most frequent first."""
    query = """
        SELECT intent, COUNT(*) AS total
        FROM ChatMessage
        WHERE intent IS NOT NULL
        GROUP BY intent
        ORDER BY total DESC;
    """
    return _read(query)


def average_carbon_by_mode():
    """Average and total carbon per transport mode in the catalogue."""
    query = """
        SELECT mode,
               ROUND(AVG(carbon_kg), 2) AS avg_carbon_kg,
               COUNT(*) AS options
        FROM TransportOption
        GROUP BY mode
        ORDER BY avg_carbon_kg ASC;
    """
    return _read(query)


def hotel_sustainability_distribution():
    """Distribution of eco hotels across sustainability-score buckets."""
    query = """
        SELECT
            CASE
                WHEN sustainability_score >= 80 THEN '80-100'
                WHEN sustainability_score >= 60 THEN '60-79'
                WHEN sustainability_score >= 40 THEN '40-59'
                ELSE 'below 40'
            END AS score_band,
            COUNT(*) AS hotels
        FROM EcoHotel
        GROUP BY score_band
        ORDER BY score_band;
    """
    return _read(query)


def cumulative_trip_plans_by_day():
    """Daily and running-total trip plans (window function)."""
    query = """
        SELECT
            created_at::date AS day,
            COUNT(*) AS plans_on_day,
            SUM(COUNT(*)) OVER (ORDER BY created_at::date) AS cumulative_plans
        FROM TripPlan
        GROUP BY created_at::date
        ORDER BY day;
    """
    return _read(query)


def top_destinations(limit=10):
    """Most planned destinations across all trip plans."""
    query = """
        SELECT destination, COUNT(*) AS plans
        FROM TripPlan
        WHERE destination IS NOT NULL
        GROUP BY destination
        ORDER BY plans DESC
        LIMIT %(limit)s;
    """
    return _read(query, {"limit": limit})


def sustainability_level_breakdown():
    """
    Share of trip plans by sustainability level, using the FILTER clause to
    compute counts and average carbon side by side.
    """
    query = """
        SELECT
            sustainability_level,
            COUNT(*) AS plans,
            ROUND(AVG(total_carbon_kg), 2) AS avg_total_carbon_kg,
            COUNT(*) FILTER (WHERE total_carbon_kg < 100) AS low_carbon_plans
        FROM TripPlan
        WHERE sustainability_level IS NOT NULL
        GROUP BY sustainability_level
        ORDER BY plans DESC;
    """
    return _read(query)


def frequent_sessions_last_month():
    """Sessions with more than five messages in the last 30 days (CTE)."""
    query = """
        WITH recent AS (
            SELECT session_id, COUNT(*) AS messages
            FROM ChatMessage
            WHERE created_at >= (CURRENT_DATE - INTERVAL '30 days')
            GROUP BY session_id
        )
        SELECT s.session_id, s.user_ref, r.messages
        FROM ChatSession s
        JOIN recent r ON s.session_id = r.session_id
        WHERE r.messages > 5
        ORDER BY r.messages DESC
        LIMIT 20;
    """
    return _read(query)


def failed_actions():
    """Audit view of failed custom actions, most recent first."""
    query = """
        SELECT action_type, status, details, created_at
        FROM ChatbotActionLog
        WHERE status = 'failed'
        ORDER BY created_at DESC
        LIMIT 50;
    """
    return _read(query)


def handover_queue():
    """Pending human-handover requests with their packaged context."""
    query = """
        SELECT handover_id, session_id, plan_id, status, created_at
        FROM HandoverRequest
        WHERE status = 'pending'
        ORDER BY created_at DESC;
    """
    return _read(query)
