"""
OpenAI Vision field classifier implementation.

Uses OpenAI's GPT-5/GPT-5-mini for field classification.
Single parameterized class for multiple model variants.
Same prompt structure as ClaudeFieldClassifier and LlamaFieldClassifier.
"""
import io
import os
import json
import base64
import logging
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

# Model ID mapping
OPENAI_MODELS = {
    "gpt5": "gpt-5",
    "gpt5_mini": "gpt-5-mini",
}

DEFAULT_FIELD_TYPES = [
    "defendant_name",
    "county",
    "cause_number",
    "charge",
    "condition_order",
    "assessed_amount",
    "address",
]


class OpenAIFieldClassifier:
    """Post-OCR field classification using OpenAI Vision models."""

    _client = None

    def __init__(self, model_key: str = "gpt5"):
        self._model_key = model_key
        self._model_id = OPENAI_MODELS.get(model_key, "gpt-5")

    def _get_client(self):
        """Lazy-init the OpenAI client."""
        if OpenAIFieldClassifier._client is None:
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set")

            OpenAIFieldClassifier._client = OpenAI(api_key=api_key)
        return OpenAIFieldClassifier._client

    def _resize_for_api(self, image: Image.Image) -> Image.Image:
        """Resize image to stay within API limits."""
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(f"Resized image from {w}x{h} to {new_w}x{new_h} for classification")
        return image

    def classify_fields(
        self,
        ocr_text: str,
        image: Optional[Image.Image] = None,
        field_types: Optional[List[str]] = None,
        prompt_template: Optional[str] = None,
    ) -> dict:
        """
        Classify fields in OCR text using OpenAI Vision.

        Same interface as ClaudeFieldClassifier.classify_fields().
        """
        types = field_types if field_types else DEFAULT_FIELD_TYPES

        try:
            client = self._get_client()
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Failed to initialize OpenAI client: {e}",
            }

        content = []

        # Include image if provided for visual context
        if image is not None:
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image = self._resize_for_api(image)

            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            image_bytes = buffer.getvalue()

            if len(image_bytes) > 5_000_000:
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=60)
                image_bytes = buffer.getvalue()

            b64_image = base64.b64encode(image_bytes).decode('utf-8')
            logger.info(f"Classification image: {image.width}x{image.height}, {len(image_bytes)} bytes")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
            })

        types_list = "\n".join(f"- {t}" for t in types)

        if prompt_template:
            prompt = prompt_template.replace("{field_types}", types_list).replace("{ocr_text}", ocr_text)
        else:
            prompt = (
                "You are analyzing a court form document. "
                "Use BOTH the image and the OCR text below to extract specific data fields.\n\n"
                "Extract the following fields:\n"
                f"{types_list}\n\n"
                "Field descriptions:\n"
                "- defendant_name: The defendant's full name (first and last name)\n"
                "- county: The county name where the court is located\n"
                "- cause_number: The cause/case number\n"
                "- charge: The criminal charge or offense described\n"
                "- condition_order: Any conditions of release or court orders listed\n"
                "- assessed_amount: Any monetary amount assessed (bond fee, fine, etc.)\n"
                "- address: Any address mentioned in the document\n\n"
                "IMPORTANT:\n"
                "- Extract the ACTUAL HANDWRITTEN or FILLED-IN values, not the template labels.\n"
                "- Use the image to read any handwritten text that the OCR may have missed.\n"
                "- Return the classified_fields array in document order (top to bottom).\n"
                "- If a field appears multiple times, include each occurrence.\n\n"
                "Return ONLY valid JSON (no markdown, no code fences) in this format:\n"
                "{\n"
                '  "form_type": "descriptive name of the form type",\n'
                '  "classified_fields": [\n'
                '    {"field_type": "...", "value": "...", "context": "nearby label or description", "confidence": 0.0-1.0}\n'
                "  ]\n"
                "}\n\n"
                "OCR Text:\n"
                "---\n"
                f"{ocr_text}\n"
                "---"
            )

        content.append({"type": "text", "text": prompt})

        logger.info(
            f"OpenAI classification request ({self._model_id}): "
            f"{len(ocr_text)} chars of text, image={'yes' if image is not None else 'no'}, "
            f"field_types={types}"
        )

        try:
            response = client.chat.completions.create(
                model=self._model_id,
                messages=[{"role": "user", "content": content}],
                max_completion_tokens=2048,
            )
            response_text = response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"OpenAI classification API error ({self._model_id}): {type(e).__name__}: {e}")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"OpenAI API error: {type(e).__name__}: {e}",
            }

        logger.info(f"OpenAI classification response ({len(response_text)} chars): {response_text[:200]}")

        if not response_text:
            logger.error("OpenAI returned empty response for classification")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": "OpenAI returned an empty response",
            }

        # Strip markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            response_text = "\n".join(lines).strip()

        try:
            result = json.loads(response_text)

            if "form_type" not in result:
                result["form_type"] = "unknown"
            if "classified_fields" not in result:
                result["classified_fields"] = []

            result["field_types_used"] = types
            return result

        except json.JSONDecodeError as e:
            logger.error(f"OpenAI classification returned invalid JSON: {e}")
            logger.error(f"Raw response was: {response_text[:500]}")
            return {
                "form_type": "unknown",
                "classified_fields": [],
                "field_types_used": types,
                "raw_response": response_text,
            }
