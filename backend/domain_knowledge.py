"""
Domain Knowledge Base and System Prompt Generator for NovaPharma Commercial Analytics.
Encapsulates pharmaceutical commercial business rules, metric formulas, and security guidance.
"""

from typing import Dict, Any, List, Optional


# Complete Schema DDL representation for LLM Context
SCHEMA_DDL = """
-- Table: organizations (40,000 facilities, parents, IDN grandparents, GPOs)
CREATE TABLE organizations (
    org_id              TEXT PRIMARY KEY,
    org_name            TEXT NOT NULL,
    org_type            TEXT NOT NULL,       -- 'Facility', 'Parent', 'Grandparent', 'GPO', 'Payer'
    org_status          TEXT NOT NULL,       -- 'Active', 'Inactive'
    org_archetype       TEXT,               -- 'Hospital', 'Clinic', 'IDN', 'Government', 'Specialty Pharmacy'
    specialty           TEXT,               -- 'Oncology', 'Urology', 'Mixed'
    address_line1       TEXT,
    city                TEXT,
    state               TEXT,
    zip                 TEXT,
    parent_org_id       TEXT,               -- references organizations.org_id
    parent_org_name     TEXT,
    grandparent_org_id  TEXT,               -- references organizations.org_id (top-level IDN/system)
    grandparent_org_name TEXT,
    gpo_name            TEXT,               -- 'Onmark', 'ION', 'Unity', 'VitalSource'
    is_340b             INTEGER DEFAULT 0   -- 1 = 340B covered entity, 0 = standard
);

-- Table: products (40 products: 7 NovaPharma branded + 33 competitors)
CREATE TABLE products (
    ndc                     TEXT PRIMARY KEY,   -- 11-digit NDC code
    drug_name               TEXT NOT NULL,
    generic_name            TEXT NOT NULL,
    strength                TEXT,               -- e.g. '80MG/4ML', '20MG/1ML'
    form                    TEXT,               -- 'Injectable', 'Tablet', 'Oral'
    brand_flag              INTEGER NOT NULL,   -- 1 = NovaPharma owned brand, 0 = competitor/generic
    specialty               TEXT,               -- 'Oncology', 'Urology'
    market_category         TEXT,               -- e.g. 'Taxanes', 'Platinum Compounds', 'Antimetabolites', 'GnRH Agonists'
    market_subcategory      TEXT,               -- e.g. 'Docetaxel', 'Carboplatin', 'Gemcitabine', 'Pemetrexed', 'Leuprolide'
    unit_conversion_factor  REAL,               -- pack_units * unit_conversion_factor = equivalents
    mg_equivalent           REAL                -- dosing equivalent in mg
);

-- Table: sales (~2M rows: 3 years of daily sales)
CREATE TABLE sales (
    sale_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id              TEXT NOT NULL,           -- references organizations.org_id
    ndc                 TEXT NOT NULL,           -- references products.ndc
    drug_name           TEXT NOT NULL,
    data_source         TEXT NOT NULL,           -- 'distributor', 'hub_dispense', 'market_data'
    brand_flag          INTEGER NOT NULL,        -- 1 = branded, 0 = generic/competitor
    pack_units          REAL,
    total_mg            REAL,
    wac                 REAL,                    -- wholesale acquisition cost (dollar amount, RESTRICTED: Exec only)
    transaction_date    TEXT,                    -- YYYY-MM-DD
    week_ending_date    TEXT,                    -- YYYY-MM-DD
    state               TEXT,
    specialty           TEXT,
    period_wk           TEXT,                    -- YYYY-WNN (e.g. 2026-W38)
    period_mo           TEXT,                    -- YYYY-MM (e.g. 2026-09)
    period_qtr          TEXT,                    -- YYYY-QN (e.g. 2026-Q3)
    wk_offset           INTEGER,                -- 0 = current week, 1 = last week
    mo_offset           INTEGER,                -- 0 = current month, 1 = last month, 0..2 = R3M, 3..5 = R6M
    FOREIGN KEY (org_id) REFERENCES organizations(org_id),
    FOREIGN KEY (ndc) REFERENCES products(ndc)
);

-- Table: zip_territory (mapping of ZIP codes to territory & region)
CREATE TABLE zip_territory (
    zip                 TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    territory_number    TEXT NOT NULL,
    territory_name      TEXT NOT NULL,          -- e.g. 'New York Metro', 'New England', 'Texas'
    region_number       TEXT,
    region_name         TEXT                    -- e.g. 'Northeast', 'Mid-Atlantic', 'Southeast', 'Midwest', 'South Central', 'West'
);

-- Table: users (role-based access control)
CREATE TABLE users (
    user_id             TEXT PRIMARY KEY,
    email               TEXT NOT NULL UNIQUE,
    full_name           TEXT NOT NULL,
    role                TEXT NOT NULL,          -- 'exec', 'director', 'ram'
    territory_name      TEXT,                  -- assigned territory (RAM only)
    region_name         TEXT,                  -- assigned region (Director and RAM)
    can_view_wac        INTEGER DEFAULT 0      -- 1 = Exec can see WAC pricing, 0 = Director/RAM cannot
);
"""

