"""
Claude field classifier implementation (direct Anthropic API).

Uses Claude's vision and text capabilities to classify fields in OCR text.
Same interface as BedrockFieldClassifier but calls Anthropic directly.
"""
import io
import json
import base64
import logging
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_FIELD_TYPES = [
    "defendant_name",
    "county",
    "cause_number",
    "charge",
    "condition_order",
    "assessed_amount",
    "address",
]


class ClaudeFieldClassifier:
    """Post-OCR field classification using Claude (direct Anthropic API)."""

    _client = None

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if ClaudeFieldClassifier._client is None:
            import anthropic

            ClaudeFieldClassifier._client = anthropic.Anthropic(
                timeout=300.0,
            )
        return ClaudeFieldClassifier._client

    def _resize_for_api(self, image: Image.Image) -> Image.Image:
        """Resize image to stay within API limits."""
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(f"Resized image from {w}x{h} to {new_w}x{new_h} for Claude classification")
        return image

    def _image_to_content_block(self, image: Image.Image, label: str = "") -> dict:
        """Convert a PIL image to an Anthropic API image content block."""
        if image.mode != "RGB":
            image = image.convert("RGB")
        image = self._resize_for_api(image)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        # Fall back to JPEG if too large
        if len(image_bytes) > 3_500_000:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            image_bytes = buffer.getvalue()
            media_type = "image/jpeg"
        else:
            media_type = "image/png"

        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info(
            f"Classification image {label}(claude_anthropic): "
            f"{image.width}x{image.height}, {len(image_bytes)} bytes"
        )
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64_image,
            },
        }

    def classify_fields(
        self,
        ocr_text: str,
        image: Optional[Image.Image] = None,
        field_types: Optional[List[str]] = None,
        prompt_template: Optional[str] = None,
        images: Optional[List[Image.Image]] = None,
    ) -> dict:
        """
        Classify fields in OCR text using Claude (Anthropic API).

        Same interface as BedrockFieldClassifier.classify_fields().
        """
        types = field_types if field_types else DEFAULT_FIELD_TYPES

        try:
            client = self._get_client()
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Failed to initialize Anthropic client: {e}",
            }

        content = []

        # Include images for visual context (multi-page or single)
        page_images = images if images else ([image] if image is not None else [])
        for idx, img in enumerate(page_images):
            if img is not None:
                label = f"page {idx+1}/{len(page_images)} " if len(page_images) > 1 else ""
                content.append(self._image_to_content_block(img, label=label))

        types_list = "\n".join(f"- {t}" for t in types)

        if prompt_template:
            prompt = prompt_template.replace("{field_types}", types_list).replace(
                "{ocr_text}", ocr_text
            )
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
                '    {"field_type": "...", "value": "...", "context": "nearby label or description", "confidence": 0.0-1.0, "page": 1, "area": "top|middle|bottom of page"}\n'
                "  ]\n"
                "}\n\n"
                "OCR Text:\n"
                "---\n"
                f"{ocr_text}\n"
                "---"
            )

        content.append({"type": "text", "text": prompt})

        logger.info(
            f"Claude (Anthropic) classification request: "
            f"{len(ocr_text)} chars of text, "
            f"image={'yes' if image is not None else 'no'}, field_types={types}"
        )

        try:
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=8192,
                messages=[{"role": "user", "content": content}],
            )

            response_text = message.content[0].text.strip()
            stop_reason = message.stop_reason

        except Exception as e:
            logger.error(
                f"Claude (Anthropic) classification error: "
                f"{type(e).__name__}: {e}"
            )
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Claude (Anthropic) API error: {type(e).__name__}: {e}",
            }

        logger.info(
            f"Claude (Anthropic) classification response "
            f"(stop_reason={stop_reason}, {len(response_text)} chars): {response_text[:500]}"
        )

        if stop_reason == "max_tokens":
            logger.warning("Claude response was truncated due to max_tokens limit")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Response was truncated (hit max_tokens limit). The model produced too much output ({len(response_text)} chars). Try simplifying your prompt or reducing the number of field types.",
                "raw_response": response_text,
            }

        if not response_text:
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": "Claude (Anthropic) returned an empty response",
            }

        # Strip markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            response_text = "\n".join(lines).strip()

        try:
            result = json.loads(response_text)

            from app.processing.classification.normalize import normalize_classification_response
            normalize_classification_response(result)

            result["field_types_used"] = types
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Claude (Anthropic) classification returned invalid JSON: {e}")
            logger.error(f"Raw response was: {response_text[:500]}")
            return {
                "form_type": "unknown",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Model response was not valid JSON (possible truncation). JSON error: {e}",
                "raw_response": response_text,
            }
