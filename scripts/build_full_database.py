"""
High-Performance SQLite Full Dataset Builder.
Generates 2,000,000 sales records and 40,000 organizations into an indexed SQLite database,
then compresses it with gzip into pharma_full.db.gz for lightning-fast deployment.
"""

import os
import sys
import time
import gzip
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from schema.generate_data import (
    generate_organizations,
    generate_zip_territories,
    generate_sales,
    ALL_PRODUCTS,
    ORG_FIELDS,
    PRODUCT_FIELDS,
    ZIP_FIELDS,
    SALES_FIELDS,
    NUM_SALES,
)
from backend.domain_knowledge import SCHEMA_DDL


def build_database(target_db_path: Path, num_sales: int = NUM_SALES):
    start_time = time.time()
    print(f"=== [1/5] Initializing Database: {target_db_path.name} ===")
    if target_db_path.exists():
        target_db_path.unlink()

    conn = sqlite3.connect(str(target_db_path))
    cursor = conn.cursor()

    # Turbo PRAGMAs for massive batch ingest
    cursor.execute("PRAGMA synchronous = OFF;")
    cursor.execute("PRAGMA journal_mode = MEMORY;")
    cursor.execute("PRAGMA cache_size = 200000;")
    cursor.execute("PRAGMA temp_store = MEMORY;")

    # Execute base DDL
    create_tables_sql_path = ROOT / "schema" / "create_tables.sql"
    if create_tables_sql_path.exists():
        with open(create_tables_sql_path, "r", encoding="utf-8") as f:
            cursor.executescript(f.read())
    else:
        cursor.executescript(SCHEMA_DDL)

    print("=== [2/5] Generating and inserting organizations & products ===")
    orgs, org_index = generate_organizations()
    org_rows = [[org.get(f, "") for f in ORG_FIELDS] for org in orgs]
    cursor.executemany(
        f"INSERT INTO organizations ({','.join(ORG_FIELDS)}) VALUES ({','.join(['?']*len(ORG_FIELDS))});",
        org_rows
    )
    conn.commit()
    print(f"  Inserted {len(org_rows):,} organizations.")

    products_as_rows = [list(p) for p in ALL_PRODUCTS]
    cursor.executemany(
        f"INSERT INTO products ({','.join(PRODUCT_FIELDS)}) VALUES ({','.join(['?']*len(PRODUCT_FIELDS))});",
        products_as_rows
    )
    conn.commit()
    print(f"  Inserted {len(products_as_rows):,} products.")

    print("=== [3/5] Generating and inserting zip territories ===")
    zips = generate_zip_territories(orgs)
    zip_rows = [[z.get(f, "") for f in ZIP_FIELDS] for z in zips]
    cursor.executemany(
        f"INSERT INTO zip_territory ({','.join(ZIP_FIELDS)}) VALUES ({','.join(['?']*len(ZIP_FIELDS))});",
        zip_rows
    )
    conn.commit()
    print(f"  Inserted {len(zip_rows):,} zip territory records.")

    print(f"=== [4/5] Streaming and inserting {num_sales:,} sales transactions ===")
    sales_gen = generate_sales(orgs, org_index)
    batch = []
    batch_size = 50_000
    total_sales = 0
    insert_sql = f"INSERT INTO sales ({','.join(SALES_FIELDS)}) VALUES ({','.join(['?']*len(SALES_FIELDS))});"

    for sale_row in sales_gen:
        batch.append(sale_row)
        if len(batch) >= batch_size:
            cursor.executemany(insert_sql, batch)
            conn.commit()
            total_sales += len(batch)
            print(f"  ... {total_sales:,} / {num_sales:,} sales inserted ({time.time() - start_time:.1f}s)")
            batch = []

    if batch:
        cursor.executemany(insert_sql, batch)
        conn.commit()
        total_sales += len(batch)

    print(f"  Total sales inserted: {total_sales:,}")

    # Seed users and session tables
    print("=== [5/5] Creating user mappings and analytics indexes ===")
    seed_users_sql = """
    CREATE TABLE IF NOT EXISTS users (
        user_id         TEXT PRIMARY KEY,
        email           TEXT UNIQUE NOT NULL,
        full_name       TEXT NOT NULL,
        role            TEXT NOT NULL CHECK(role IN ('exec', 'director', 'ram')),
        territory_name  TEXT,
        region_name     TEXT,
        can_view_wac    INTEGER DEFAULT 0
    );

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

    INSERT OR IGNORE INTO users (user_id, email, full_name, role, territory_name, region_name, can_view_wac) VALUES
    ('usr_exec_01', 'sarah.chen@novapharma.com', 'Sarah Chen', 'exec', NULL, NULL, 1),
    ('usr_exec_02', 'robert.taylor@novapharma.com', 'Robert Taylor', 'exec', NULL, NULL, 1),
    ('usr_dir_ne', 'marcus.vance@novapharma.com', 'Marcus Vance', 'director', NULL, 'Northeast', 0),
    ('usr_dir_ma', 'elizabeth.stone@novapharma.com', 'Elizabeth Stone', 'director', NULL, 'Mid-Atlantic', 0),
    ('usr_dir_se', 'james.holloway@novapharma.com', 'James Holloway', 'director', NULL, 'Southeast', 0),
    ('usr_dir_mw', 'karen.brooks@novapharma.com', 'Karen Brooks', 'director', NULL, 'Midwest', 0),
    ('usr_dir_sc', 'thomas.wright@novapharma.com', 'Thomas Wright', 'director', NULL, 'South Central', 0),
    ('usr_dir_we', 'patricia.king@novapharma.com', 'Patricia King', 'director', NULL, 'West', 0),
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

    print("  Creating high-performance indexes on 2M sales rows...")
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_sales_data_source ON sales(data_source, brand_flag);",
        "CREATE INDEX IF NOT EXISTS idx_sales_mo_offset ON sales(mo_offset);",
        "CREATE INDEX IF NOT EXISTS idx_sales_wk_offset ON sales(wk_offset);",
        "CREATE INDEX IF NOT EXISTS idx_sales_org_id ON sales(org_id);",
        "CREATE INDEX IF NOT EXISTS idx_sales_ndc ON sales(ndc);",
        "CREATE INDEX IF NOT EXISTS idx_sales_drug_name ON sales(drug_name);",
        "CREATE INDEX IF NOT EXISTS idx_sales_period_mo ON sales(period_mo);",
        "CREATE INDEX IF NOT EXISTS idx_sales_period_qtr ON sales(period_qtr);",
        "CREATE INDEX IF NOT EXISTS idx_org_zip ON organizations(zip);",
        "CREATE INDEX IF NOT EXISTS idx_org_grandparent ON organizations(grandparent_org_name);",
        "CREATE INDEX IF NOT EXISTS idx_zip_terr_zip ON zip_territory(zip);",
        "CREATE INDEX IF NOT EXISTS idx_zip_terr_name ON zip_territory(territory_name);",
        "CREATE INDEX IF NOT EXISTS idx_zip_reg_name ON zip_territory(region_name);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON chat_sessions(user_id, updated_at);",
        "CREATE INDEX IF NOT EXISTS idx_messages_session ON session_messages(session_id, created_at);",
    ]
    for idx_sql in indices:
        cursor.execute(idx_sql)
    conn.commit()

    # Reset PRAGMAs to safe WAL mode for runtime
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    conn.commit()
    conn.close()

    db_size_mb = os.path.getsize(target_db_path) / (1024 * 1024)
    print(f"\n[DONE] Built {target_db_path.name} ({db_size_mb:.1f} MB) in {time.time() - start_time:.1f}s")
    return target_db_path


def compress_database(db_path: Path, output_gz_path: Path):
    print(f"\nCompressing {db_path.name} into {output_gz_path.name}...")
    start = time.time()
    with open(db_path, "rb") as f_in, gzip.open(output_gz_path, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    gz_size_mb = os.path.getsize(output_gz_path) / (1024 * 1024)
    print(f"[DONE] Compressed to {output_gz_path.name} ({gz_size_mb:.1f} MB) in {time.time() - start:.1f}s")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "pharma.db")
    build_database(target)
