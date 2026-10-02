"""
FastAPI Backend Application for Pharma Analytics Bot (Commercial Intelligence AI).
Provides RESTful APIs for chat, user switching, session management, schema exploration, and static web UI.
"""

import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.db import (
    init_database, execute_query, get_user_by_id_or_email, get_all_users,
    init_session_tables, create_session, get_user_sessions, get_session_history,
    save_message, rename_session, delete_session, clear_all_sessions, auto_name_session
)
from backend.models import ChatRequest, ChatResponse, QueryResult, ChartConfig, SessionInfo
from backend.security import validate_and_sanitize_sql, filter_response_data
from backend.llm_engine import LLMEngine
from backend.domain_knowledge import NOVAPHARMA_PRODUCTS, SCHEMA_DDL, DOMAIN_RULES
from backend.logger import log_interaction, get_recent_logs, clear_logs

from backend.agent_harness import agent_harness

# Initialize database tables including session state tables
init_database()
init_session_tables()

app = FastAPI(
    title="Pharma Analytics Bot",
    description="Enterprise NL-to-SQL conversational commercial intelligence assistant with multi-source domain reasoning, multi-agent harness, RBAC security, and persistent multi-user session state.",
    version="2.0.0"
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


# ====================================================================
# HEALTH & DIAGNOSTICS
# ====================================================================

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


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Handle browser favicon request cleanly without 404 logs."""
    return Response(status_code=204)


# ====================================================================
# USER MANAGEMENT
# ====================================================================

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


# ====================================================================
# SESSION STATE MANAGEMENT
# ====================================================================

@app.post("/api/sessions")
def create_new_session(user_id: str):
    """Create a new isolated chat session for a user. Returns session_id."""
    user = get_user_by_id_or_email(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
    session = create_session(user_id=user_id, session_name="New Chat")
    return session


@app.get("/api/sessions/{user_id}")
def list_user_sessions(user_id: str):
    """List all chat sessions for a user (newest first, with message count)."""
    user = get_user_by_id_or_email(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
    return get_user_sessions(user_id)


@app.get("/api/sessions/{session_id}/messages")
@app.get("/api/sessions/{session_id}/history")
def get_session_messages(session_id: str):
    """Load full message history of a session for restoring conversation UI."""
    messages = get_session_history(session_id)
    return messages


@app.patch("/api/sessions/{session_id}/rename")
def rename_session_endpoint(session_id: str, name: str):
    """Rename a session."""
    ok = rename_session(session_id, name)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"status": "renamed", "session_id": session_id, "new_name": name}


@app.delete("/api/sessions/{session_id}")
def delete_session_endpoint(session_id: str):
    """Delete a session and all its messages."""
    ok = delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"status": "deleted", "session_id": session_id}


@app.post("/api/sessions/clear_all")
def clear_all_sessions_endpoint(user_id: Optional[str] = None):
    """Clear all chat sessions and messages across users or for a specific user."""
    deleted = clear_all_sessions(user_id)
    return {"status": "cleared", "sessions_deleted": deleted}


# ====================================================================
# MAIN CHAT ENDPOINT (Session-Aware)
# ====================================================================

@app.post("/api/chat", response_model=ChatResponse)
def handle_chat_query(req: ChatRequest):
    """
    Main Conversational NL-to-SQL endpoint driven by the Multi-Agent Harness.
    Supports persistent session state: loads history from DB if session_id is provided.
    Orchestrates Supervisor, SQL Architect, Security Guardrail, DB Reflexion, and Executive Insights agents.
    """
    user = get_user_by_id_or_email(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{req.user_id}' not found in system.")

    # ---- Session State: Load or create session ----
    session_id = req.session_id
    is_new_session = False
    if session_id:
        # Load persistent history from DB (overrides any history sent from frontend)
        db_history = get_session_history(session_id)
        history_dicts = [
            {"role": m["role"], "content": m["content"], "sql": m.get("sql_query")}
            for m in db_history
        ]
    else:
        # No session_id: create a new session now
        new_session = create_session(user_id=user["user_id"])
        session_id = new_session["session_id"]
        is_new_session = True
        history_dicts = [{"role": m.role, "content": m.content, "sql": m.sql} for m in (req.conversation_history or [])]

    # Persist the user's message immediately
    save_message(
        session_id=session_id,
        user_id=user["user_id"],
        role="user",
        content=req.message
    )

    # Auto-name the session after first user message
    if is_new_session or len(history_dicts) == 0:
        rename_session(session_id, auto_name_session(req.message))

    # ---- Run Multi-Agent Pipeline ----
    try:
        pipeline_res = agent_harness.run_pipeline(
            user_info=user,
            message=req.message,
            conversation_history=history_dicts,
            provider_override=req.api_provider,
            api_key_override=req.api_key
        )
    except Exception as exc:
        err_str = str(exc)
        log_interaction(
            user_name=user["full_name"],
            user_role=user["role"],
            question=req.message,
            provider=req.api_provider or "gemini",
            error=err_str
        )
        # Persist error response too
        save_message(session_id=session_id, user_id=user["user_id"], role="assistant",
                     content=f"⚠️ {err_str}")
        return ChatResponse(
            success=False,
            user_id=user["user_id"],
            user_name=user["full_name"],
            user_role=user["role"],
            session_id=session_id,
            territory=user["territory_name"],
            region=user["region_name"],
            can_view_wac=bool(user["can_view_wac"]),
            question=req.message,
            sql=None,
            explanation=f"⚠️ {err_str}",
            error=err_str,
            suggestions=["Configure API Key in Settings"]
        )

    q_data = pipeline_res.get("data")
    explanation = pipeline_res.get("explanation", "")

    log_interaction(
        user_name=user["full_name"],
        user_role=user["role"],
        question=req.message,
        provider=req.api_provider or "gemini",
        sql=pipeline_res.get("sql"),
        row_count=q_data.row_count if q_data else 0,
        execution_time_ms=q_data.execution_time_ms if q_data else 0.0,
        error=pipeline_res.get("error")
    )

    # Persist assistant response to session DB
    save_message(
        session_id=session_id,
        user_id=user["user_id"],
        role="assistant",
        content=explanation,
        sql_query=pipeline_res.get("sql"),
        row_count=q_data.row_count if q_data else 0,
        latency_ms=q_data.execution_time_ms if q_data else 0.0,
        traces_json=json.dumps(pipeline_res.get("traces", []))
    )

    return ChatResponse(
        success=pipeline_res.get("success", True),
        user_id=user["user_id"],
        user_name=user["full_name"],
        user_role=user["role"],
        session_id=session_id,
        territory=user["territory_name"],
        region=user["region_name"],
        can_view_wac=bool(user["can_view_wac"]),
        question=req.message,
        sql=pipeline_res.get("sql"),
        explanation=explanation,
        data=q_data,
        chart=pipeline_res.get("chart"),
        suggestions=pipeline_res.get("suggestions", []),
        rag_sources=pipeline_res.get("rag_sources", []),
        traces=pipeline_res.get("traces", []),
        security_notice=pipeline_res.get("security_notice"),
        error=pipeline_res.get("error")
    )


# ====================================================================
# RAG DIAGNOSTICS & LOGS
# ====================================================================

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


# ====================================================================
# STATIC FRONTEND
# ====================================================================
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
