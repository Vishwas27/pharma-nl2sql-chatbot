"""
Multi-Agent Orchestration & Supervision Harness for NovaPharma Analytics Assistant.
Coordinates specialized agents:
1. Supervisor Agent (Intent Routing & RAG Context)
2. SQL Architect Agent (NL-to-SQL Generation)
3. Security Guardrail Agent (AST Validation & RBAC Scoping)
4. DB Execution & Self-Healing Reflection Loop
5. Executive Insights & Visualization Agent
Provides full observability traces for runtime auditability.
"""

import time
from typing import Dict, Any, List, Optional, Tuple

from backend.db import execute_query
from backend.security import validate_and_sanitize_sql, filter_response_data
from backend.rag_engine import rag_engine
from backend.domain_knowledge import build_system_prompt
from backend.llm_engine import LLMEngine
from backend.models import QueryResult, ChartConfig


class TraceStep:
    def __init__(self, step_num: int, agent_name: str, action: str, details: Optional[str] = None, latency_ms: float = 0.0, status: str = "SUCCESS"):
        self.step_num = step_num
        self.agent_name = agent_name
        self.action = action
        self.details = details
        self.latency_ms = round(latency_ms, 2)
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_num,
            "agent": self.agent_name,
            "action": self.action,
            "details": self.details,
            "latency_ms": self.latency_ms,
            "status": self.status
        }