# Portfolio and Market metadata
NOVAPHARMA_PRODUCTS = [
    {"drug_name": "ZENOVAX", "generic_name": "docetaxel", "specialty": "Oncology", "market_category": "Taxanes", "market_subcategory": "Docetaxel"},
    {"drug_name": "CARBOTREL", "generic_name": "carboplatin", "specialty": "Oncology", "market_category": "Platinum Compounds", "market_subcategory": "Carboplatin"},
    {"drug_name": "GEMTARA", "generic_name": "gemcitabine", "specialty": "Oncology", "market_category": "Antimetabolites", "market_subcategory": "Gemcitabine"},
    {"drug_name": "PAXELIUM", "generic_name": "pemetrexed", "specialty": "Oncology", "market_category": "Antimetabolites", "market_subcategory": "Pemetrexed"},
    {"drug_name": "ONCOSETRON", "generic_name": "palonosetron", "specialty": "Oncology", "market_category": "Antiemetics", "market_subcategory": "Palonosetron"},
    {"drug_name": "CYCLONOVA", "generic_name": "cyclophosphamide", "specialty": "Oncology", "market_category": "Alkylating Agents", "market_subcategory": "Cyclophosphamide"},
    {"drug_name": "LUPREX DEPOT", "generic_name": "leuprolide", "specialty": "Urology", "market_category": "GnRH Agonists", "market_subcategory": "Leuprolide"},
]

DOMAIN_RULES = """
### DOMAIN RULES & BUSINESS METRIC DEFINITIONS:

1. **DATA SOURCES**:
   - `distributor`: NovaPharma's shipment data (paid demand). ALWAYS use this for NovaPharma sales, volume, and revenue queries. Must filter `data_source = 'distributor' AND brand_flag = 1`.
   - `hub_dispense`: Free drug / patient assistance program (PAP). `wac = 0`. ONLY include if the user specifically asks about free drug, PAP, or "total volume including free drug".
   - `market_data`: Third-party competitor & market research volume. Used exclusively for Market Share denominator, competitive analysis, or total market size.

2. **MARKET SHARE FORMULA**:
   - Market Share = (NovaPharma Branded Equivalents from `distributor`) / (Total Market Equivalents from `market_data`).
   - Both numerator and denominator MUST be calculated for the same therapeutic `market_subcategory` (or `market_category`).
   - Equivalents calculation: `SUM(s.pack_units * p.unit_conversion_factor)` or `SUM(s.total_mg / p.mg_equivalent)`.
   - Example SQL structure:
     ```sql
     WITH nova_vol AS (
         SELECT SUM(s.pack_units * p.unit_conversion_factor) AS nova_eq
         FROM sales s
         JOIN products p ON s.ndc = p.ndc
         WHERE s.data_source = 'distributor' AND s.brand_flag = 1 AND p.market_subcategory = 'Docetaxel'
     ),
     market_vol AS (
         SELECT SUM(s.pack_units * p.unit_conversion_factor) AS mkt_eq
         FROM sales s
         JOIN products p ON s.ndc = p.ndc
         WHERE s.data_source = 'market_data' AND p.market_subcategory = 'Docetaxel'
     )
     SELECT 
         nova_eq, 
         mkt_eq, 
         ROUND((nova_eq * 100.0) / NULLIF(mkt_eq, 0), 2) AS market_share_pct
     FROM nova_vol, market_vol;
     ```

3. **PERIOD OFFSETS (ALWAYS PREFER OFFSETS OVER DATE MATH)**:
   - Current Month: `mo_offset = 0`
   - Last Month (completed full month): `mo_offset = 1`
   - Last 3 Months (R3M): `mo_offset IN (0, 1, 2)` (or `mo_offset BETWEEN 0 AND 2`)
   - Prior 3 Months (R6M comparison): `mo_offset IN (3, 4, 5)`
   - Current Week: `wk_offset = 0`
   - Last 4 Weeks: `wk_offset <= 3`
   - For trends or grouping by time, use `period_mo` (e.g. '2026-09') or `period_qtr` (e.g. '2026-Q3').

4. **ACCOUNT AGGREGATION & HIERARCHY**:
   - Account aggregation defaults to Grandparent level: `COALESCE(o.grandparent_org_name, o.org_name) AS account_name`.
   - To link sales to territory/region: `JOIN organizations o ON s.org_id = o.org_id JOIN zip_territory z ON o.zip = z.zip`.
"""

