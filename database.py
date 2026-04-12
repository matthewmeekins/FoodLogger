"""
Database module for food logging system.
Handles SQLite connection and all database operations.
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
import json

from nutrition.models import NutritionCandidate


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
    ("confidence_score", "REAL"),
    ("confidence_level", "TEXT"),
    ("source", "TEXT"),
    ("assumptions", "TEXT"),  # json
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

    # candidates: nutrition lookup results for explainability
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            parsed_id         INTEGER NOT NULL REFERENCES parsed_entries(id),
            intent_index      INTEGER NOT NULL,
            name              TEXT NOT NULL,
            brand             TEXT,
            serving           TEXT,
            calories          REAL,
            protein_g         REAL,
            carbs_g           REAL,
            fat_g             REAL,
            source            TEXT NOT NULL,
            source_url        TEXT,
            source_confidence REAL,
            provider_item_id  TEXT,
            extra_nutrients   TEXT,
            score             REAL
        )
    """)

    # pending_entries: entries waiting for clarification
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_entries (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            parsed_id         INTEGER NOT NULL REFERENCES parsed_entries(id),
            intent_index      INTEGER NOT NULL,
            input_text        TEXT NOT NULL,
            food_name         TEXT NOT NULL,
            brand             TEXT,
            modifiers         TEXT,  -- json list
            quantity          TEXT,
            meal              TEXT,
            logged_date       TEXT NOT NULL,
            confidence_score  REAL,
            confidence_level  TEXT,
            source            TEXT,
            assumptions       TEXT,  -- json list
            question          TEXT,
            created_at        TEXT NOT NULL
        )
    """)

    # Ensure existing databases are upgraded with any missing nutrient columns.
    _ensure_resolved_entry_columns(cursor)
    
    conn.commit()
    conn.close()


def insert_raw_entry(input_text: str) -> int:
    """
    Insert raw user input immediately. Returns the raw_id.
    This should always be the first operation.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    timestamp = datetime.utcnow().isoformat()
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
    
    created_at = datetime.utcnow().isoformat()
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
) -> int:
    """
    Insert a single resolved food item. Returns the resolved_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """INSERT INTO resolved_entries 
           (parsed_id, food_name, calories, meal, logged_date,
            protein_g, carbs_g, fat_g, fiber_g, sugar_g,
            sodium_mg, potassium_mg, cholesterol_mg,
            saturated_fat_g, trans_fat_g,
            calcium_mg, iron_mg, vitamin_c_mg, vitamin_d_iu,
            confidence_score, confidence_level, source, assumptions) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            parsed_id,
            food_name,
            calories,
            meal,
            logged_date,
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
        )
    )
    
    resolved_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return resolved_id


def insert_pending_entry(
    parsed_id: int,
    intent_index: int,
    input_text: str,
    food_name: str,
    brand: Optional[str],
    modifiers: List[str],
    quantity: Optional[str],
    meal: Optional[str],
    logged_date: str,
    confidence_score: float,
    confidence_level: str,
    source: str,
    assumptions: List[str],
    question: str,
) -> int:
    """
    Insert a pending entry that needs clarification. Returns the pending_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    created_at = datetime.utcnow().isoformat()
    cursor.execute(
        """INSERT INTO pending_entries 
           (parsed_id, intent_index, food_name, brand, modifiers, quantity, meal, logged_date,
            confidence_score, confidence_level, source, assumptions, question, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            parsed_id,
            intent_index,
            food_name,
            brand,
            json.dumps(modifiers),
            quantity,
            meal,
            logged_date,
            confidence_score,
            confidence_level,
            source,
            json.dumps(assumptions),
            question,
            created_at,
        )
    )
    
    pending_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return pending_id


def get_pending_entry(pending_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a pending entry by ID.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT id, parsed_id, intent_index, input_text, food_name, brand, modifiers, quantity, meal, logged_date,
                  confidence_score, confidence_level, source, assumptions, question, created_at
           FROM pending_entries 
           WHERE id = ?""",
        (pending_id,)
    )
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def delete_pending_entry(pending_id: int) -> None:
    """
    Delete a pending entry after resolving it.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM pending_entries WHERE id = ?", (pending_id,))
    
    conn.commit()
    conn.close()


def insert_candidates(parsed_id: int, intent_index: int, candidates: List[NutritionCandidate], scores: List[float]) -> None:
    """
    Insert nutrition candidates for a specific intent.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    for candidate, score in zip(candidates, scores):
        cursor.execute(
            """INSERT INTO candidates 
               (parsed_id, intent_index, name, brand, serving, calories, protein_g, carbs_g, fat_g,
                source, source_url, source_confidence, provider_item_id, extra_nutrients, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                parsed_id,
                intent_index,
                candidate.name,
                candidate.brand,
                candidate.serving,
                candidate.calories,
                candidate.protein_g,
                candidate.carbs_g,
                candidate.fat_g,
                candidate.source,
                candidate.source_url,
                candidate.source_confidence,
                candidate.provider_item_id,
                json.dumps(candidate.extra_nutrients),
                score,
            )
        )
    
    conn.commit()
    conn.close()


def get_entries_for_date(date: str) -> List[Dict[str, Any]]:
    """
    Get all resolved entries for a specific date (YYYY-MM-DD).
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT id, food_name, calories, meal, logged_date,
                  protein_g, carbs_g, fat_g, fiber_g, sugar_g,
                  sodium_mg, potassium_mg, cholesterol_mg,
                  saturated_fat_g, trans_fat_g,
                  calcium_mg, iron_mg, vitamin_c_mg, vitamin_d_iu
           FROM resolved_entries 
           WHERE logged_date = ?
           ORDER BY id""",
        (date,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


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
