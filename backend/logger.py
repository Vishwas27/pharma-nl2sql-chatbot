"""
Structured Logging Module for NovaPharma Commercial Analytics Assistant.
Logs interactions, SQL queries, execution metrics, and detailed errors to console and file (app.log).
Also maintains an in-memory buffer of recent logs for the UI Log Viewer.
"""

import os
import sys
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).parent.parent
LOG_FILE_PATH = BASE_DIR / "app.log"

# In-memory circular log buffer for UI inspection (last 100 entries)
MEMORY_LOGS: List[Dict[str, Any]] = []
MAX_MEMORY_LOGS = 150


def setup_logger():
    """Configure system logger for file and console outputs with UTF-8 encoding."""
    logger = logging.getLogger("novapharma")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File Handler
    file_handler = logging.FileHandler(str(LOG_FILE_PATH), mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Stream Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


logger = setup_logger()


def log_interaction(
    user_name: str,
    user_role: str,
    question: str,
    provider: str,
    sql: str = None,
    row_count: int = 0,
    execution_time_ms: float = 0.0,
    error: str = None
):
    """Record an interaction event in file, console, and in-memory buffer."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "ERROR" if error else "SUCCESS"

    entry = {
        "timestamp": now_str,
        "status": status,
        "user": f"{user_name} ({user_role.upper()})",
        "question": question,
        "provider": provider,
        "sql": sql,
        "row_count": row_count,
        "latency_ms": execution_time_ms,
        "error": error
    }

    # Add to in-memory buffer
    MEMORY_LOGS.insert(0, entry)
    if len(MEMORY_LOGS) > MAX_MEMORY_LOGS:
        MEMORY_LOGS.pop()

    # Log to system logger
    if error:
        logger.error(
            f"USER='{user_name}' ROLE='{user_role}' QUESTION='{question}' "
            f"PROVIDER='{provider}' STATUS=FAILED ERROR='{error}'"
        )
    else:
        logger.info(
            f"USER='{user_name}' ROLE='{user_role}' QUESTION='{question}' "
            f"PROVIDER='{provider}' SQL='{sql}' ROWS={row_count} TIME={execution_time_ms}ms"
        )


def get_recent_logs() -> List[Dict[str, Any]]:
    """Retrieve recent in-memory logs for the frontend UI."""
    return MEMORY_LOGS


def clear_logs():
    """Clear memory and file logs."""
    global MEMORY_LOGS
    MEMORY_LOGS.clear()
    with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Logs reset.\n")
