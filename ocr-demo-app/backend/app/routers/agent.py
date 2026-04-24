from fastapi import APIRouter, Query

from ..models.agent import AgentRequest, AgentResponse
from ..services.agent_service import ask_agent

router = APIRouter()


@router.post("/ask", response_model=AgentResponse)
async def ask_agent_question(request: AgentRequest) -> AgentResponse:
    return ask_agent(request)


@router.get("/ask", response_model=AgentResponse)
async def ask_agent_question_get(
    session_id: str = Query(..., description="OCR session ID"),
    question: str = Query(..., description="Question to ask about the OCR session"),
) -> AgentResponse:
    request = AgentRequest(session_id=session_id, question=question)
    return ask_agent(request)ml)
