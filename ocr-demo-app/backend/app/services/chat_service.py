import logging
from typing import List, Dict, Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import get_settings
from ..models.chat import ChatResponse, ChatSource
from ..processing.ocr.bedrock_engine import (
    get_bedrock_client,
    bedrock_converse,
    BEDROCK_MODELS,
)
from .vector_store import (
    add_session_documents,
    delete_session_documents,
    search_legal,
    search_session,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _safe_snippet(text: str, max_len: int = 240) -> str:
    text = " ".join((text or "").split())
    return text[:max_len]


def _format_docs_for_prompt(docs: List[Document]) -> str:
    blocks = []
    for idx, doc in enumerate(docs, start=1):
        source_name = doc.metadata.get("source_name", "Unknown Source")
        page = doc.metadata.get("page")
        source_type = doc.metadata.get("source_type", "unknown")
        blocks.append(
            f"[{idx}] type={source_type} source={source_name} page={page}\n{doc.page_content}"
        )
    return "\n\n".join(blocks)


def _build_sources(docs: List[Document]) -> List[ChatSource]:
    sources: List[ChatSource] = []
    seen = set()

    for doc in docs:
        source_name = doc.metadata.get("source_name", "Unknown Source")
        page = doc.metadata.get("page")
        source_type = doc.metadata.get("source_type", "unknown")
        key = (source_type, source_name, page, doc.page_content[:100])
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            ChatSource(
                source_type=source_type,
                source_name=source_name,
                page=page,
                snippet=_safe_snippet(doc.page_content),
            )
        )
    return sources


def index_session_payload(
    session_id: str,
    source_name: str,
    detected_form_type: str,
    page_entries: List[Dict[str, Any]],
    classified_fields: List[Dict[str, Any]],
) -> None:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.text_chunk_size,
        chunk_overlap=settings.text_chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    docs: List[Document] = []

    for entry in page_entries or []:
        page_num = entry.get("page")
        text = (entry.get("text") or "").strip()
        if not text:
            continue

        base_doc = Document(
            page_content=text,
            metadata={
                "session_id": session_id,
                "source_type": "ocr_page",
                "source_name": source_name,
                "page": page_num,
                "form_type": detected_form_type or "unknown",
            },
        )
        docs.extend(splitter.split_documents([base_doc]))

    for field in classified_fields or []:
        if isinstance(field, dict):
            field_name = str(field.get("field_type", "")).strip()
            field_value = field.get("value")
            page_num = field.get("page", 1)
        else:
            continue

        if not field_name or field_value in [None, ""]:
            continue

        docs.append(
            Document(
                page_content=f"{field_name.replace('_', ' ').title()}: {field_value}",
                metadata={
                    "session_id": session_id,
                    "source_type": "ocr_field",
                    "source_name": source_name,
                    "page": page_num,
                    "field_name": field_name,
                    "form_type": detected_form_type or "unknown",
                },
            )
        )

    delete_session_documents(session_id)
    add_session_documents(docs)
    logger.info("Indexed %s session documents for session_id=%s", len(docs), session_id)


def ask_question(session_id: str, question: str) -> ChatResponse:
    session_docs = search_session(session_id, question, k=settings.session_top_k)
    legal_docs = search_legal(question, k=settings.legal_top_k)

    if not session_docs and not legal_docs:
        return ChatResponse(
            answer="I do not have enough information to answer that question for this session.",
            sources=[],
        )

    session_context = _format_docs_for_prompt(session_docs)
    legal_context = _format_docs_for_prompt(legal_docs)

    prompt = f"""
You are an OCR Assistant for a document processing application.

Answer the user's question using ONLY:
1. OCR content from the current session
2. Legal/reference documents

Rules:
- Prioritize the current session OCR content for case-specific facts.
- Use legal documents for policy, rules, or guidance.
- Do not invent missing facts.
- If the answer is not supported, say that clearly.
- Keep the answer concise and useful.
- If relevant, mention where the answer came from.

CURRENT SESSION OCR CONTEXT:
{session_context}

LEGAL / REFERENCE CONTEXT:
{legal_context}

QUESTION:
{question}
""".strip()

    model_name = settings.chat_model_name
    if model_name not in BEDROCK_MODELS:
        model_name = "claude_bedrock"

    client = get_bedrock_client()
    model_id = BEDROCK_MODELS[model_name]

    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}],
        }
    ]

    answer = bedrock_converse(
        client,
        model_id,
        messages,
        max_tokens=2048,
        engine_name=model_name,
    )

    sources = _build_sources(session_docs + legal_docs)

    return ChatResponse(answer=answer, sources=sources)
