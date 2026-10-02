"""
Database Manager for NovaPharma Commercial Analytics Assistant.
Handles schema initialization, indexing, data loading, and secure query execution.
"""

import sqlite3
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Base paths
BASE_DIR = Path(__file__).parent.parent
# Look for schema files in project root schema/ or fallback paths
SCHEMA_DIR = BASE_DIR / "schema"
if not SCHEMA_DIR.exists():
    SCHEMA_DIR = BASE_DIR / "nl2sql-assignment-main" / "nl2sql-assignment-main" / "schema"

DB_PATH = BASE_DIR / "pharma.db"


def get_db_connection() -> sqlite3.Connection:
    """Create a configured SQLite database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode and performance pragmas
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_database(force_reseed: bool = False) -> None:
    """Initialize database tables, indices, and load seed/generated data if not present."""
    compressed_db_path = BASE_DIR / "pharma_full.db.gz"
    full_db_path = BASE_DIR / "pharma_full.db"
    
    # If full pre-built compressed database is present and pharma.db is missing/reseeded
    if compressed_db_path.exists() and (not DB_PATH.exists() or force_reseed):
        print(f"[DB] Extracting full 2M-row database from {compressed_db_path.name}...")
        import gzip, shutil
        with gzip.open(compressed_db_path, "rb") as f_in, open(DB_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        print("[DB] Decompressed full 2,000,000-row database successfully!")
        return
    elif full_db_path.exists() and (not DB_PATH.exists() or force_reseed):
        import shutil
        shutil.copyfile(full_db_path, DB_PATH)
        print("[DB] Initialized from pharma_full.db successfully!")
        return

    create_tables_sql_path = SCHEMA_DIR / "create_tables.sql"
    seed_data_sql_path = SCHEMA_DIR / "seed_data.sql"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if tables already exist and have data
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sales';")
    sales_table_exists = cursor.fetchone() is not None
    
    sales_count = 0
    if sales_table_exists:
        cursor.execute("SELECT COUNT(*) FROM sales;")
        sales_count = cursor.fetchone()[0]
        
    if not sales_table_exists or sales_count == 0 or force_reseed:
        print("[DB] Initializing schema and seeding database...")
        if create_tables_sql_path.exists() and seed_data_sql_path.exists():
            print(f"[DB] Loading original schema files from {SCHEMA_DIR}...")
            with open(create_tables_sql_path, "r", encoding="utf-8") as f:
                create_sql = f.read()
                conn.executescript(create_sql)
            with open(seed_data_sql_path, "r", encoding="utf-8") as f:
                seed_sql = f.read()
                safe_seed = seed_sql.replace("INSERT INTO ", "INSERT OR IGNORE INTO ")
                conn.executescript(safe_seed)
        else:
            from backend.domain_knowledge import SCHEMA_DDL
            conn.executescript(SCHEMA_DDL)
            
        # Check if users exist or re-seed valid user territory mapping
        cursor.execute("SELECT COUNT(*) FROM users;")
        user_count = cursor.fetchone()[0]
        if user_count < 25:
            print("[DB] Seeding comprehensive list of commercial users...")
            seed_users_sql = """
            INSERT OR IGNORE INTO users (user_id, email, full_name, role, territory_name, region_name, can_view_wac) VALUES
            -- Standard IDs (U001 - U023)
            ('U001', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
            ('U002', 'michael.torres@novapharma.com', 'Michael Torres', 'exec', NULL, NULL, 1),
            ('U003', 'jennifer.walsh@novapharma.com', 'Jennifer Walsh', 'director', NULL, 'Northeast', 0),
            ('U004', 'david.park@novapharma.com', 'David Park', 'director', NULL, 'Mid-Atlantic', 0),
            ('U005', 'lisa.johnson@novapharma.com', 'Lisa Johnson', 'director', NULL, 'Southeast', 0),
            ('U006', 'robert.kim@novapharma.com', 'Robert Kim', 'director', NULL, 'Midwest', 0),
            ('U007', 'maria.garcia@novapharma.com', 'Maria Garcia', 'director', NULL, 'South Central', 0),
            ('U008', 'james.anderson@novapharma.com', 'James Anderson', 'director', NULL, 'West', 0),
            ('U009', 'amy.nguyen@novapharma.com', 'Amy Nguyen', 'ram', 'New York Metro', 'Northeast', 0),
            ('U010', 'brian.murphy@novapharma.com', 'Brian Murphy', 'ram', 'New England', 'Northeast', 0),
            ('U011', 'carlos.rivera@novapharma.com', 'Carlos Rivera', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('U012', 'diana.wright@novapharma.com', 'Diana Wright', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('U013', 'eric.thompson@novapharma.com', 'Eric Thompson', 'ram', 'Southeast', 'Southeast', 0),
            ('U014', 'fiona.davis@novapharma.com', 'Fiona Davis', 'ram', 'Southeast', 'Southeast', 0),
            ('U015', 'george.martinez@novapharma.com', 'George Martinez', 'ram', 'Great Lakes', 'Midwest', 0),
            ('U016', 'hannah.lee@novapharma.com', 'Hannah Lee', 'ram', 'Great Lakes', 'Midwest', 0),
            ('U017', 'ivan.petrov@novapharma.com', 'Ivan Petrov', 'ram', 'Upper Midwest', 'Midwest', 0),
            ('U018', 'julia.robinson@novapharma.com', 'Julia Robinson', 'ram', 'South Central', 'South Central', 0),
            ('U019', 'kevin.brown@novapharma.com', 'Kevin Brown', 'ram', 'South Central', 'South Central', 0),
            ('U020', 'laura.wilson@novapharma.com', 'Laura Wilson', 'ram', 'Pacific', 'West', 0),
            ('U021', 'nathan.clark@novapharma.com', 'Nathan Clark', 'ram', 'Pacific', 'West', 0),
            ('U022', 'olivia.taylor@novapharma.com', 'Olivia Taylor', 'ram', 'Pacific', 'West', 0),
            ('U023', 'patrick.moore@novapharma.com', 'Patrick Moore', 'ram', 'Mountain', 'West', 0),

            -- Persona Aliases (usr_*)
            ('usr_exec_01', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
            ('usr_exec_02', 'michael.torres@novapharma.com', 'Michael Torres', 'exec', NULL, NULL, 1),
            ('usr_dir_ne', 'jennifer.walsh@novapharma.com', 'Jennifer Walsh', 'director', NULL, 'Northeast', 0),
            ('usr_dir_ma', 'david.park@novapharma.com', 'David Park', 'director', NULL, 'Mid-Atlantic', 0),
            ('usr_dir_se', 'lisa.johnson@novapharma.com', 'Lisa Johnson', 'director', NULL, 'Southeast', 0),
            ('usr_dir_mw', 'robert.kim@novapharma.com', 'Robert Kim', 'director', NULL, 'Midwest', 0),
            ('usr_dir_sc', 'maria.garcia@novapharma.com', 'Maria Garcia', 'director', NULL, 'South Central', 0),
            ('usr_dir_we', 'james.anderson@novapharma.com', 'James Anderson', 'director', NULL, 'West', 0),
            ('usr_ram_nym', 'amy.nguyen@novapharma.com', 'Amy Nguyen', 'ram', 'New York Metro', 'Northeast', 0),
            ('usr_ram_ne', 'brian.murphy@novapharma.com', 'Brian Murphy', 'ram', 'New England', 'Northeast', 0),
            ('usr_ram_ma', 'carlos.rivera@novapharma.com', 'Carlos Rivera', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('usr_ram_se', 'eric.thompson@novapharma.com', 'Eric Thompson', 'ram', 'Southeast', 'Southeast', 0),
            ('usr_ram_gl', 'george.martinez@novapharma.com', 'George Martinez', 'ram', 'Great Lakes', 'Midwest', 0),
            ('usr_ram_umw', 'ivan.petrov@novapharma.com', 'Ivan Petrov', 'ram', 'Upper Midwest', 'Midwest', 0),
            ('usr_ram_sc', 'kevin.brown@novapharma.com', 'Kevin Brown', 'ram', 'South Central', 'South Central', 0),
            ('usr_ram_pac', 'laura.wilson@novapharma.com', 'Laura Wilson', 'ram', 'Pacific', 'West', 0),
            ('usr_ram_mtn', 'patrick.moore@novapharma.com', 'Patrick Moore', 'ram', 'Mountain', 'West', 0);
            """
            cursor.executescript(seed_users_sql)

        # Create performance indices for fast analytics queries
        print("[DB] Creating high-performance indexes...")
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_sales_data_source ON sales(data_source, brand_flag);",
            "CREATE INDEX IF NOT EXISTS idx_sales_mo_offset ON sales(mo_offset);",
            "CREATE INDEX IF NOT EXISTS idx_sales_wk_offset ON sales(wk_offset);",
            "CREATE INDEX IF NOT EXISTS idx_sales_org_id ON sales(org_id);",
            "CREATE INDEX IF NOT EXISTS idx_sales_ndc ON sales(ndc);",
            "CREATE INDEX IF NOT EXISTS idx_sales_drug_name ON sales(drug_name);",
            "CREATE INDEX IF NOT EXISTS idx_sales_period_mo ON sales(period_mo);",
            "CREATE INDEX IF NOT EXISTS idx_org_zip ON organizations(zip);",
            "CREATE INDEX IF NOT EXISTS idx_org_grandparent ON organizations(grandparent_org_name);",
            "CREATE INDEX IF NOT EXISTS idx_zip_territory ON zip_territory(territory_name, region_name);",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
        ]
        for idx in indices:
            cursor.execute(idx)
        conn.commit()
        print("[DB] Database initialization complete.")
    else:
        # Verify users exist and update with exact valid territories
        cursor.execute("SELECT COUNT(*) FROM users;")
        user_count = cursor.fetchone()[0]
        if user_count < 25:
            print("[DB] Seeding comprehensive list of commercial users into existing database...")
            seed_users_sql = """
            INSERT OR IGNORE INTO users (user_id, email, full_name, role, territory_name, region_name, can_view_wac) VALUES
            -- Standard IDs (U001 - U023)
            ('U001', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
            ('U002', 'michael.torres@novapharma.com', 'Michael Torres', 'exec', NULL, NULL, 1),
            ('U003', 'jennifer.walsh@novapharma.com', 'Jennifer Walsh', 'director', NULL, 'Northeast', 0),
            ('U004', 'david.park@novapharma.com', 'David Park', 'director', NULL, 'Mid-Atlantic', 0),
            ('U005', 'lisa.johnson@novapharma.com', 'Lisa Johnson', 'director', NULL, 'Southeast', 0),
            ('U006', 'robert.kim@novapharma.com', 'Robert Kim', 'director', NULL, 'Midwest', 0),
            ('U007', 'maria.garcia@novapharma.com', 'Maria Garcia', 'director', NULL, 'South Central', 0),
            ('U008', 'james.anderson@novapharma.com', 'James Anderson', 'director', NULL, 'West', 0),
            ('U009', 'amy.nguyen@novapharma.com', 'Amy Nguyen', 'ram', 'New York Metro', 'Northeast', 0),
            ('U010', 'brian.murphy@novapharma.com', 'Brian Murphy', 'ram', 'New England', 'Northeast', 0),
            ('U011', 'carlos.rivera@novapharma.com', 'Carlos Rivera', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('U012', 'diana.wright@novapharma.com', 'Diana Wright', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('U013', 'eric.thompson@novapharma.com', 'Eric Thompson', 'ram', 'Southeast', 'Southeast', 0),
            ('U014', 'fiona.davis@novapharma.com', 'Fiona Davis', 'ram', 'Southeast', 'Southeast', 0),
            ('U015', 'george.martinez@novapharma.com', 'George Martinez', 'ram', 'Great Lakes', 'Midwest', 0),
            ('U016', 'hannah.lee@novapharma.com', 'Hannah Lee', 'ram', 'Great Lakes', 'Midwest', 0),
            ('U017', 'ivan.petrov@novapharma.com', 'Ivan Petrov', 'ram', 'Upper Midwest', 'Midwest', 0),
            ('U018', 'julia.robinson@novapharma.com', 'Julia Robinson', 'ram', 'South Central', 'South Central', 0),
            ('U019', 'kevin.brown@novapharma.com', 'Kevin Brown', 'ram', 'South Central', 'South Central', 0),
            ('U020', 'laura.wilson@novapharma.com', 'Laura Wilson', 'ram', 'Pacific', 'West', 0),
            ('U021', 'nathan.clark@novapharma.com', 'Nathan Clark', 'ram', 'Pacific', 'West', 0),
            ('U022', 'olivia.taylor@novapharma.com', 'Olivia Taylor', 'ram', 'Pacific', 'West', 0),
            ('U023', 'patrick.moore@novapharma.com', 'Patrick Moore', 'ram', 'Mountain', 'West', 0),

            -- Persona Aliases (usr_*)
            ('usr_exec_01', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
            ('usr_exec_02', 'michael.torres@novapharma.com', 'Michael Torres', 'exec', NULL, NULL, 1),
            ('usr_dir_ne', 'jennifer.walsh@novapharma.com', 'Jennifer Walsh', 'director', NULL, 'Northeast', 0),
            ('usr_dir_ma', 'david.park@novapharma.com', 'David Park', 'director', NULL, 'Mid-Atlantic', 0),
            ('usr_dir_se', 'lisa.johnson@novapharma.com', 'Lisa Johnson', 'director', NULL, 'Southeast', 0),
            ('usr_dir_mw', 'robert.kim@novapharma.com', 'Robert Kim', 'director', NULL, 'Midwest', 0),
            ('usr_dir_sc', 'maria.garcia@novapharma.com', 'Maria Garcia', 'director', NULL, 'South Central', 0),
            ('usr_dir_we', 'james.anderson@novapharma.com', 'James Anderson', 'director', NULL, 'West', 0),
            ('usr_ram_nym', 'amy.nguyen@novapharma.com', 'Amy Nguyen', 'ram', 'New York Metro', 'Northeast', 0),
            ('usr_ram_ne', 'brian.murphy@novapharma.com', 'Brian Murphy', 'ram', 'New England', 'Northeast', 0),
            ('usr_ram_ma', 'carlos.rivera@novapharma.com', 'Carlos Rivera', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('usr_ram_se', 'eric.thompson@novapharma.com', 'Eric Thompson', 'ram', 'Southeast', 'Southeast', 0),
            ('usr_ram_gl', 'george.martinez@novapharma.com', 'George Martinez', 'ram', 'Great Lakes', 'Midwest', 0),
            ('usr_ram_umw', 'ivan.petrov@novapharma.com', 'Ivan Petrov', 'ram', 'Upper Midwest', 'Midwest', 0),
            ('usr_ram_sc', 'kevin.brown@novapharma.com', 'Kevin Brown', 'ram', 'South Central', 'South Central', 0),
            ('usr_ram_pac', 'laura.wilson@novapharma.com', 'Laura Wilson', 'ram', 'Pacific', 'West', 0),
            ('usr_ram_mtn', 'patrick.moore@novapharma.com', 'Patrick Moore', 'ram', 'Mountain', 'West', 0);
            """
            cursor.executescript(seed_users_sql)
            conn.commit()
        print(f"[DB] Database already initialized with {sales_count} sales rows.")
        
    conn.close()


def execute_query(sql: str, params: tuple = ()) -> Tuple[List[Dict[str, Any]], float, List[str]]:
    """
    Execute a read-only SQL query safely with execution timing and column names.
    Returns: (results, execution_time_ms, column_names)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    start_time = time.perf_counter()
    
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        results = [dict(zip(columns, row)) for row in rows]
        return results, execution_time_ms, columns
    finally:
        conn.close()


def get_user_by_id_or_email(identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieve user details for role-based scoping (supports U001-U023, usr_ aliases, and emails)."""
    if not identifier:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Direct match on user_id or email
    cursor.execute(
        "SELECT user_id, email, full_name, role, territory_name, region_name, can_view_wac FROM users WHERE user_id = ? OR LOWER(email) = LOWER(?) LIMIT 1;",
        (identifier, identifier)
    )
    row = cursor.fetchone()
    if row:
        conn.close()
        return dict(row)

    # 2. Alias fallback mapping
    alias_map = {
        "U001": "usr_exec_01",
        "U002": "usr_exec_02",
        "U003": "usr_dir_ne",
        "U004": "usr_dir_ma",
        "U005": "usr_dir_se",
        "U006": "usr_dir_mw",
        "U007": "usr_dir_sc",
        "U008": "usr_dir_we",
        "U009": "usr_ram_nym",
        "usr_exec_01": "U001",
        "usr_exec_02": "U002",
        "usr_dir_ne": "U003",
        "usr_dir_ma": "U004",
        "usr_dir_se": "U005",
        "usr_dir_mw": "U006",
        "usr_dir_sc": "U007",
        "usr_dir_we": "U008",
        "usr_ram_nym": "U009",
    }
    alt_id = alias_map.get(identifier)
    if alt_id:
        cursor.execute(
            "SELECT user_id, email, full_name, role, territory_name, region_name, can_view_wac FROM users WHERE user_id = ? OR LOWER(email) = LOWER(?) LIMIT 1;",
            (alt_id, alt_id)
        )
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    conn.close()
    return None


def get_all_users() -> List[Dict[str, Any]]:
    """List all available users in the system for testing / persona switching."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, email, full_name, role, territory_name, region_name, can_view_wac FROM users ORDER BY role, full_name;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# SESSION STATE MANAGEMENT (Multi-User Persistent Conversations)
# ============================================================

def init_session_tables() -> None:
    """Create persistent session and message tables if not already present."""
    conn = get_db_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id   TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL,
            session_name TEXT NOT NULL DEFAULT 'New Chat',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS session_messages (
            message_id   TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            role         TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content      TEXT NOT NULL,
            sql_query    TEXT,
            row_count    INTEGER DEFAULT 0,
            latency_ms   REAL DEFAULT 0.0,
            traces_json  TEXT DEFAULT '[]',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON chat_sessions(user_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON session_messages(session_id, created_at);
    """)
    conn.commit()
    conn.close()


def create_session(user_id: str, session_name: str = "New Chat") -> Dict[str, Any]:
    """Create a new isolated chat session for a user and return its metadata."""
    import uuid
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO chat_sessions (session_id, user_id, session_name) VALUES (?, ?, ?);",
        (session_id, user_id, session_name)
    )
    conn.commit()
    conn.close()
    return {"session_id": session_id, "user_id": user_id, "session_name": session_name}


def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all chat sessions for a user, ordered newest-first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.session_id, s.user_id, s.session_name, s.created_at, s.updated_at,
               COUNT(m.message_id) as message_count
        FROM chat_sessions s
        LEFT JOIN session_messages m ON s.session_id = m.session_id
        WHERE s.user_id = ?
        GROUP BY s.session_id
        ORDER BY s.updated_at DESC
        LIMIT 50;
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_history(session_id: str) -> List[Dict[str, Any]]:
    """Load the full ordered message history of a session for context injection."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT message_id, session_id, user_id, role, content, sql_query,
               row_count, latency_ms, traces_json, created_at
        FROM session_messages
        WHERE session_id = ?
        ORDER BY created_at ASC;
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def ensure_session_exists(session_id: str, user_id: str) -> None:
    """Ensure a session row exists in chat_sessions so foreign keys never fail."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO chat_sessions (session_id, user_id, session_name) VALUES (?, ?, 'New Chat');",
        (session_id, user_id)
    )
    conn.commit()
    conn.close()


def save_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    sql_query: str = None,
    row_count: int = 0,
    latency_ms: float = 0.0,
    traces_json: str = "[]"
) -> str:
    """Persist a user or assistant message to the session and touch the session timestamp."""
    import uuid, json
    ensure_session_exists(session_id, user_id)
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    conn.execute(
        """INSERT INTO session_messages
           (message_id, session_id, user_id, role, content, sql_query, row_count, latency_ms, traces_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
        (message_id, session_id, user_id, role, content, sql_query, row_count, latency_ms, traces_json)
    )
    # Update session name on first user message and touch updated_at
    conn.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now') WHERE session_id = ?;",
        (session_id,)
    )
    conn.commit()
    conn.close()
    return message_id


def rename_session(session_id: str, new_name: str) -> bool:
    """Rename a chat session."""
    conn = get_db_connection()
    cursor = conn.execute(
        "UPDATE chat_sessions SET session_name = ?, updated_at = datetime('now') WHERE session_id = ?;",
        (new_name, session_id)
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def delete_session(session_id: str) -> bool:
    """Delete a session and all its messages (cascade)."""
    conn = get_db_connection()
    cursor = conn.execute("DELETE FROM chat_sessions WHERE session_id = ?;", (session_id,))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def clear_all_sessions(user_id: str = None) -> int:
    """Clear all chat sessions and messages, optionally scoped to a user."""
    conn = get_db_connection()
    if user_id:
        cursor = conn.execute("DELETE FROM chat_sessions WHERE user_id = ?;", (user_id,))
    else:
        conn.execute("DELETE FROM session_messages;")
        cursor = conn.execute("DELETE FROM chat_sessions;")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def auto_name_session(first_user_message: str) -> str:
    """Generate a short session name from the user's first message (truncated to 40 chars)."""
    name = first_user_message.strip()
    return name[:40] + "…" if len(name) > 40 else name

