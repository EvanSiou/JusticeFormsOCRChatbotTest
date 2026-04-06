"""LLM-based document quality detection using Bedrock."""
import json
import logging
from PIL import Image

from .ocr.bedrock_engine import (
    get_bedrock_client, bedrock_converse, prepare_image_for_bedrock,
    BEDROCK_MODELS,
)

logger = logging.getLogger(__name__)

QUALITY_DETECTION_PROMPT = """Analyze this scanned document page for quality issues.

Evaluate:
1. Is the page rotated? If so, how many degrees clockwise to correct (0, 90, 180, or 270)?
2. Is there a slight skew (tilt)? Estimate the clockwise angle in degrees (0 = perfectly straight).
3. How degraded is the image? (contrast loss, noise, blur, stains, fading)
4. What is the overall readability quality?

Return ONLY valid JSON (no markdown, no code fences):
{
  "skew_angle": <float, estimated clockwise tilt in degrees, 0 = straight>,
  "rotation_needed": <int, degrees to rotate to correct: 0, 90, 180, or 270>,
  "degradation_score": <float 0-1, 0=pristine, 1=unreadable>,
  "contrast_quality": <float 0-1, 0=washed out, 1=excellent>,
  "noise_level": <float 0-1, 0=clean, 1=very noisy>,
  "overall_quality_score": <float 0-1, composite readability quality>,
  "issues": ["list of detected quality issues as strings"]
}"""


def detect_page_quality(image: Image.Image, model_name: str = "claude_bedrock") -> dict:
    """Detect quality issues on a single page image.

    Returns dict with skew_angle, rotation_needed, degradation_score, etc.
    """
    if model_name not in BEDROCK_MODELS:
        model_name = "claude_bedrock"

    client = get_bedrock_client()
    model_id = BEDROCK_MODELS[model_name]
    image_bytes, fmt, w, h = prepare_image_for_bedrock(image)

    messages = [{
        "role": "user",
        "content": [
            {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
            {"text": QUALITY_DETECTION_PROMPT},
        ],
    }]

    logger.info(f"Quality detection ({model_name}): {w}x{h}, {len(image_bytes)} bytes")

    response_text = bedrock_converse(
        client, model_id, messages,
        max_tokens=1024, engine_name=model_name,
    )

    # Parse JSON
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        result = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        # Try to find JSON in response
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(response_text[start:end])
            except json.JSONDecodeError:
                result = {}
        else:
            result = {}

    # Fill defaults for missing fields
    defaults = {
        "skew_angle": 0.0,
        "rotation_needed": 0,
        "degradation_score": 0.0,
        "contrast_quality": 1.0,
        "noise_level": 0.0,
        "overall_quality_score": 0.8,
        "issues": [],
    }
    for k, v in defaults.items():
        if k not in result:
            result[k] = v

    return result
