"""
FastAPI Backend Application for NovaPharma Commercial Analytics Assistant.
Provides RESTful APIs for chat, user switching, schema exploration, and static web UI.
"""

import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.db import init_database, execute_query, get_user_by_id_or_email, get_all_users
from backend.models import ChatRequest, ChatResponse, QueryResult, ChartConfig
from backend.security import validate_and_sanitize_sql, filter_response_data
from backend.llm_engine import LLMEngine
from backend.domain_knowledge import NOVAPHARMA_PRODUCTS, SCHEMA_DDL, DOMAIN_RULES
from backend.logger import log_interaction, get_recent_logs, clear_logs

# Ensure database is initialized
init_database()

app = FastAPI(
    title="NovaPharma Commercial Analytics Assistant",
    description="Production-grade NL-to-SQL conversational assistant with domain intelligence and RBAC security.",
    version="1.0.0"
)

# Enable CORS for local development and integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm_engine = LLMEngine()
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/api/health")
def health_check():
    """Healthcheck endpoint returning database and engine status."""
    try:
        rows, exec_time, _ = execute_query("SELECT COUNT(*) as total_sales FROM sales;")
        return {
            "status": "healthy",
            "database": "connected",
            "total_sales_rows": rows[0]["total_sales"] if rows else 0,
            "engine_latency_ms": exec_time
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "unhealthy", "error": str(e)})


@app.get("/api/users")
def list_users():
    """Retrieve all personas for easy role switching in the UI."""
    return get_all_users()


@app.get("/api/user/{identifier}")
def get_user_profile(identifier: str):
    """Retrieve details for a specific user ID or email."""
    user = get_user_by_id_or_email(identifier)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/api/schema")
def get_schema_metadata():
    """Returns database schema, product portfolio, and domain glossary for UI exploration."""
    return {
        "schema_ddl": SCHEMA_DDL,
        "products": NOVAPHARMA_PRODUCTS,
        "domain_rules": DOMAIN_RULES,
        "roles": [
            {
                "role": "exec",
                "scope": "Global (All territories and regions)",
                "wac_access": "Full Access (Revenue & Dollar metrics visible)",
                "sample_user": "Sarah Chen (sarah.chen@novapharma.com)"
            },
            {
                "role": "director",
                "scope": "Region-Scoped (e.g. Northeast)",
                "wac_access": "Hidden (Volume and Equivalents only)",
                "sample_user": "Jennifer Walsh (jennifer.walsh@novapharma.com)"
            },
            {
                "role": "ram",
                "scope": "Territory-Scoped (e.g. New York Metro)",
                "wac_access": "Hidden (Volume and Equivalents only)",
                "sample_user": "Amy Nguyen (amy.nguyen@novapharma.com)"
            }
        ]
    }


