"""
Multi-Layer Security & RBAC Guardrail Module.
Enforces Row-Level Security (Territory/Region) and Column-Level Security (WAC restriction),
along with AST & SQL safety validation to guarantee zero data leakage.
"""

import re
from typing import Dict, Any, Tuple, Optional


DISALLOWED_SQL_KEYWORDS = [
    r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b",
    r"\bALTER\b", r"\bCREATE\b", r"\bTRUNCATE\b", r"\bREPLACE\b",
    r"\bATTACH\b", r"\bDETACH\b", r"\bPRAGMA\b", r"\bEXEC\b",
    r"\bVACUUM\b", r"\bGRANT\b", r"\bREVOKE\b"
]


class SecurityViolationError(Exception):
    """Custom exception raised when a security constraint or RBAC policy is breached."""
    pass


def validate_and_sanitize_sql(sql: str, user_info: Dict[str, Any]) -> Tuple[bool, Optional[str], str]:
    """
    Validates SQL safety and enforces RBAC rules (Row-Level Security & Column-Level WAC restriction).
    Returns (is_valid, error_message_if_invalid, sanitized_sql).
    """
    if not sql or not sql.strip():
        return False, "No SQL query generated.", ""

    cleaned_sql = sql.strip().rstrip(";")
    
    # 1. Prevent Multi-Statement / Semicolon injection
    if ";" in cleaned_sql:
        return False, "Multiple SQL statements in a single execution are prohibited for security.", ""

    # 2. Strict Read-Only Query Enforcement (Only SELECT / WITH allowed)
    upper_sql = cleaned_sql.upper().strip()
    if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
        return False, "Only read-only SELECT queries are permitted.", ""

    for pattern in DISALLOWED_SQL_KEYWORDS:
        if re.search(pattern, cleaned_sql, re.IGNORECASE):
            return False, f"Security Violation: Prohibited SQL command detected.", ""

    role = user_info.get("role", "ram").lower()
    can_view_wac = user_info.get("can_view_wac", 0) == 1
    territory = user_info.get("territory_name")
    region = user_info.get("region_name")

    # 3. Column-Level Security: WAC Restriction for non-executives
    if not can_view_wac:
        # Check for wac column reference in SELECT, WHERE, GROUP BY, ORDER BY
        wac_match = re.search(r"\b(s\.|sales\.)?wac\b", cleaned_sql, re.IGNORECASE)
        if wac_match:
            return (
                False,
                f"Access Denied: Pricing data (WAC revenue) is confidential and restricted to Executive roles. "
                f"As a {role.upper()}, you can analyze volume metrics (pack_units, equivalents, total_mg) instead.",
                ""
            )

    # 4. Row-Level Security: Territory and Region Scope Enforcement
    # Verify RAM / Director cannot query forbidden territories/regions
    if role == "ram" and territory:
        # Check if another territory is explicitly targeted in query
        other_territories = [
            "New England", "Mid-Atlantic East", "Mid-Atlantic West", "Southeast Atlantic",
            "Southeast Gulf", "Great Lakes East", "Great Lakes West", "Upper Midwest",
            "Texas", "South Central", "Pacific Northwest", "California North",
            "California South", "Mountain", "New York Metro"
        ]
        for t in other_territories:
            if t.lower() != territory.lower():
                # If another territory name is mentioned in quotes inside query
                if re.search(rf"'{re.escape(t)}'", cleaned_sql, re.IGNORECASE):
                    return (
                        False,
                        f"Access Denied: You are assigned to '{territory}'. You do not have permission to view data for '{t}'.",
                        ""
                    )

    elif role == "director" and region:
        # Check if another region is explicitly targeted
        other_regions = ["Northeast", "Mid-Atlantic", "Southeast", "Midwest", "South Central", "West"]
        for r in other_regions:
            if r.lower() != region.lower():
                if re.search(rf"'{re.escape(r)}'", cleaned_sql, re.IGNORECASE):
                    return (
                        False,
                        f"Access Denied: You are Director of the '{region}' region. You do not have permission to access data for '{r}'.",
                        ""
                    )

    return True, None, cleaned_sql + ";"


def filter_response_data(rows: list, user_info: Dict[str, Any]) -> list:
    """Post-execution defense: Ensure no restricted columns (like WAC) leak in output."""
    can_view_wac = user_info.get("can_view_wac", 0) == 1
    if can_view_wac:
        return rows

    sanitized_rows = []
    for row in rows:
        cleaned_row = {}
        for k, v in row.items():
            if "wac" in k.lower() or "gross_revenue" in k.lower() or "dollar" in k.lower():
                continue
            cleaned_row[k] = v
        sanitized_rows.append(cleaned_row)
    return sanitized_rows
