from fastapi import APIRouter, Query

from ..models.chat import ChatRequest, ChatResponse
from ..services.chat_service import ask_question

router = APIRouter()


@router.post("/ask", response_model=ChatResponse)
async def ask_chat_question(request: ChatRequest) -> ChatResponse:
    return ask_question(request.session_id, request.question)


@router.get("/ask", response_model=ChatResponse)
async def ask_chat_question_get(
    session_id: str = Query(..., description="OCR session ID"),
    question: str = Query(..., description="Question to ask about the OCR session"),
) -> ChatResponse:
    return ask_question(session_id, question)
    return HTMLResponse(content=html)
