"""
Amazon Bedrock field classifier.

Uses shared Bedrock client and rate limiter from ocr.bedrock_engine.
Adapted from eCourtDateOCR — removed cross-import, uses shared functions.
"""
import json
import logging
from typing import List, Optional
from PIL import Image

from ..ocr.bedrock_engine import (
    BEDROCK_MODELS, get_bedrock_client, bedrock_converse,
    prepare_image_for_bedrock, MODEL_REQUEST_DELAY,
)
from .normalize import normalize_classification_response

logger = logging.getLogger(__name__)

BEDROCK_MAX_TOKENS = {
    "claude_bedrock": 16384,
    "claude_haiku_bedrock": 16384,
    "nova_pro_bedrock": 5120,
    "nova_lite_bedrock": 5120,
    "pixtral_large_bedrock": 8192,
    "llama4_maverick_bedrock": 8192,
    "llama4_scout_bedrock": 8192,
}


class BedrockFieldClassifier:
    """Field classification using Amazon Bedrock Converse API."""

    def __init__(self, model_name: str = "claude_bedrock"):
        if model_name not in BEDROCK_MODELS:
            raise ValueError(f"Unknown model: {model_name}. Available: {list(BEDROCK_MODELS.keys())}")
        self._model_name = model_name
        self._model_id = BEDROCK_MODELS[model_name]

    def classify_fields(
        self,
        ocr_text: str,
        image: Optional[Image.Image] = None,
        field_types: Optional[List[str]] = None,
        prompt_template: Optional[str] = None,
        images: Optional[List[Image.Image]] = None,
    ) -> dict:
        """Classify fields in OCR text using a Bedrock vision model."""
        types = field_types or []

        try:
            client = get_bedrock_client()
        except Exception as e:
            logger.error(f"Failed to init Bedrock client: {e}")
            return {"form_type": "error", "classified_fields": [], "error": str(e)}

        content = []

        # Include page images
        page_images = images if images else ([image] if image is not None else [])
        for idx, img in enumerate(page_images):
            if img is not None:
                img_bytes, fmt, w, h = prepare_image_for_bedrock(img)
                label = f"page {idx+1}/{len(page_images)} " if len(page_images) > 1 else ""
                logger.info(f"Classification image {label}({self._model_name}): {w}x{h}, {len(img_bytes)} bytes")
                content.append({
                    "image": {"format": fmt, "source": {"bytes": img_bytes}}
                })

        types_list = "\n".join(f"- {t}" for t in types) if types else "(extract all fields)"

        if prompt_template:
            prompt = prompt_template.replace("{field_types}", types_list).replace("{ocr_text}", ocr_text)
        else:
            prompt = (
                "You are analyzing a document. "
                "Use BOTH the image and the OCR text below to extract specific data fields.\n\n"
                "Extract the following fields:\n"
                f"{types_list}\n\n"
                "IMPORTANT:\n"
                "- Extract the ACTUAL HANDWRITTEN or FILLED-IN values, not template labels.\n"
                "- Use the image to read any handwritten text that OCR may have missed.\n"
                "- Return classified_fields array in document order.\n\n"
                'Return ONLY valid JSON (no markdown, no code fences) in this format:\n'
                '{\n'
                '  "form_type": "descriptive name of the form type",\n'
                '  "classified_fields": [\n'
                '    {"field_type": "...", "value": "...", "confidence": 0.0-1.0}\n'
                '  ]\n'
                '}\n\n'
                "OCR Text:\n---\n"
                f"{ocr_text}\n---"
            )

        content.append({"text": prompt})
        messages = [{"role": "user", "content": content}]
        max_tokens = BEDROCK_MAX_TOKENS.get(self._model_name, 8192)

        logger.info(f"Bedrock classification ({self._model_name}): {len(ocr_text)} chars, image={'yes' if page_images else 'no'}")

        response_text = bedrock_converse(
            client, self._model_id, messages,
            max_tokens=max_tokens, engine_name=self._model_name,
        )

        # Parse JSON response
        result = self._parse_response(response_text)
        result["field_types_used"] = types

        # Normalize response format
        try:
            result = normalize_classification_response(result)
        except Exception as e:
            logger.warning(f"Normalization error: {e}")

        return result

    def _parse_response(self, text: str) -> dict:
        """Parse LLM JSON response, handling markdown fences."""
        if not text:
            return {"form_type": "unknown", "classified_fields": []}

        # Strip markdown code fences
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]  # Remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end])
                except json.JSONDecodeError:
                    pass

            logger.warning(f"Could not parse classification JSON: {cleaned[:200]}")
            return {"form_type": "unknown", "classified_fields": [], "raw_response": text[:500]}
