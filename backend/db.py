"""
Database Manager for NovaPharma Commercial Analytics Assistant.
Handles schema initialization, indexing, data loading, and secure query execution.
"""

import sqlite3
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Base paths
BASE_DIR = Path(__file__).parent.parent
# Look for schema files in project root schema/ or fallback paths
SCHEMA_DIR = BASE_DIR / "schema"
if not SCHEMA_DIR.exists():
    SCHEMA_DIR = BASE_DIR / "nl2sql-assignment-main" / "nl2sql-assignment-main" / "schema"

DB_PATH = BASE_DIR / "pharma.db"


def get_db_connection() -> sqlite3.Connection:
    """Create a configured SQLite database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode and performance pragmas
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_database(force_reseed: bool = False) -> None:
    """Initialize database tables, indices, and load seed/generated data if not present."""
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
        if create_tables_sql_path.exists():
            with open(create_tables_sql_path, "r", encoding="utf-8") as f:
                create_tables_sql = f.read()
            conn.executescript(create_tables_sql)
        else:
            from backend.domain_knowledge import SCHEMA_DDL
            # Use CREATE TABLE IF NOT EXISTS to prevent OperationalError on re-init
            ddl_if_not_exists = SCHEMA_DDL.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
            conn.executescript(ddl_if_not_exists)
        
        # Load seed data if available
        if seed_data_sql_path.exists():
            print("[DB] Loading seed_data.sql...")
            with open(seed_data_sql_path, "r", encoding="utf-8") as f:
                seed_data_sql = f.read()
            conn.executescript(seed_data_sql)
            
        # Check if users exist or re-seed valid user territory mapping
        cursor.execute("SELECT COUNT(*) FROM users;")
        user_count = cursor.fetchone()[0]
        if user_count < 10:
            print("[DB] Seeding comprehensive list of commercial users...")
            seed_users_sql = """
            INSERT OR IGNORE INTO users (user_id, email, full_name, role, territory_name, region_name, can_view_wac) VALUES
            -- Executives (Global)
            ('usr_exec_01', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
            ('usr_exec_02', 'robert.taylor@novapharma.com', 'Robert Taylor', 'exec', NULL, NULL, 1),
            
            -- Regional Directors (Region Scoped)
            ('usr_dir_ne', 'marcus.vance@novapharma.com', 'Marcus Vance', 'director', NULL, 'Northeast', 0),
            ('usr_dir_ma', 'elizabeth.stone@novapharma.com', 'Elizabeth Stone', 'director', NULL, 'Mid-Atlantic', 0),
            ('usr_dir_se', 'james.holloway@novapharma.com', 'James Holloway', 'director', NULL, 'Southeast', 0),
            ('usr_dir_mw', 'karen.brooks@novapharma.com', 'Karen Brooks', 'director', NULL, 'Midwest', 0),
            ('usr_dir_sc', 'thomas.wright@novapharma.com', 'Thomas Wright', 'director', NULL, 'South Central', 0),
            ('usr_dir_we', 'patricia.king@novapharma.com', 'Patricia King', 'director', NULL, 'West', 0),

            -- Regional Account Managers (RAMs) mapped to exact database territories
            ('usr_ram_nym', 'amy.nguyen@novapharma.com', 'Amy Nguyen', 'ram', 'New York Metro', 'Northeast', 0),
            ('usr_ram_ne', 'brian.kelly@novapharma.com', 'Brian Kelly', 'ram', 'New England', 'Northeast', 0),
            ('usr_ram_ma', 'carlos.rivera@novapharma.com', 'Carlos Rivera', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('usr_ram_se', 'rachel.adams@novapharma.com', 'Rachel Adams', 'ram', 'Southeast', 'Southeast', 0),
            ('usr_ram_gl', 'lisa.ray@novapharma.com', 'Lisa Ray', 'ram', 'Great Lakes', 'Midwest', 0),
            ('usr_ram_umw', 'ivan.petrov@novapharma.com', 'Ivan Petrov', 'ram', 'Upper Midwest', 'Midwest', 0),
            ('usr_ram_sc', 'david.miller@novapharma.com', 'David Miller', 'ram', 'South Central', 'South Central', 0),
            ('usr_ram_pac', 'kevin.zhang@novapharma.com', 'Kevin Zhang', 'ram', 'Pacific', 'West', 0),
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
        if user_count < 10:
            print("[DB] Seeding comprehensive list of commercial users into existing database...")
            seed_users_sql = """
            INSERT OR IGNORE INTO users (user_id, email, full_name, role, territory_name, region_name, can_view_wac) VALUES
            -- Executives (Global)
            ('usr_exec_01', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
            ('usr_exec_02', 'robert.taylor@novapharma.com', 'Robert Taylor', 'exec', NULL, NULL, 1),
            
            -- Regional Directors (Region Scoped)
            ('usr_dir_ne', 'marcus.vance@novapharma.com', 'Marcus Vance', 'director', NULL, 'Northeast', 0),
            ('usr_dir_ma', 'elizabeth.stone@novapharma.com', 'Elizabeth Stone', 'director', NULL, 'Mid-Atlantic', 0),
            ('usr_dir_se', 'james.holloway@novapharma.com', 'James Holloway', 'director', NULL, 'Southeast', 0),
            ('usr_dir_mw', 'karen.brooks@novapharma.com', 'Karen Brooks', 'director', NULL, 'Midwest', 0),
            ('usr_dir_sc', 'thomas.wright@novapharma.com', 'Thomas Wright', 'director', NULL, 'South Central', 0),
            ('usr_dir_we', 'patricia.king@novapharma.com', 'Patricia King', 'director', NULL, 'West', 0),

            -- Regional Account Managers (RAMs) mapped to exact database territories
            ('usr_ram_nym', 'amy.nguyen@novapharma.com', 'Amy Nguyen', 'ram', 'New York Metro', 'Northeast', 0),
            ('usr_ram_ne', 'brian.kelly@novapharma.com', 'Brian Kelly', 'ram', 'New England', 'Northeast', 0),
            ('usr_ram_ma', 'carlos.rivera@novapharma.com', 'Carlos Rivera', 'ram', 'Mid-Atlantic', 'Mid-Atlantic', 0),
            ('usr_ram_se', 'rachel.adams@novapharma.com', 'Rachel Adams', 'ram', 'Southeast', 'Southeast', 0),
            ('usr_ram_gl', 'lisa.ray@novapharma.com', 'Lisa Ray', 'ram', 'Great Lakes', 'Midwest', 0),
            ('usr_ram_umw', 'ivan.petrov@novapharma.com', 'Ivan Petrov', 'ram', 'Upper Midwest', 'Midwest', 0),
            ('usr_ram_sc', 'david.miller@novapharma.com', 'David Miller', 'ram', 'South Central', 'South Central', 0),
            ('usr_ram_pac', 'kevin.zhang@novapharma.com', 'Kevin Zhang', 'ram', 'Pacific', 'West', 0),
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


def get_user_by_id_or_email(identifier: str) -> Dict[str, Any]:
    """Retrieve user details for role-based scoping (supports both usr_ and U001 legacy aliases)."""
    # Legacy test ID mapping
    legacy_map = {
        "U001": "usr_exec_01",
        "U002": "usr_exec_02",
        "U003": "usr_dir_ne",
        "U004": "usr_dir_ma",
        "U005": "usr_dir_se",
        "U006": "usr_dir_mw",
        "U007": "usr_dir_sc",
        "U008": "usr_dir_we",
        "U009": "usr_ram_nym",
        "U010": "usr_ram_ne",
        "U011": "usr_ram_ma",
        "U012": "usr_ram_se",
        "U013": "usr_ram_gl",
        "U014": "usr_ram_umw",
        "U015": "usr_ram_sc",
        "U016": "usr_ram_pac",
        "U017": "usr_ram_mtn",
        "sarah.chen@novapharma.com": "usr_exec_01",
        "jennifer.walsh@novapharma.com": "usr_dir_ne",
        "amy.nguyen@novapharma.com": "usr_ram_nym",
    }
    lookup_id = legacy_map.get(identifier, identifier)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, email, full_name, role, territory_name, region_name, can_view_wac FROM users WHERE user_id = ? OR email = ? LIMIT 1;",
        (lookup_id, identifier)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
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


def auto_name_session(first_user_message: str) -> str:
    """Generate a short session name from the user's first message (truncated to 40 chars)."""
    name = first_user_message.strip()
    return name[:40] + "…" if len(name) > 40 else name

