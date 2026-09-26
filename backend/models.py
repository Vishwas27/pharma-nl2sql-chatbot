"""
Pydantic Schemas for Request & Response models.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message text")
    sql: Optional[str] = Field(None, description="Generated SQL if applicable")


class ChatRequest(BaseModel):
    user_id: str = Field(..., description="User ID or email (e.g. 'U001', 'sarah.chen@novapharma.com')")
    message: str = Field(..., description="Natural language question from user")
    conversation_history: Optional[List[ChatMessage]] = Field(default_factory=list, description="Previous messages for multi-turn context")
    api_provider: Optional[str] = Field(default=None, description="Optional override: 'gemini', 'openai', 'groq', 'offline'")
    api_key: Optional[str] = Field(default=None, description="Optional runtime API key")


class QueryResult(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0


class ChartConfig(BaseModel):
    chart_type: str = Field("none", description="'bar', 'line', 'pie', 'table', 'none'")
    x_key: Optional[str] = None
    y_keys: Optional[List[str]] = None
    title: Optional[str] = None


class ChatResponse(BaseModel):
    success: bool
    user_id: str
    user_name: str
    user_role: str
    territory: Optional[str] = None
    region: Optional[str] = None
    can_view_wac: bool
    
    question: str
    sql: Optional[str] = None
    explanation: str
    data: Optional[QueryResult] = None
    chart: Optional[ChartConfig] = None
    suggestions: List[str] = Field(default_factory=list)
    rag_sources: List[Dict[str, Any]] = Field(default_factory=list, description="Retrieved RAG domain knowledge chunks")
    traces: List[Dict[str, Any]] = Field(default_factory=list, description="Multi-Agent runtime execution trace")
    security_notice: Optional[str] = None
    error: Optional[str] = None
