
# db.py  : Neon PostgreSQL access layer for the Eco-Travel Advisor.



import psycopg2
from psycopg2.extras import Json, RealDictCursor
import time

from config import get_database_url


def create_connection():
    """Open a connection to the Neon PostgreSQL database.
    """
    url = get_database_url()
    if not url:
        print("Database connection error: no DATABASE_URL configured.")
        return None
    for attempt in range(2):
        try:
            return psycopg2.connect(url, connect_timeout=10)
        except psycopg2.Error as error:
            if attempt == 0:
                time.sleep(2)  # Neon may be waking from idle; retry once.
                continue
            print("Database connection error: {0}".format(error))
            return None


def is_available():
    """Return True if the database can currently be reached.
    """
    conn = create_connection()
    if conn:
        conn.close()
        return True
    return False


def create_tables():
    """Create the full Eco-Travel Advisor schema if it does not exist."""
    conn = create_connection()
    if not conn:
        print("Connection failed.")
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS EcoHotel (
                hotel_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT,
                eco_certification TEXT,
                price_per_night NUMERIC(10, 2),
                sustainability_score INTEGER,
                carbon_per_night_kg NUMERIC(10, 2),
                rooms_available INTEGER
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS TransportOption (
                transport_id SERIAL PRIMARY KEY,
                origin_city TEXT NOT NULL,
                destination_city TEXT NOT NULL,
                mode TEXT NOT NULL,
                provider TEXT,
                price NUMERIC(10, 2),
                duration_minutes INTEGER,
                distance_km NUMERIC(10, 2),
                carbon_kg NUMERIC(10, 2),
                departure_time TIMESTAMP,
                arrival_time TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS CarbonOffsetProgram (
                offset_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                provider TEXT,
                country TEXT,
                price_per_ton NUMERIC(10, 2),
                project_type TEXT,
                verified BOOLEAN DEFAULT FALSE,
                description TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS CulturalExperience (
                experience_id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT,
                category TEXT,
                price NUMERIC(10, 2),
                supports_local_community BOOLEAN DEFAULT FALSE,
                duration_hours NUMERIC(5, 2),
                description TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS EcoFAQ (
                faq_id SERIAL PRIMARY KEY,
                question TEXT UNIQUE NOT NULL,
                answer TEXT NOT NULL,
                category TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_eco_faq_search
            ON EcoFAQ
            USING GIN (to_tsvector('english', question || ' ' || answer));
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ChatSession (
                session_id SERIAL PRIMARY KEY,
                user_ref TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ChatMessage (
                message_id SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES ChatSession(session_id),
                sender TEXT NOT NULL,
                text TEXT,
                intent TEXT,
                entities JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_message_entities
            ON ChatMessage USING GIN (entities);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS TripPlan (
                plan_id SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES ChatSession(session_id),
                origin TEXT,
                destination TEXT,
                start_date DATE,
                end_date DATE,
                budget NUMERIC(10, 2),
                sustainability_level TEXT,
                total_carbon_kg NUMERIC(10, 2),
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS TripPlanItem (
                item_id SERIAL PRIMARY KEY,
                plan_id INTEGER REFERENCES TripPlan(plan_id),
                item_type TEXT NOT NULL,
                ref_id INTEGER,
                description TEXT,
                price NUMERIC(10, 2),
                carbon_kg NUMERIC(10, 2)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS HandoverRequest (
                handover_id SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES ChatSession(session_id),
                plan_id INTEGER REFERENCES TripPlan(plan_id),
                context JSONB DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS UserPreference (
                pref_id SERIAL PRIMARY KEY,
                session_ref TEXT UNIQUE NOT NULL,
                preferences JSONB DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ChatbotActionLog (
                action_id SERIAL PRIMARY KEY,
                session_id INTEGER,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                details JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        print("Tables created successfully.")
    except psycopg2.Error as error:
        conn.rollback()
        print("Error creating tables: {0}".format(error))
    finally:
        cur.close()
        conn.close()


def reset_data():
    """Empty all tables and restart identity counters."""
    conn = create_connection()
    if not conn:
        print("Connection failed.")
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            TRUNCATE TABLE
                ChatbotActionLog,
                HandoverRequest,
                TripPlanItem,
                TripPlan,
                ChatMessage,
                ChatSession,
                UserPreference,
                EcoFAQ,
                CulturalExperience,
                CarbonOffsetProgram,
                TransportOption,
                EcoHotel
            RESTART IDENTITY CASCADE;
            """
        )
        conn.commit()
        print("All data reset successfully.")
    except psycopg2.Error as error:
        conn.rollback()
        print("Error resetting data: {0}".format(error))
    finally:
        cur.close()
        conn.close()


def drop_all_tables():
    """Drop every table (full teardown)."""
    conn = create_connection()
    if not conn:
        print("Connection failed.")
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DROP TABLE IF EXISTS
                ChatbotActionLog, HandoverRequest, TripPlanItem, TripPlan,
                ChatMessage, ChatSession, UserPreference, EcoFAQ,
                CulturalExperience, CarbonOffsetProgram, TransportOption,
                EcoHotel
            CASCADE;
            """
        )
        conn.commit()
        print("All tables dropped.")
    except psycopg2.Error as error:
        conn.rollback()
        print("Error dropping tables: {0}".format(error))
    finally:
        cur.close()
        conn.close()


def fetch_all(query, params=None):
    """Run a SELECT and return a list of dictionaries."""
    conn = create_connection()
    if not conn:
        return []
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, params or ())
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except psycopg2.Error as error:
        print("Query error: {0}".format(error))
        return []
    finally:
        cur.close()
        conn.close()


def get_or_create_session(user_ref):
    """Return an open session id for a user reference, creating one if needed."""
    conn = create_connection()
    if not conn:
        return None
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT session_id FROM ChatSession
            WHERE user_ref = %s AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1;
            """,
            (user_ref,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO ChatSession (user_ref) VALUES (%s) RETURNING session_id;",
            (user_ref,),
        )
        session_id = cur.fetchone()[0]
        conn.commit()
        return session_id
    except psycopg2.Error as error:
        conn.rollback()
        print("Session error: {0}".format(error))
        return None
    finally:
        cur.close()
        conn.close()


def delete_user_data(user_ref):
    """Delete all stored data for a given user reference (GDPR erasure).

    Removes the user's chat sessions and everything that depends on them
    (messages, trip plans and their items, handover requests, action logs).
    Returns the number of sessions removed, or None if the database is
    unreachable.
    """
    conn = create_connection()
    if not conn:
        return None
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT session_id FROM ChatSession WHERE user_ref = %s;",
            (user_ref,),
        )
        session_ids = [row[0] for row in cur.fetchall()]
        if not session_ids:
            return 0
        cur.execute(
            "SELECT plan_id FROM TripPlan WHERE session_id = ANY(%s);",
            (session_ids,),
        )
        plan_ids = [row[0] for row in cur.fetchall()]
        if plan_ids:
            cur.execute("DELETE FROM TripPlanItem WHERE plan_id = ANY(%s);",
                        (plan_ids,))
        # HandoverRequest references TripPlan, so remove it before TripPlan.
        cur.execute("DELETE FROM HandoverRequest WHERE session_id = ANY(%s);",
                    (session_ids,))
        cur.execute("DELETE FROM TripPlan WHERE session_id = ANY(%s);",
                    (session_ids,))
        cur.execute("DELETE FROM ChatbotActionLog WHERE session_id = ANY(%s);",
                    (session_ids,))
        cur.execute("DELETE FROM ChatMessage WHERE session_id = ANY(%s);",
                    (session_ids,))
        cur.execute("DELETE FROM ChatSession WHERE session_id = ANY(%s);",
                    (session_ids,))
        cur.execute("DELETE FROM UserPreference WHERE session_ref = %s;",
                    (user_ref,))
        conn.commit()
        return len(session_ids)
    except psycopg2.Error as error:
        conn.rollback()
        print("Data deletion error: {0}".format(error))
        return None
    finally:
        cur.close()
        conn.close()


def log_message(session_id, sender, text, intent=None, entities=None):
    """Persist a single conversation turn to ChatMessage."""
    conn = create_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO ChatMessage (session_id, sender, text, intent, entities)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (session_id, sender, text, intent, Json(entities or {})),
        )
        conn.commit()
    except psycopg2.Error as error:
        conn.rollback()
        print("Log message error: {0}".format(error))
    finally:
        cur.close()
        conn.close()


def log_action(session_id, action_type, status, details=None):
    """Record the outcome of a custom action (used for failed-API auditing)."""
    conn = create_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO ChatbotActionLog (session_id, action_type, status, details)
            VALUES (%s, %s, %s, %s);
            """,
            (session_id, action_type, status, Json(details or {})),
        )
        conn.commit()
    except psycopg2.Error as error:
        conn.rollback()
        print("Log action error: {0}".format(error))
    finally:
        cur.close()
        conn.close()
