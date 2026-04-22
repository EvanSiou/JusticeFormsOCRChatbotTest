from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AgentRequest(BaseModel):
    session_id: str
    question: str


class AgentSource(BaseModel):
    source_type: str
    source_name: str
    page: Optional[int] = None
    snippet: str


class AgentToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]


class AgentToolResult(BaseModel):
    tool_name: str
    result: Dict[str, Any]


class AgentResponse(BaseModel):
    answer: str
    tool_calls: List[AgentToolCall] = []
    tool_results: List[AgentToolResult] = []
    sources: List[AgentSource] = []
