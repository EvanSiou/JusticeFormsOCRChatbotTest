"""LLM-based form type detection using Bedrock."""
import json
import logging
from PIL import Image

from .ocr.bedrock_engine import (
    get_bedrock_client, bedrock_converse, prepare_image_for_bedrock,
    BEDROCK_MODELS,
)

logger = logging.getLogger(__name__)

FORM_DETECTION_PROMPT = """Look at this document image and identify what type of form it is.

Known form types:
{form_types_list}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "detected_form_type": "<the form_type_id that best matches, or 'unknown'>",
  "confidence": <float 0-1>,
  "reasoning": "<brief explanation>"
}}"""


def detect_form_type(
    image: Image.Image,
    known_form_types: list[dict],
    model_name: str = "claude_bedrock",
) -> dict:
    """Identify the form type from the first page image.

    Args:
        image: First page of the document
        known_form_types: List of dicts with form_type_id and display_name
        model_name: Bedrock model to use

    Returns:
        Dict with detected_form_type, confidence, reasoning
    """
    if model_name not in BEDROCK_MODELS:
        model_name = "claude_bedrock"

    # Build form types list for the prompt
    type_lines = []
    for ft in known_form_types:
        type_lines.append(f"- {ft['form_type_id']}: {ft.get('display_name', ft['form_type_id'])}")
    types_str = "\n".join(type_lines) if type_lines else "- (no registered form types)"

    prompt = FORM_DETECTION_PROMPT.replace("{form_types_list}", types_str)

    client = get_bedrock_client()
    model_id = BEDROCK_MODELS[model_name]
    image_bytes, fmt, w, h = prepare_image_for_bedrock(image)

    messages = [{
        "role": "user",
        "content": [
            {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
            {"text": prompt},
        ],
    }]

    logger.info(f"Form detection ({model_name}): {w}x{h}")

    response_text = bedrock_converse(
        client, model_id, messages,
        max_tokens=512, engine_name=model_name,
    )

    # Parse JSON
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        result = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(response_text[start:end])
            except json.JSONDecodeError:
                result = {"detected_form_type": "unknown", "confidence": 0.0, "reasoning": "Could not parse response"}
        else:
            result = {"detected_form_type": "unknown", "confidence": 0.0, "reasoning": "No JSON in response"}

    return result
