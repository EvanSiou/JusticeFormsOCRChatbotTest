import json
import logging
from typing import Any, Dict, List

from ..config import get_settings
from ..models.agent import (
    AgentRequest,
    AgentResponse,
    AgentSource,
    AgentToolCall,
    AgentToolResult,
)
from ..processing.ocr.bedrock_engine import (
    get_bedrock_client,
    bedrock_converse,
    BEDROCK_MODELS,
)
from .agent_tools import get_tool_schemas, execute_tool_call

logger = logging.getLogger(__name__)
settings = get_settings()


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def _unique_sources(source_dicts: List[Dict[str, Any]]) -> List[AgentSource]:
    seen = set()
    sources: List[AgentSource] = []

    for src in source_dicts:
        key = (
            src.get("source_type"),
            src.get("source_name"),
            src.get("page"),
            src.get("snippet"),
        )
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            AgentSource(
                source_type=src.get("source_type", "unknown"),
                source_name=src.get("source_name", "Unknown Source"),
                page=src.get("page"),
                snippet=src.get("snippet", ""),
            )
        )
    return sources


def _get_model_name() -> str:
    model_name = settings.chat_model_name
    if model_name not in BEDROCK_MODELS:
        return "claude_bedrock"
    return model_name


def plan_tool_calls(session_id: str, question: str) -> List[AgentToolCall]:
    model_name = _get_model_name()
    client = get_bedrock_client()
    model_id = BEDROCK_MODELS[model_name]

    tool_schemas = get_tool_schemas()

    prompt = f"""
You are a tool-using OCR Assistant.

Your job is to decide which tools to call for the current user question.

Rules:
- The assistant is session-based. The session_id is: {session_id}
- Prefer using the current OCR session for case-specific facts.
- Use legal docs for policy/rules/guidance.
- Use only the allowed tools below.
- Return ONLY valid JSON.
- Maximum 4 tool calls.
- If a tool needs session_id, always use the provided session_id.
- Do not answer the question yet. Only decide tool calls.

Allowed tools:
{json.dumps(tool_schemas, indent=2)}

Return JSON in exactly this format:
{{
  "tool_calls": [
    {{
      "tool_name": "search_session_context",
      "arguments": {{
        "session_id": "{session_id}",
        "query": "example query",
        "k": 5
      }}
    }}
  ]
}}

User question:
{question}
""".strip()

    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}],
        }
    ]

    response_text = bedrock_converse(
        client,
        model_id,
        messages,
        max_tokens=1200,
        engine_name=model_name,
    )

    parsed = _extract_json(response_text)
    raw_calls = parsed.get("tool_calls", [])

    tool_calls: List[AgentToolCall] = []
    for item in raw_calls[:4]:
        tool_name = item.get("tool_name")
        arguments = item.get("arguments", {}) or {}

        if "session_id" in arguments:
            arguments["session_id"] = session_id

        tool_calls.append(
            AgentToolCall(
                tool_name=tool_name,
                arguments=arguments,
            )
        )

    return tool_calls


def build_final_answer(session_id: str, question: str, tool_results: List[AgentToolResult]) -> str:
    model_name = _get_model_name()
    client = get_bedrock_client()
    model_id = BEDROCK_MODELS[model_name]

    prompt = f"""
You are an OCR Assistant.

Answer the user's question using ONLY the tool results below.

Rules:
- The session is: {session_id}
- Prioritize the OCR session results for case-specific facts.
- Use legal docs only for guidance/policy/rules.
- Do not invent missing facts.
- If the answer is uncertain or unsupported, say so clearly.
- Keep the answer concise and helpful.

User question:
{question}

Tool results:
{json.dumps([tr.model_dump() for tr in tool_results], indent=2)}
""".strip()

    messages = [
        {
            "role": "user",
            "content": [{"text": prompt}],
        }
    ]

    return bedrock_converse(
        client,
        model_id,
        messages,
        max_tokens=1800,
        engine_name=model_name,
    )


def ask_agent(request: AgentRequest) -> AgentResponse:
    tool_calls = plan_tool_calls(request.session_id, request.question)

    tool_results: List[AgentToolResult] = []
    source_dicts: List[Dict[str, Any]] = []

    for call in tool_calls:
        result = execute_tool_call(call.tool_name, call.arguments)
        tool_results.append(
            AgentToolResult(
                tool_name=call.tool_name,
                result=result,
            )
        )

        result_sources = result.get("sources", [])
        if isinstance(result_sources, list):
            source_dicts.extend(result_sources)

    answer = build_final_answer(
        session_id=request.session_id,
        question=request.question,
        tool_results=tool_results,
    )

    sources = _unique_sources(source_dicts)

    return AgentResponse(
        answer=answer,
        tool_calls=tool_calls,
        tool_results=tool_results,
        sources=sources,
    )
