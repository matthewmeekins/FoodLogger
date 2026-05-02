"""
Database module for food logging system.
Handles SQLite connection and all database operations.
"""

import sqlite3
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
import json


DB_PATH = "food_log.db"


RESOLVED_ENTRY_NUTRIENT_COLUMNS = [
    ("protein_g", "REAL"),
    ("carbs_g", "REAL"),
    ("fat_g", "REAL"),
    ("fiber_g", "REAL"),
    ("sugar_g", "REAL"),
    ("sodium_mg", "REAL"),
    ("potassium_mg", "REAL"),
    ("cholesterol_mg", "REAL"),
    ("saturated_fat_g", "REAL"),
    ("trans_fat_g", "REAL"),
    ("calcium_mg", "REAL"),
    ("iron_mg", "REAL"),
    ("vitamin_c_mg", "REAL"),
    ("vitamin_d_iu", "REAL"),
]

RESOLVED_ENTRY_EXTRA_COLUMNS = [
    ("created_at", "TEXT"),
    ("confidence_score", "REAL"),
    ("confidence_level", "TEXT"),
    ("source", "TEXT"),
    ("assumptions", "TEXT"),  # json
    ("reasoning", "TEXT"),  # OpenAI's component breakdown
    ("openai_response", "TEXT"),  # Full OpenAI JSON response for audit trail
]


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_resolved_entry_columns(cursor: sqlite3.Cursor) -> None:
    """Add missing nutrition columns for existing databases."""
    cursor.execute("PRAGMA table_info(resolved_entries)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_type in RESOLVED_ENTRY_NUTRIENT_COLUMNS + RESOLVED_ENTRY_EXTRA_COLUMNS:
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE resolved_entries ADD COLUMN {column_name} {column_type}"
            )


def _backfill_resolved_entry_created_at(cursor: sqlite3.Cursor) -> None:
    """Backfill missing resolved entry timestamps for older rows."""
    cursor.execute(
        """UPDATE resolved_entries
           SET created_at = COALESCE(created_at, logged_date || 'T12:00:00')
           WHERE created_at IS NULL OR created_at = ''"""
    )


def _ensure_indexes(cursor: sqlite3.Cursor) -> None:
    """Create indexes for hot query paths."""
    cursor.execute(
        """CREATE INDEX IF NOT EXISTS idx_resolved_entries_logged_date_id
           ON resolved_entries(logged_date, id DESC)"""
    )


def init_db() -> None:
    """Initialize database tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # raw_entries: never modify after insert
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            input_text  TEXT NOT NULL
        )
    """)
    
    # parsed_entries: LLM output storage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parsed_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id      INTEGER NOT NULL REFERENCES raw_entries(id),
            parsed_json TEXT NOT NULL,
            confidence  TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)
    
    # resolved_entries: individual food items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resolved_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            parsed_id   INTEGER NOT NULL REFERENCES parsed_entries(id),
            food_name   TEXT NOT NULL,
            calories    INTEGER,
            meal        TEXT,
            logged_date TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            fiber_g REAL,
            sugar_g REAL,
            sodium_mg REAL,
            potassium_mg REAL,
            cholesterol_mg REAL,
            saturated_fat_g REAL,
            trans_fat_g REAL,
            calcium_mg REAL,
            iron_mg REAL,
            vitamin_c_mg REAL,
            vitamin_d_iu REAL
        )
    """)

    # Ensure existing databases are upgraded with any missing nutrient columns.
    _ensure_resolved_entry_columns(cursor)
    _ensure_indexes(cursor)
    _backfill_resolved_entry_created_at(cursor)
    
    conn.commit()
    conn.close()


def insert_raw_entry(input_text: str) -> int:
    """
    Insert raw user input immediately. Returns the raw_id.
    This should always be the first operation.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    timestamp = datetime.now(UTC).isoformat()
    cursor.execute(
        "INSERT INTO raw_entries (timestamp, input_text) VALUES (?, ?)",
        (timestamp, input_text)
    )
    
    raw_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return raw_id


