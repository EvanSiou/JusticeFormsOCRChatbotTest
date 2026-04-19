from typing import Optional, List
from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    question: str


class ChatSource(BaseModel):
    source_type: str
    source_name: str
    page: Optional[int] = None
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: List[ChatSource] = []