@app.post("/api/chat", response_model=ChatResponse)
def handle_chat_query(req: ChatRequest):
    """
    Main Conversational NL-to-SQL endpoint.
    Processes natural language question, enforces RBAC & WAC security, executes SQL, and returns structured insights.
    """
    user = get_user_by_id_or_email(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{req.user_id}' not found in system.")

    history_dicts = [{"role": m.role, "content": m.content, "sql": m.sql} for m in (req.conversation_history or [])]

    # Generate response from LLM or deterministic engine
    try:
        llm_output = llm_engine.generate_response(
            user_info=user,
            message=req.message,
            conversation_history=history_dicts,
            provider_override=req.api_provider,
            api_key_override=req.api_key
        )
    except Exception as llm_exc:
        err_str = str(llm_exc)
        log_interaction(
            user_name=user["full_name"],
            user_role=user["role"],
            question=req.message,
            provider=req.api_provider or "gemini",
            error=err_str
        )
        return ChatResponse(
            success=False,
            user_id=user["user_id"],
            user_name=user["full_name"],
            user_role=user["role"],
            territory=user["territory_name"],
            region=user["region_name"],
            can_view_wac=bool(user["can_view_wac"]),
            question=req.message,
            sql=None,
            explanation=f"⚠️ {err_str}",
            error=err_str,
            suggestions=["Configure API Key in Settings"]
        )

    sql_query = llm_output.get("sql")
    explanation = llm_output.get("explanation", "Here are the results for your request.")
    chart_type = llm_output.get("chart_type", "none")
    x_key = llm_output.get("x_key")
    y_keys = llm_output.get("y_keys")
    suggestions = llm_output.get("suggestions", [])
    security_notice = None
    query_data = None
    error_msg = None

    if sql_query:
        # Enforce Multi-Layer Security Guardrails
        is_valid, sec_error, sanitized_sql = validate_and_sanitize_sql(sql_query, user)
        if not is_valid:
            log_interaction(
                user_name=user["full_name"],
                user_role=user["role"],
                question=req.message,
                provider=req.api_provider or "default",
                sql=sql_query,
                error=sec_error
            )
            return ChatResponse(
                success=False,
                user_id=user["user_id"],
                user_name=user["full_name"],
                user_role=user["role"],
                territory=user["territory_name"],
                region=user["region_name"],
                can_view_wac=bool(user["can_view_wac"]),
                question=req.message,
                sql=sql_query,
                explanation=sec_error or "Security policy violation.",
                security_notice=sec_error,
                suggestions=["Show volume in pack units instead", "What are my top accounts?"]
            )

        try:
            # Execute sanitized query
            rows, exec_time, cols = execute_query(sanitized_sql)
            
            # Post-execution column filtering defense
            clean_rows = filter_response_data(rows, user)
            clean_cols = [c for c in cols if "wac" not in c.lower()] if not user["can_view_wac"] else cols

            query_data = QueryResult(
                columns=clean_cols,
                rows=clean_rows,
                row_count=len(clean_rows),
                execution_time_ms=exec_time
            )

            # Refine chart hints if not provided
            if len(clean_rows) == 0:
                if not explanation or "here are" in explanation.lower() or "top" in explanation.lower():
                    explanation = "No matching records were found for this specific filter criteria in the database. You may want to broaden your search or adjust the timeframe."
                if not suggestions:
                    suggestions = ["Show overall top accounts", "Show all products this quarter", "Check last 6 months trend"]
            elif chart_type == "none" and len(clean_rows) > 0 and len(clean_cols) >= 2:
                chart_type = "bar" if len(clean_rows) <= 15 else "table"
                x_key = clean_cols[0]
                y_keys = [clean_cols[1]]

        except Exception as query_exc:
            error_msg = f"Database Query Error: {str(query_exc)}"
            explanation = f"I encountered an error executing the query: {str(query_exc)}"

    chart_config = ChartConfig(
        chart_type=chart_type or "none",
        x_key=x_key,
        y_keys=y_keys,
        title=f"Analysis for: {req.message[:50]}..."
    )

    # Record log
    log_interaction(
        user_name=user["full_name"],
        user_role=user["role"],
        question=req.message,
        provider=req.api_provider or "gemini",
        sql=sql_query,
        row_count=query_data.row_count if query_data else 0,
        execution_time_ms=query_data.execution_time_ms if query_data else 0.0,
        error=error_msg
    )

    rag_sources = llm_output.get("rag_sources", [])

    return ChatResponse(
        success=error_msg is None,
        user_id=user["user_id"],
        user_name=user["full_name"],
        user_role=user["role"],
        territory=user["territory_name"],
        region=user["region_name"],
        can_view_wac=bool(user["can_view_wac"]),
        question=req.message,
        sql=sql_query,
        explanation=explanation,
        data=query_data,
        chart=chart_config,
        suggestions=suggestions,
        rag_sources=rag_sources,
        security_notice=security_notice,
        error=error_msg
    )


@app.get("/api/rag/domains")
def get_rag_domains():
    """Retrieve indexed Multi-Domain RAG status and metadata."""
    from backend.rag_engine import rag_engine
    return rag_engine.get_indexed_summary()


@app.get("/api/rag/search")
def search_rag(query: str, domain: Optional[str] = None):
    """Debug endpoint to search the multi-domain RAG knowledge base."""
    from backend.rag_engine import rag_engine
    chunks = rag_engine.retrieve_relevant_context(query, top_k=5, target_domain=domain)
    return {
        "query": query,
        "routed_domains": rag_engine.route_query_domains(query) if not domain else [domain],
        "chunks": chunks
    }


@app.get("/api/logs")
def get_logs():
    """Retrieve in-memory chronological interaction logs."""
    return get_recent_logs()


@app.post("/api/logs/clear")
def clear_all_logs():
    """Clear memory and disk interaction logs."""
    clear_logs()
    return {"status": "logs cleared"}


# Serve Static Frontend Files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