FEW_SHOT_EXAMPLES = [
    {
        "role": "exec",
        "question": "What is our total revenue and pack units this quarter by product?",
        "sql": """SELECT 
    s.drug_name,
    SUM(s.pack_units) AS total_pack_units,
    ROUND(SUM(s.wac), 2) AS gross_revenue_wac
FROM sales s
WHERE s.data_source = 'distributor' 
  AND s.brand_flag = 1 
  AND s.mo_offset IN (0, 1, 2)
GROUP BY s.drug_name
ORDER BY gross_revenue_wac DESC;"""
    },
    {
        "role": "ram",
        "scope": "New York Metro",
        "question": "What are my top 5 accounts by pack units this quarter?",
        "sql": """SELECT 
    COALESCE(o.grandparent_org_name, o.org_name) AS account_name,
    SUM(s.pack_units) AS total_pack_units
FROM sales s
JOIN organizations o ON s.org_id = o.org_id
JOIN zip_territory z ON o.zip = z.zip
WHERE s.data_source = 'distributor' 
  AND s.brand_flag = 1
  AND s.mo_offset IN (0, 1, 2)
  AND z.territory_name = 'New York Metro'
GROUP BY account_name
ORDER BY total_pack_units DESC
LIMIT 5;"""
    },
    {
        "role": "director",
        "scope": "Northeast",
        "question": "Show me Zenovax volume by territory for last month.",
        "sql": """SELECT 
    z.territory_name,
    SUM(s.pack_units) AS total_pack_units
FROM sales s
JOIN organizations o ON s.org_id = o.org_id
JOIN zip_territory z ON o.zip = z.zip
WHERE s.data_source = 'distributor'
  AND s.brand_flag = 1
  AND s.drug_name = 'ZENOVAX'
  AND s.mo_offset = 1
  AND z.region_name = 'Northeast'
GROUP BY z.territory_name
ORDER BY total_pack_units DESC;"""
    },
    {
        "role": "ram",
        "scope": "New York Metro",
        "question": "What is our market share for Zenovax in my territory?",
        "sql": """WITH nova_sales AS (
    SELECT SUM(s.pack_units * p.unit_conversion_factor) AS nova_eq
    FROM sales s
    JOIN products p ON s.ndc = p.ndc
    JOIN organizations o ON s.org_id = o.org_id
    JOIN zip_territory z ON o.zip = z.zip
    WHERE s.data_source = 'distributor'
      AND s.brand_flag = 1
      AND p.market_subcategory = 'Docetaxel'
      AND z.territory_name = 'New York Metro'
),
market_sales AS (
    SELECT SUM(s.pack_units * p.unit_conversion_factor) AS total_mkt_eq
    FROM sales s
    JOIN products p ON s.ndc = p.ndc
    JOIN organizations o ON s.org_id = o.org_id
    JOIN zip_territory z ON o.zip = z.zip
    WHERE s.data_source = 'market_data'
      AND p.market_subcategory = 'Docetaxel'
      AND z.territory_name = 'New York Metro'
)
SELECT 
    ROUND(nova_sales.nova_eq, 2) AS nova_equivalents,
    ROUND(market_sales.total_mkt_eq, 2) AS total_market_equivalents,
    ROUND((nova_sales.nova_eq * 100.0) / NULLIF(market_sales.total_mkt_eq, 0), 2) AS market_share_pct
FROM nova_sales, market_sales;"""
    }
]


from backend.rag_engine import rag_engine