def insert_parsed_entry(raw_id: int, parsed_json: Dict[str, Any], confidence: str) -> int:
    """
    Insert parsed LLM output. Returns the parsed_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    created_at = datetime.now(UTC).isoformat()
    cursor.execute(
        "INSERT INTO parsed_entries (raw_id, parsed_json, confidence, created_at) VALUES (?, ?, ?, ?)",
        (raw_id, json.dumps(parsed_json), confidence, created_at)
    )
    
    parsed_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return parsed_id


def insert_resolved_entry(
    parsed_id: int,
    food_name: str,
    calories: Optional[int],
    meal: Optional[str],
    logged_date: str,
    protein_g: Optional[float] = None,
    carbs_g: Optional[float] = None,
    fat_g: Optional[float] = None,
    fiber_g: Optional[float] = None,
    sugar_g: Optional[float] = None,
    sodium_mg: Optional[float] = None,
    potassium_mg: Optional[float] = None,
    cholesterol_mg: Optional[float] = None,
    saturated_fat_g: Optional[float] = None,
    trans_fat_g: Optional[float] = None,
    calcium_mg: Optional[float] = None,
    iron_mg: Optional[float] = None,
    vitamin_c_mg: Optional[float] = None,
    vitamin_d_iu: Optional[float] = None,
    confidence_score: Optional[float] = None,
    confidence_level: Optional[str] = None,
    source: Optional[str] = None,
    assumptions: Optional[List[str]] = None,
    reasoning: Optional[str] = None,
    openai_response: Optional[str] = None,
) -> int:
    """
    Insert a single resolved food item. Returns the resolved_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    created_at = datetime.now(UTC).isoformat()
    
    cursor.execute(
        """INSERT INTO resolved_entries 
           (parsed_id, food_name, calories, meal, logged_date, created_at,
            protein_g, carbs_g, fat_g, fiber_g, sugar_g,
            sodium_mg, potassium_mg, cholesterol_mg,
            saturated_fat_g, trans_fat_g,
            calcium_mg, iron_mg, vitamin_c_mg, vitamin_d_iu,
            confidence_score, confidence_level, source, assumptions, reasoning, openai_response) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            parsed_id,
            food_name,
            calories,
            meal,
            logged_date,
            created_at,
            protein_g,
            carbs_g,
            fat_g,
            fiber_g,
            sugar_g,
            sodium_mg,
            potassium_mg,
            cholesterol_mg,
            saturated_fat_g,
            trans_fat_g,
            calcium_mg,
            iron_mg,
            vitamin_c_mg,
            vitamin_d_iu,
            confidence_score,
            confidence_level,
            source,
            json.dumps(assumptions) if assumptions else None,
            reasoning,
            openai_response,
        )
    )
    
    resolved_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return resolved_id


def get_entries_for_date(date: str) -> List[Dict[str, Any]]:
    """
    Get all resolved entries for a specific date (YYYY-MM-DD).
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT id, food_name, calories, meal, logged_date, created_at,
                  protein_g, carbs_g, fat_g, fiber_g, sugar_g,
                  sodium_mg, potassium_mg, cholesterol_mg,
                  saturated_fat_g, trans_fat_g,
                  calcium_mg, iron_mg, vitamin_c_mg, vitamin_d_iu,
                  confidence_score, confidence_level, source, assumptions
           FROM resolved_entries 
           WHERE logged_date = ?
           ORDER BY id DESC""",
        (date,)
    )
    
    rows = cursor.fetchall()
    conn.close()

    entries: List[Dict[str, Any]] = []
    for row in rows:
        entry = dict(row)
        assumptions = entry.get("assumptions")
        if isinstance(assumptions, str):
            try:
                parsed = json.loads(assumptions)
                entry["assumptions"] = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                entry["assumptions"] = []
        elif assumptions is None:
            entry["assumptions"] = []
        entries.append(entry)

    return entries


def get_summary_last_n_days(days: int = 7) -> List[Dict[str, Any]]:
    """
    Get total calories grouped by date for the last N days.
    Returns list of {date, total_calories, entry_count}.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT 
               logged_date as date,
               SUM(calories) as total_calories,
               COUNT(*) as entry_count
           FROM resolved_entries
           WHERE logged_date >= date('now', '-' || ? || ' days')
           GROUP BY logged_date
           ORDER BY logged_date DESC""",
        (days,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_summary_by_date_range(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Get total calories grouped by date for an inclusive date range.
    Returns list of {date, total_calories, entry_count}.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT
               logged_date as date,
               SUM(calories) as total_calories,
               COUNT(*) as entry_count
           FROM resolved_entries
           WHERE logged_date >= ? AND logged_date <= ?
           GROUP BY logged_date
           ORDER BY logged_date DESC""",
        (start_date, end_date)
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def delete_resolved_entry(entry_id: int) -> bool:
    """
    Delete a resolved entry by ID.
    Returns True if deleted, False if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "DELETE FROM resolved_entries WHERE id = ?",
        (entry_id,)
    )
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return deleted


def get_entry_trace(entry_id: int) -> Optional[Dict[str, Any]]:
    """
    Get trace details for a resolved entry:
    - raw input text (journal source)
    - parsed structured response
    - candidate responses considered during nutrition lookup
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT r.id as resolved_id, r.food_name, r.calories, r.meal, r.logged_date,
                  r.source as resolved_source, r.confidence_level,
                  p.id as parsed_id, p.parsed_json, p.confidence as parsed_confidence, p.created_at as parsed_created_at,
                  rw.id as raw_id, rw.input_text as raw_input_text, rw.timestamp as raw_timestamp
           FROM resolved_entries r
           JOIN parsed_entries p ON p.id = r.parsed_id
           JOIN raw_entries rw ON rw.id = p.raw_id
           WHERE r.id = ?""",
        (entry_id,)
    )

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    trace = dict(row)

    parsed_json_raw = trace.get("parsed_json")
    if isinstance(parsed_json_raw, str):
        try:
            trace["parsed_json"] = json.loads(parsed_json_raw)
        except json.JSONDecodeError:
            trace["parsed_json"] = parsed_json_raw

    parsed_id = trace["parsed_id"]
    cursor.execute(
        """SELECT intent_index, name, brand, serving, calories, protein_g, carbs_g, fat_g,
                  source, source_url, source_confidence, score
           FROM candidates
           WHERE parsed_id = ?
           ORDER BY intent_index ASC, score DESC""",
        (parsed_id,)
    )
    candidate_rows = cursor.fetchall()
    trace["candidates"] = [dict(r) for r in candidate_rows]

    conn.close()
    return trace


def get_recent_entries_by_meal(meal: str, date: str, hours_ago: int = 2) -> List[Dict[str, Any]]:
    """
    Get entries for a specific meal type on a given date.
    Useful for duplicate detection.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT id, food_name, calories, meal, logged_date 
           FROM resolved_entries 
           WHERE meal = ? AND logged_date = ?
           ORDER BY id DESC""",
        (meal, date)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def delete_entries_by_meal_and_date(meal: str, date: str) -> int:
    """
    Delete all entries for a specific meal type on a given date.
    Returns the number of entries deleted.
    Used when replacing duplicate meals.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "DELETE FROM resolved_entries WHERE meal = ? AND logged_date = ?",
        (meal, date)
    )
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted_count
