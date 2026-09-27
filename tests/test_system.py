"""
Comprehensive Automated Test Suite for NovaPharma Commercial Analytics Assistant.
Standard library unittest implementation for zero-dependency test execution.
"""

import unittest
import sqlite3
from pathlib import Path

from backend.db import init_database, execute_query, get_user_by_id_or_email, get_all_users
from backend.security import validate_and_sanitize_sql, filter_response_data
from backend.llm_engine import LLMEngine
from backend.models import ChatRequest
from backend.app import handle_chat_query


class TestNovaPharmaSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_01_database_tables(self):
        conn = sqlite3.connect("pharma.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        conn.close()

        self.assertIn("sales", tables)
        self.assertIn("organizations", tables)
        self.assertIn("products", tables)
        self.assertIn("zip_territory", tables)
        self.assertIn("users", tables)

    def test_02_user_profiles_and_roles(self):
        users = get_all_users()
        self.assertGreaterEqual(len(users), 15)

        # Sarah Chen is Exec
        exec_user = get_user_by_id_or_email("sarah.chen@novapharma.com")
        self.assertIsNotNone(exec_user)
        self.assertEqual(exec_user["role"], "exec")
        self.assertEqual(exec_user["can_view_wac"], 1)

        # Jennifer Walsh is Director of Northeast
        director_user = get_user_by_id_or_email("jennifer.walsh@novapharma.com")
        self.assertIsNotNone(director_user)
        self.assertEqual(director_user["role"], "director")
        self.assertEqual(director_user["region_name"], "Northeast")
        self.assertEqual(director_user["can_view_wac"], 0)

        # Amy Nguyen is RAM of New York Metro
        ram_user = get_user_by_id_or_email("amy.nguyen@novapharma.com")
        self.assertIsNotNone(ram_user)
        self.assertEqual(ram_user["role"], "ram")
        self.assertEqual(ram_user["territory_name"], "New York Metro")
        self.assertEqual(ram_user["can_view_wac"], 0)

    def test_03_sql_injection_and_mutations_blocked(self):
        exec_user = get_user_by_id_or_email("U001")

        bad_queries = [
            "DROP TABLE sales;",
            "DELETE FROM organizations WHERE 1=1;",
            "UPDATE products SET brand_flag = 1;",
            "INSERT INTO users VALUES ('x', 'y', 'z', 'exec', null, null, 1);",
            "SELECT * FROM sales; DROP TABLE users;",
            "PRAGMA table_info(sales);"
        ]

        for bq in bad_queries:
            is_valid, err, _ = validate_and_sanitize_sql(bq, exec_user)
            self.assertFalse(is_valid, f"Query should have been rejected: {bq}")
            self.assertIsNotNone(err)

    def test_04_wac_access_blocked_for_ram_and_director(self):
        ram_user = get_user_by_id_or_email("U009")  # Amy Nguyen
        director_user = get_user_by_id_or_email("U003")  # Jennifer Walsh
        exec_user = get_user_by_id_or_email("U001")  # Sarah Chen

        wac_query = "SELECT drug_name, SUM(wac) as rev FROM sales GROUP BY drug_name"

        # RAM should be blocked
        is_valid_ram, err_ram, _ = validate_and_sanitize_sql(wac_query, ram_user)
        self.assertFalse(is_valid_ram)
        self.assertTrue("WAC" in err_ram or "restricted" in err_ram)

        # Director should be blocked
        is_valid_dir, err_dir, _ = validate_and_sanitize_sql(wac_query, director_user)
        self.assertFalse(is_valid_dir)
        self.assertTrue("WAC" in err_dir or "restricted" in err_dir)

        # Exec should be allowed
        is_valid_exec, err_exec, clean_sql = validate_and_sanitize_sql(wac_query, exec_user)
        self.assertTrue(is_valid_exec)
        self.assertIsNone(err_exec)
        self.assertIn("SELECT", clean_sql)

    def test_05_cross_territory_access_blocked_for_ram(self):
        ram_user = get_user_by_id_or_email("U009")  # New York Metro
        cross_query = "SELECT * FROM zip_territory WHERE territory_name = 'Texas'"

        is_valid, err, _ = validate_and_sanitize_sql(cross_query, ram_user)
        self.assertFalse(is_valid)
        self.assertIn("Access Denied", err)

    def test_06_live_gemini_market_share_query(self):
        req = ChatRequest(
            user_id="U001",  # Sarah Chen (Exec)
            message="What is our market share for Zenovax in Docetaxel?"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        self.assertIsNotNone(resp.sql)
        self.assertIn("sales", resp.sql.lower())
        self.assertIsNotNone(resp.data)

    def test_07_live_gemini_top_products_query(self):
        req = ChatRequest(
            user_id="U001",  # Sarah Chen (Exec)
            message="Tell me about top 2 products by volume"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        self.assertIsNotNone(resp.sql)
        self.assertIsNotNone(resp.data)
        self.assertLessEqual(resp.data.row_count, 2)

    def test_08_missing_api_key_error_handling(self):
        req = ChatRequest(
            user_id="U001",
            message="Show all accounts",
            api_provider="openai",
            api_key=""
        )
        resp = handle_chat_query(req)
        self.assertFalse(resp.success)
        self.assertIn("No API key found", resp.error or resp.explanation)

    def test_09_invalid_api_key_server_error_handling(self):
        req = ChatRequest(
            user_id="U001",
            message="Show all accounts",
            api_provider="gemini",
            api_key="INVALID_KEY_9999"
        )
        resp = handle_chat_query(req)
        self.assertFalse(resp.success)
        self.assertIn("Server not working", resp.error or resp.explanation)

    def test_10_ram_wac_access_blocked_guardrail(self):
        req = ChatRequest(
            user_id="U009",  # Amy Nguyen (RAM)
            message="What are my top 5 accounts by pack units?"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        self.assertFalse(resp.can_view_wac)
        if resp.data and len(resp.data.rows) > 0:
            for col in resp.data.columns:
                self.assertNotIn("wac", col.lower())

    def test_11_multi_domain_rag_indexing_and_routing(self):
        from backend.rag_engine import rag_engine
        summary = rag_engine.get_indexed_summary()
        self.assertGreater(summary["total_chunks"], 0)
        self.assertIn("metrics", summary["domains"])
        self.assertIn("products", summary["domains"])
        self.assertIn("accounts_and_sources", summary["domains"])

        # Test Domain Routing
        metric_domains = rag_engine.route_query_domains("What is our market share for Zenovax?")
        self.assertIn("metrics", metric_domains)
        self.assertIn("products", metric_domains)

        account_domains = rag_engine.route_query_domains("Show top 340B hospitals and IDN grandparents")
        self.assertIn("accounts_and_sources", account_domains)

        # Test Semantic Chunk Retrieval
        chunks = rag_engine.retrieve_relevant_context("market share docetaxel formula", top_k=2)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("domain", chunks[0])
        self.assertIn("source_file", chunks[0])

    def test_12_rag_sources_attached_to_chat_response(self):
        req = ChatRequest(
            user_id="U001",
            message="What is the market share for Zenovax this quarter?"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        self.assertIsInstance(resp.rag_sources, list)
        if resp.rag_sources:
            self.assertTrue(any(s["domain"] in ["metrics", "products", "accounts_and_sources"] for s in resp.rag_sources))

    def test_13_multi_turn_conversational_drilldown(self):
        from backend.models import ChatMessage
        # Turn 1: Top accounts for Zenovax
        req1 = ChatRequest(
            user_id="U001",
            message="Show top 3 accounts for Zenovax this quarter"
        )
        resp1 = handle_chat_query(req1)
        self.assertTrue(resp1.success)
        self.assertIsNotNone(resp1.sql)

        # Turn 2: Follow-up drill-down "Break that down by month"
        history = [
            ChatMessage(role="user", content=req1.message),
            ChatMessage(role="assistant", content=resp1.explanation, sql=resp1.sql)
        ]
        req2 = ChatRequest(
            user_id="U001",
            message="Break that down by month",
            conversation_history=history
        )
        resp2 = handle_chat_query(req2)
        self.assertTrue(resp2.success)
        self.assertIsNotNone(resp2.sql)
        # Should include period_mo or mo_offset in grouping or select
        sql_lower = resp2.sql.lower()
        self.assertTrue("mo" in sql_lower or "month" in sql_lower or "date" in sql_lower)

    def test_14_zero_row_graceful_handling(self):
        # Impossible query yielding 0 rows
        req = ChatRequest(
            user_id="U001",
            message="Show sales for NonExistentDrug12345 in 2099"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        if resp.data:
            self.assertEqual(resp.data.row_count, 0)
        self.assertIsNotNone(resp.explanation)

    def test_15_multi_turn_security_scoping_holds(self):
        from backend.models import ChatMessage
        # RAM asks initial question
        history = [
            ChatMessage(role="user", content="Show my top accounts"),
            ChatMessage(role="assistant", content="Here are your top accounts in New York Metro.", sql="SELECT ... WHERE territory_name = 'New York Metro'")
        ]
        # RAM tries to drill into Texas in follow-up
        req = ChatRequest(
            user_id="U009",  # Amy Nguyen (New York Metro RAM)
            message="Now show all accounts in Texas instead",
            conversation_history=history
        )
        resp = handle_chat_query(req)
        # Security guardrail should block or restrict to New York Metro
        if resp.data and len(resp.data.rows) > 0:
            for row in resp.data.rows:
                self.assertNotEqual(row.get("territory_name"), "Texas")

    def test_16_multi_agent_harness_execution_trace(self):
        req = ChatRequest(
            user_id="U001",
            message="What are our top 3 products by volume this quarter?"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        self.assertIsInstance(resp.traces, list)
        self.assertGreaterEqual(len(resp.traces), 4)

        agent_names = [t["agent"] for t in resp.traces]
        self.assertIn("SupervisorAgent", agent_names)
        self.assertIn("SQLArchitectAgent", agent_names)
        self.assertIn("SecurityGuardrailAgent", agent_names)
        self.assertIn("DatabaseEngine", agent_names)
        self.assertIn("ExecutiveInsightsAgent", agent_names)

    def test_17_multi_agent_harness_conversational_turn(self):
        req = ChatRequest(
            user_id="U001",
            message="Hello, what can you do?"
        )
        resp = handle_chat_query(req)
        self.assertTrue(resp.success)
        self.assertIsNone(resp.sql)
        self.assertGreaterEqual(len(resp.traces), 2)


if __name__ == "__main__":
    unittest.main()
