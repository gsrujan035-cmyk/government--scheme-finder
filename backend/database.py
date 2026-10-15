"""
Database module for Government Scheme Finder.
Manages SQLite connection, table schema creation, data seeding, and safe parameterized queries.
"""
import sqlite3
import json
import os
from .config import Config
from .seed_data import INITIAL_SCHEMES


def get_db_connection():
    """
    Establish a thread-safe connection to the SQLite database.
    Enables Row factory for dictionary-like column access.
    """
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Initialize SQLite database tables and seed initial records if empty.
    """
    db_dir = os.path.dirname(Config.DATABASE_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create schemes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schemes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                acronym TEXT NOT NULL,
                department TEXT NOT NULL,
                category TEXT NOT NULL,
                scope TEXT NOT NULL,
                benefit TEXT NOT NULL,
                benefit_value INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL,
                min_age INTEGER NOT NULL DEFAULT 0,
                max_age INTEGER NOT NULL DEFAULT 100,
                gender TEXT NOT NULL DEFAULT 'all',
                income_max INTEGER NOT NULL DEFAULT 10000000,
                occupations TEXT NOT NULL DEFAULT '["all"]',
                states TEXT NOT NULL DEFAULT '["all"]',
                requires_land INTEGER NOT NULL DEFAULT 0,
                requires_girl_child INTEGER NOT NULL DEFAULT 0,
                requires_bpl INTEGER NOT NULL DEFAULT 0,
                criteria_summary TEXT,
                documents TEXT NOT NULL DEFAULT '[]',
                application_steps TEXT NOT NULL DEFAULT '[]',
                official_url TEXT NOT NULL,
                verification_status TEXT NOT NULL,
                source_dept TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check existing count
        cursor.execute("SELECT COUNT(*) FROM schemes")
        count = cursor.fetchone()[0]

        if count == 0:
            print("[Database] Seeding authentic government scheme records into SQLite...")
            for s in INITIAL_SCHEMES:
                cursor.execute("""
                    INSERT INTO schemes (
                        id, title, acronym, department, category, scope, benefit, benefit_value,
                        description, min_age, max_age, gender, income_max, occupations, states,
                        requires_land, requires_girl_child, requires_bpl, criteria_summary,
                        documents, application_steps, official_url, verification_status, source_dept
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    s["id"],
                    s["title"],
                    s["acronym"],
                    s["department"],
                    s["category"],
                    s["scope"],
                    s["benefit"],
                    s["benefit_value"],
                    s["description"],
                    s["min_age"],
                    s["max_age"],
                    s["gender"],
                    s["income_max"],
                    json.dumps(s["occupations"]),
                    json.dumps(s["states"]),
                    s["requires_land"],
                    s["requires_girl_child"],
                    s["requires_bpl"],
                    s["criteria_summary"],
                    json.dumps(s["documents"]),
                    json.dumps(s["application_steps"]),
                    s["official_url"],
                    s["verification_status"],
                    s["source_dept"]
                ))
            conn.commit()
            print(f"[Database] Successfully seeded {len(INITIAL_SCHEMES)} schemes.")
        else:
            print(f"[Database] Database already initialized with {count} scheme records.")


def row_to_dict(row):
    """
    Convert a sqlite3.Row object to a clean Python dictionary,
    safely parsing JSON strings back into Python arrays/objects.
    """
    if not row:
        return None
    d = dict(row)
    try:
        d["occupations"] = json.loads(d["occupations"])
    except (TypeError, json.JSONDecodeError):
        d["occupations"] = []

    try:
        d["states"] = json.loads(d["states"])
    except (TypeError, json.JSONDecodeError):
        d["states"] = []

    try:
        d["documents"] = json.loads(d["documents"])
    except (TypeError, json.JSONDecodeError):
        d["documents"] = []

    try:
        d["application_steps"] = json.loads(d["application_steps"])
    except (TypeError, json.JSONDecodeError):
        d["application_steps"] = []

    # Format criteria sub-object for frontend compatibility
    d["criteria"] = {
        "minAge": d["min_age"],
        "maxAge": d["max_age"],
        "gender": d["gender"],
        "incomeMax": d["income_max"],
        "occupations": d["occupations"],
        "states": d["states"],
        "requiresLand": bool(d["requires_land"]),
        "requiresGirlChild": bool(d["requires_girl_child"]),
        "requiresBpl": bool(d["requires_bpl"]),
        "summary": d["criteria_summary"]
    }
    
    # CamelCase aliases for seamless frontend compatibility
    d["benefitValue"] = d["benefit_value"]
    d["officialUrl"] = d["official_url"]
    d["verificationStatus"] = d["verification_status"]
    d["sourceDept"] = d["source_dept"]

    return d


def query_schemes(category=None, state=None, search=None, sort=None):
    """
    Safely query schemes with optional filters and parameterized SQL.
    """
    query = "SELECT * FROM schemes WHERE 1=1"
    params = []

    if category and category.lower() != 'all':
        query += " AND LOWER(category) = ?"
        params.append(category.lower())

    if search:
        search_term = f"%{search.strip().lower()}%"
        query += """ AND (
            LOWER(title) LIKE ? OR
            LOWER(acronym) LIKE ? OR
            LOWER(department) LIKE ? OR
            LOWER(benefit) LIKE ? OR
            LOWER(description) LIKE ?
        )"""
        params.extend([search_term] * 5)

    if sort == 'amount':
        query += " ORDER BY benefit_value DESC"
    elif sort == 'name':
        query += " ORDER BY title ASC"
    else:
        query += " ORDER BY id ASC"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for r in rows:
            scheme = row_to_dict(r)
            # Filter state if state filter is specified
            if state and state.lower() != 'all':
                scope_states = [s.lower() for s in scheme["states"]]
                if 'all' not in scope_states and state.lower() not in scope_states:
                    continue
            results.append(scheme)
        return results


def query_scheme_by_id(scheme_id):
    """
    Retrieve single scheme by primary key ID.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schemes WHERE id = ?", (scheme_id,))
        row = cursor.fetchone()
        return row_to_dict(row)