class MultiAgentHarness:
    def __init__(self, llm_engine: Optional[LLMEngine] = None):
        self.llm_engine = llm_engine or LLMEngine()

    def run_pipeline(
        self,
        user_info: Dict[str, Any],
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the multi-agent pipeline with step-by-step telemetry trace and self-healing reflexion.
        """
        traces: List[TraceStep] = []
        step_counter = 1
        start_total = time.time()
        conversation_history = conversation_history or []

        # -------------------------------------------------------------
        # STEP 1: Supervisor Agent (Intent Routing & RAG Selection)
        # -------------------------------------------------------------
        t0 = time.time()
        routed_domains = rag_engine.route_query_domains(message)
        retrieved_chunks = rag_engine.retrieve_relevant_context(message, top_k=3)
        t_supervisor = (time.time() - t0) * 1000

        traces.append(TraceStep(
            step_num=step_counter,
            agent_name="SupervisorAgent",
            action=f"Routed intent to domains: {', '.join(routed_domains).upper()}",
            details=f"Retrieved {len(retrieved_chunks)} semantic knowledge chunks from assignment docs.",
            latency_ms=t_supervisor,
            status="SUCCESS"
        ))
        step_counter += 1

        # -------------------------------------------------------------
        # STEP 2: SQL Architect Agent (NL-to-SQL Generation)
        # -------------------------------------------------------------
        t0 = time.time()
        try:
            llm_output = self.llm_engine.generate_response(
                user_info=user_info,
                message=message,
                conversation_history=conversation_history,
                provider_override=provider_override,
                api_key_override=api_key_override
            )
            t_sql = (time.time() - t0) * 1000
            draft_sql = llm_output.get("sql")

            traces.append(TraceStep(
                step_num=step_counter,
                agent_name="SQLArchitectAgent",
                action="Generated structured SQL & preliminary insight",
                details=f"SQL: {draft_sql}" if draft_sql else "Conversational response (No SQL required).",
                latency_ms=t_sql,
                status="SUCCESS"
            ))
            step_counter += 1
        except Exception as e:
            t_err = (time.time() - t0) * 1000
            traces.append(TraceStep(
                step_num=step_counter,
                agent_name="SQLArchitectAgent",
                action="Model generation failed",
                details=str(e),
                latency_ms=t_err,
                status="FAILED"
            ))
            raise e

        # If conversational only (greeting/out-of-scope)
        if not draft_sql:
            return {
                "success": True,
                "sql": None,
                "explanation": llm_output.get("explanation", "How can I assist you with commercial analytics?"),
                "data": None,
                "chart": ChartConfig(chart_type="none"),
                "suggestions": llm_output.get("suggestions", []),
                "rag_sources": retrieved_chunks,
                "traces": [t.to_dict() for t in traces],
                "security_notice": None,
                "error": None
            }

        # -------------------------------------------------------------
        # STEP 3: Security & Compliance Guardrail Agent (AST & RBAC)
        # -------------------------------------------------------------
        t0 = time.time()
        is_valid, sec_error, sanitized_sql = validate_and_sanitize_sql(draft_sql, user_info)
        t_sec = (time.time() - t0) * 1000

        if not is_valid:
            traces.append(TraceStep(
                step_num=step_counter,
                agent_name="SecurityGuardrailAgent",
                action="RBAC / AST Security Policy Enforced (Blocked)",
                details=sec_error or "Access violation detected.",
                latency_ms=t_sec,
                status="GUARDRAIL_APPLIED"
            ))
            return {
                "success": False,
                "sql": draft_sql,
                "explanation": sec_error or "Access denied by security policy.",
                "data": None,
                "chart": ChartConfig(chart_type="none"),
                "suggestions": ["Show volume in pack units instead", "Show my assigned territory accounts"],
                "rag_sources": retrieved_chunks,
                "traces": [t.to_dict() for t in traces],
                "security_notice": sec_error,
                "error": sec_error
            }

        traces.append(TraceStep(
            step_num=step_counter,
            agent_name="SecurityGuardrailAgent",
            action="Security Validation Passed",
            details=f"Scope: {user_info.get('role').upper()} (Territory: {user_info.get('territory_name') or 'Global'}), WAC check PASSED, AST check PASSED.",
            latency_ms=t_sec,
            status="SUCCESS"
        ))
        step_counter += 1

        # -------------------------------------------------------------
        # STEP 4: DB Execution & Self-Healing Reflexion Loop
        # -------------------------------------------------------------
        t0 = time.time()
        rows, exec_time_ms, cols = None, 0.0, []
        max_retries = 2
        active_sql = sanitized_sql
        execution_success = False
        db_error_msg = None

        for attempt in range(max_retries):
            try:
                rows, exec_time_ms, cols = execute_query(active_sql)
                execution_success = True
                break
            except Exception as db_exc:
                db_error_msg = str(db_exc)
                traces.append(TraceStep(
                    step_num=step_counter,
                    agent_name="ExecutionReflexionAgent",
                    action=f"SQLite execution failed on attempt {attempt+1}",
                    details=f"Error: {db_error_msg}. Triggering self-correction...",
                    latency_ms=(time.time() - t0) * 1000,
                    status="RETRIED"
                ))
                step_counter += 1

                # Self-healing attempt: Ask SQL Architect to fix the specific error
                try:
                    fix_prompt = f"The previous SQL query failed with error: '{db_error_msg}'. Original SQL: {active_sql}. Fix the query for SQLite."
                    fixed_output = self.llm_engine.generate_response(
                        user_info=user_info,
                        message=fix_prompt,
                        conversation_history=conversation_history,
                        provider_override=provider_override,
                        api_key_override=api_key_override
                    )
                    fixed_sql = fixed_output.get("sql")
                    if fixed_sql:
                        _, _, active_sql = validate_and_sanitize_sql(fixed_sql, user_info)
                except Exception:
                    break

        if not execution_success:
            traces.append(TraceStep(
                step_num=step_counter,
                agent_name="DatabaseEngine",
                action="Database execution failed after self-healing",
                details=db_error_msg,
                latency_ms=(time.time() - t0) * 1000,
                status="FAILED"
            ))
            return {
                "success": False,
                "sql": active_sql,
                "explanation": f"I encountered a database execution error: {db_error_msg}",
                "data": None,
                "chart": ChartConfig(chart_type="none"),
                "suggestions": ["Try rephrasing your question", "Show top products overall"],
                "rag_sources": retrieved_chunks,
                "traces": [t.to_dict() for t in traces],
                "security_notice": None,
                "error": db_error_msg
            }

        traces.append(TraceStep(
            step_num=step_counter,
            agent_name="DatabaseEngine",
            action="Query Executed Successfully",
            details=f"Returned {len(rows)} records in {exec_time_ms}ms.",
            latency_ms=exec_time_ms,
            status="SUCCESS"
        ))
        step_counter += 1

        # -------------------------------------------------------------
        # STEP 5: Executive Insights & Visualization Agent
        # -------------------------------------------------------------
        t0 = time.time()
        clean_rows = filter_response_data(rows, user_info)
        clean_cols = [c for c in cols if "wac" not in c.lower()] if not user_info.get("can_view_wac") else cols

        query_data = QueryResult(
            columns=clean_cols,
            rows=clean_rows,
            row_count=len(clean_rows),
            execution_time_ms=exec_time_ms
        )

        explanation = llm_output.get("explanation", "Here are the commercial analytics results.")
        chart_type = llm_output.get("chart_type", "none")
        x_key = llm_output.get("x_key")
        y_keys = llm_output.get("y_keys")
        suggestions = llm_output.get("suggestions", [])

        # 0-row handling vs dynamic insight generation
        if len(clean_rows) == 0:
            explanation = "No matching records were found for this specific filter criteria in the database. You may want to broaden your search or adjust the timeframe."
            if not suggestions:
                suggestions = ["Show overall top accounts", "Show all products this quarter", "Check last 6 months trend"]
        else:
            # If query returned data, produce an executive summary if the LLM explanation was generic
            if len(clean_rows) > 0 and len(clean_cols) >= 2:
                first_row = clean_rows[0]
                last_row = clean_rows[-1]
                val_col = clean_cols[1]
                label_col = clean_cols[0]
                
                # If monthly trend data, summarize start, end, and peak
                if "mo" in label_col.lower() or "month" in label_col.lower() or "period" in label_col.lower():
                    total_vol = sum(r.get(val_col, 0) or 0 for r in clean_rows)
                    peak_row = max(clean_rows, key=lambda r: (r.get(val_col, 0) or 0))
                    explanation = f"Here is the monthly volume trend across {len(clean_rows)} months. Total volume reached {total_vol:,.0f} pack units, peaking in {peak_row.get(label_col)} with {peak_row.get(val_col):,.0f} units."
                elif len(clean_rows) == 1:
                    explanation = f"Analysis result: {first_row.get(label_col, 'Item')} recorded {first_row.get(val_col, 'N/A')} across the selected period."
                
            if chart_type == "none" and len(clean_rows) > 0 and len(clean_cols) >= 2:
                chart_type = "line" if ("mo" in clean_cols[0].lower() or "date" in clean_cols[0].lower() or "period" in clean_cols[0].lower()) else ("bar" if len(clean_rows) <= 15 else "table")
                x_key = clean_cols[0]
                y_keys = [clean_cols[1]]

        chart_config = ChartConfig(
            chart_type=chart_type or "none",
            x_key=x_key,
            y_keys=y_keys,
            title=f"Analysis for: {message[:50]}..."
        )

        t_insight = (time.time() - t0) * 1000
        traces.append(TraceStep(
            step_num=step_counter,
            agent_name="ExecutiveInsightsAgent",
            action="Synthesized business insights & chart configuration",
            details=f"Chart: {chart_type.upper()}, Metric keys: {y_keys}",
            latency_ms=t_insight,
            status="SUCCESS"
        ))

        return {
            "success": True,
            "sql": active_sql,
            "explanation": explanation,
            "data": query_data,
            "chart": chart_config,
            "suggestions": suggestions,
            "rag_sources": retrieved_chunks,
            "traces": [t.to_dict() for t in traces],
            "security_notice": None,
            "error": None
        }


# Global singleton Multi-Agent Harness
agent_harness = MultiAgentHarness()
