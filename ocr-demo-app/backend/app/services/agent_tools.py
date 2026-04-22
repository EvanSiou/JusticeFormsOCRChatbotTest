import json
from typing import Any, Dict, List

from ..models.agent import AgentSource
from . import dynamodb
from .vector_store import search_legal, search_session


def _safe_snippet(text: str, max_len: int = 240) -> str:
    text = " ".join((text or "").split())
    return text[:max_len]


def get_session_overview(session_id: str) -> Dict[str, Any]:
    session = dynamodb.get_session(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    return {
        "session_id": session_id,
        "original_filename": session.get("original_filename"),
        "status": session.get("status"),
        "page_count": session.get("page_count"),
        "detected_form_type": session.get("detected_form_type"),
        "selected_model": session.get("selected_model"),
        "summary_stats": session.get("summary_stats"),
    }


def get_classified_fields(session_id: str) -> Dict[str, Any]:
    session = dynamodb.get_session(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    return {
        "session_id": session_id,
        "original_filename": session.get("original_filename"),
        "detected_form_type": session.get("detected_form_type"),
        "classified_fields": session.get("classified_fields_original", []),
        "display_fields": session.get("classified_fields_display", []),
    }


def get_quality_results(session_id: str) -> Dict[str, Any]:
    session = dynamodb.get_session(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    pages = session.get("pages", [])
    quality_results = []
    for page in pages:
        quality_results.append(
            {
                "page_num": page.get("page_num"),
                "quality_score": page.get("quality_score"),
                "quality_passed": page.get("quality_passed"),
                "quality_details": page.get("quality_details"),
            }
        )

    return {
        "session_id": session_id,
        "quality_results": quality_results,
    }


def search_session_context(session_id: str, query: str, k: int = 5) -> Dict[str, Any]:
    docs = search_session(session_id=session_id, question=query, k=k)

    results = []
    sources = []
    for doc in docs:
        source_name = doc.metadata.get("source_name", "Unknown Source")
        page = doc.metadata.get("page")
        source_type = doc.metadata.get("source_type", "ocr_session")
        snippet = _safe_snippet(doc.page_content)

        results.append(
            {
                "source_type": source_type,
                "source_name": source_name,
                "page": page,
                "snippet": snippet,
                "content": doc.page_content,
            }
        )

        sources.append(
            AgentSource(
                source_type=source_type,
                source_name=source_name,
                page=page,
                snippet=snippet,
            )
        )

    return {
        "query": query,
        "results": results,
        "sources": [s.model_dump() for s in sources],
    }


def search_legal_docs(query: str, k: int = 4) -> Dict[str, Any]:
    docs = search_legal(question=query, k=k)

    results = []
    sources = []
    for doc in docs:
        source_name = doc.metadata.get("source_name", "Unknown Source")
        page = doc.metadata.get("page")
        source_type = doc.metadata.get("source_type", "legal_doc")
        snippet = _safe_snippet(doc.page_content)

        results.append(
            {
                "source_type": source_type,
                "source_name": source_name,
                "page": page,
                "snippet": snippet,
                "content": doc.page_content,
            }
        )

        sources.append(
            AgentSource(
                source_type=source_type,
                source_name=source_name,
                page=page,
                snippet=snippet,
            )
        )

    return {
        "query": query,
        "results": results,
        "sources": [s.model_dump() for s in sources],
    }


AVAILABLE_TOOLS = {
    "get_session_overview": get_session_overview,
    "get_classified_fields": get_classified_fields,
    "get_quality_results": get_quality_results,
    "search_session_context": search_session_context,
    "search_legal_docs": search_legal_docs,
}


def get_tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "tool_name": "get_session_overview",
            "description": "Get high-level information about the current OCR session.",
            "arguments": {
                "session_id": "string"
            },
        },
        {
            "tool_name": "get_classified_fields",
            "description": "Get extracted/classified fields for the current OCR session.",
            "arguments": {
                "session_id": "string"
            },
        },
        {
            "tool_name": "get_quality_results",
            "description": "Get quality detection / page quality results for the current OCR session.",
            "arguments": {
                "session_id": "string"
            },
        },
        {
            "tool_name": "search_session_context",
            "description": "Search OCR text and indexed OCR content for the current session.",
            "arguments": {
                "session_id": "string",
                "query": "string",
                "k": "integer optional"
            },
        },
        {
            "tool_name": "search_legal_docs",
            "description": "Search the permanent legal/reference document knowledge base.",
            "arguments": {
                "query": "string",
                "k": "integer optional"
            },
        },
    ]


def execute_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    fn = AVAILABLE_TOOLS.get(tool_name)
    if not fn:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return fn(**arguments)
    except Exception as e:
        return {"error": f"Tool execution failed for {tool_name}: {str(e)}"}
