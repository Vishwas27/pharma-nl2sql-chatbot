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
ASSIGNMENT_DIR = BASE_DIR / "nl2sql-assignment-main" / "nl2sql-assignment-main"
SCHEMA_DIR = ASSIGNMENT_DIR / "schema"
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
    
    if not create_tables_sql_path.exists():
        raise FileNotFoundError(f"Cannot find create_tables.sql at {create_tables_sql_path}")
    
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
        with open(create_tables_sql_path, "r", encoding="utf-8") as f:
            create_tables_sql = f.read()
        conn.executescript(create_tables_sql)
        
        # Load seed data
        if seed_data_sql_path.exists():
            print("[DB] Loading seed_data.sql...")
            with open(seed_data_sql_path, "r", encoding="utf-8") as f:
                seed_data_sql = f.read()
            conn.executescript(seed_data_sql)
            
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
    """Retrieve user details for role-based scoping."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, email, full_name, role, territory_name, region_name, can_view_wac FROM users WHERE user_id = ? OR email = ? LIMIT 1;",
        (identifier, identifier)
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
