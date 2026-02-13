"""
Claude field classifier implementation.

Uses Claude's vision and text capabilities to:
1. Identify field types in OCR text (user-configurable field types)
2. Classify the form type based on the document image
"""
import io
import json
import base64
import logging
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_FIELD_TYPES = [
    "full_name",
    "date",
    "case_number",
    "address",
    "monetary_amount",
    "phone_number",
    "id_number",
]


class ClaudeFieldClassifier:
    """Post-OCR field classification using Claude."""

    _client = None

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if ClaudeFieldClassifier._client is None:
            import anthropic
            ClaudeFieldClassifier._client = anthropic.Anthropic()
        return ClaudeFieldClassifier._client

    def classify_fields(
        self,
        ocr_text: str,
        image: Optional[Image.Image] = None,
        field_types: Optional[List[str]] = None,
    ) -> dict:
        """
        Classify fields in OCR text and identify the form type.

        Args:
            ocr_text: Full text extracted by OCR
            image: Optional document image for visual context
            field_types: List of field type names to look for.
                         If None, uses DEFAULT_FIELD_TYPES.

        Returns:
            Dict with form_type and classified_fields (in document order)
        """
        client = self._get_client()

        content = []

        # Include image if provided for better visual context
        if image is not None:
            if image.mode != 'RGB':
                image = image.convert('RGB')
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64_image,
                }
            })

        types = field_types if field_types else DEFAULT_FIELD_TYPES
        types_list = "\n".join(f"- {t}" for t in types)

        prompt = (
            "Analyze this OCR-extracted text from a legal/court form document. "
            "Perform two tasks:\n\n"
            "1. CLASSIFY THE FORM TYPE: Identify what kind of form this is.\n"
            "2. IDENTIFY DATA FIELDS: For each piece of meaningful data "
            "(not template labels), identify its type and value.\n\n"
            "Field types to look for:\n"
            f"{types_list}\n"
            "- other: Any other meaningful data that doesn't fit the above types\n\n"
            "IMPORTANT: Return the classified_fields array in the SAME ORDER "
            "the data appears in the original text (top to bottom, left to right). "
            "Do not sort or group by field type.\n\n"
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

        try:
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                messages=[{"role": "user", "content": content}]
            )

            response_text = message.content[0].text.strip()

            # Parse JSON response
            result = json.loads(response_text)

            # Validate structure
            if "form_type" not in result:
                result["form_type"] = "unknown"
            if "classified_fields" not in result:
                result["classified_fields"] = []

            # Store the field types used so UI knows what was configured
            result["field_types_used"] = types

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Claude classification returned invalid JSON: {e}")
            return {
                "form_type": "unknown",
                "classified_fields": [],
                "field_types_used": types,
                "raw_response": response_text if 'response_text' in dir() else str(e),
            }
        except Exception as e:
            logger.error(f"Claude classification error: {e}")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": str(e),
            }