def build_system_prompt(user_info: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Generate system prompt customized for the logged-in user's role and security scope.
    Dynamically injects retrieved knowledge chunks from Multi-Domain RAG for the specific question.
    Hardcoded RBAC/WAC security rules are strictly preserved regardless of RAG.
    """
    role = user_info.get("role", "ram").lower()
    full_name = user_info.get("full_name", "User")
    territory = user_info.get("territory_name")
    region = user_info.get("region_name")
    can_view_wac = user_info.get("can_view_wac", 0) == 1

    # HARDCODED DEFENSE-IN-DEPTH SECURITY RULES (Decoupled from RAG)
    security_clause = ""
    if role == "exec":
        security_clause = """
SECURITY & ACCESS CONTROL (ROLE: EXEC - GLOBAL ACCESS):
- User has GLOBAL access across all territories and regions.
- User HAS ACCESS to WAC pricing data (can SELECT and aggregate `s.wac`).
- Queries do NOT need territory or region filtering unless the user explicitly requests a specific region/territory.
"""
    elif role == "director":
        security_clause = f"""
SECURITY & ACCESS CONTROL (ROLE: DIRECTOR - REGIONAL ACCESS: {region}):
- User is RESTRICTED to data within their assigned region: '{region}'.
- ALL queries involving sales or organizations MUST join `zip_territory z ON o.zip = z.zip` (via `organizations o ON s.org_id = o.org_id`) and filter `z.region_name = '{region}'`.
- STRICT COLUMN RESTRICTION: User has NO ACCESS to WAC pricing data (`can_view_wac = 0`).
  - DO NOT include `s.wac` or any revenue pricing in SELECT, WHERE, or aggregation.
  - If user asks for revenue/sales in dollars, provide volume metrics (`SUM(s.pack_units)` or equivalents) instead and clearly mention that pricing is restricted to Executive role.
"""
    else:  # RAM
        security_clause = f"""
SECURITY & ACCESS CONTROL (ROLE: RAM - TERRITORY ACCESS: {territory}, Region: {region}):
- User is RESTRICTED to data within their assigned territory: '{territory}'.
- ALL queries involving sales or organizations MUST join `zip_territory z ON o.zip = z.zip` (via `organizations o ON s.org_id = o.org_id`) and filter `z.territory_name = '{territory}'`.
- STRICT COLUMN RESTRICTION: User has NO ACCESS to WAC pricing data (`can_view_wac = 0`).
  - DO NOT include `s.wac` or any revenue pricing in SELECT, WHERE, or aggregation.
  - If user asks for revenue/sales in dollars, provide volume metrics (`SUM(s.pack_units)` or equivalents) instead and clearly mention that pricing is restricted to Executive role.
- User CANNOT query data for other territories. If asked to compare or see other territories, limit results strictly to '{territory}' or explain the scope constraint.
"""

    # Retrieve dynamic domain context if a query is provided
    rag_context = ""
    if query:
        rag_context = rag_engine.format_context_for_prompt(query)

    return f"""You are NovaPharma AI, an expert pharmaceutical commercial analytics assistant.
You translate natural language questions into accurate, performant SQLite queries and provide concise, executive-ready insights.

CURRENT USER PROFILE:
- Name: {full_name}
- Role: {role.upper()}
- Assigned Region: {region or 'Global'}
- Assigned Territory: {territory or 'Global'}
- Can View WAC Pricing: {'YES' if can_view_wac else 'NO (STRICTLY FORBIDDEN)'}

{security_clause}

DATABASE SCHEMA:
{SCHEMA_DDL}

{DOMAIN_RULES}

{rag_context}

SQL & RESPONSE GUIDELINES:
1. Generate valid, high-performance SQLite queries that strictly respect the user's role and security scope.
2. The "explanation" field MUST be written in clean, professional Natural Language suitable for commercial business users.
   - DO NOT include raw SQL code, table names, or database jargon (e.g. do not mention 'mo_offset', 'brand_flag', 'sales table', 'JOIN').
   - State findings clearly (e.g., "Here are our top 5 accounts in New York Metro by volume this quarter: Memorial Hospital leads with 1,240 pack units.").
3. Return ONLY a JSON object with the following schema:
{{
    "sql": "SELECT ...;",
    "explanation": "Clear, concise natural language response explaining the findings in business terms",
    "chart_type": "bar" | "line" | "pie" | "table" | "none",
    "x_key": "column_name_for_x_axis_or_categories",
    "y_keys": ["column_name_for_metrics"],
    "suggestions": ["Follow-up question 1", "Follow-up question 2"]
}}
4. If the user question is a greeting, out of scope, or cannot be answered with SQL, provide a helpful explanation with "sql": null.
5. Always handle division by zero using `NULLIF(denominator, 0)`.
6. For product volumes, default to `pack_units` or equivalents. For revenue (Exec only), use `SUM(s.wac)`.
7. MULTI-TURN CONVERSATION & DRILL-DOWN RULES:
   - When the user asks a follow-up (e.g., "Break down by month", "Filter for 340B accounts only", "Show monthly trend for the #1 account", "Compare that with Carbotrel"), preserve the previous query's entity context (active product, timeframe, account list).
   - Resolve pronouns ("it", "they", "those", "that account") using the immediate prior conversation turns.
   - If the user asks a completely new, unrelated question ("What is our total national sales for Cyclonova?"), reset the prior drill-down filters and generate a fresh query.
"""


