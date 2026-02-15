"""
Amazon Bedrock field classifier implementation.

Uses the boto3 Converse API for unified access to all Bedrock vision models.
A single classifier class handles Claude, Nova, Pixtral, Llama, etc.
Same interface as ClaudeFieldClassifier and other classifiers.
"""
import io
import os
import json
import logging
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

# Model registry: engine_name -> Bedrock model ID
BEDROCK_MODELS = {
    "claude_bedrock": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude_haiku_bedrock": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "nova_pro": "us.amazon.nova-pro-v1:0",
    "nova_lite": "us.amazon.nova-lite-v1:0",
    "pixtral_large": "us.mistral.pixtral-large-2502-v1:0",
    "llama4_maverick_bedrock": "us.meta.llama4-maverick-17b-instruct-v1:0",
    "llama4_scout": "us.meta.llama4-scout-17b-instruct-v1:0",
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


class BedrockFieldClassifier:
    """Post-OCR field classification using Amazon Bedrock Converse API.

    Supports multiple vision models through a single unified interface.
    """

    _clients = {}  # Cache clients per region

    def __init__(self, model_name: str = "claude_bedrock"):
        if model_name not in BEDROCK_MODELS:
            raise ValueError(
                f"Unknown Bedrock classifier model: {model_name}. "
                f"Available: {list(BEDROCK_MODELS.keys())}"
            )
        self._model_name = model_name
        self._model_id = BEDROCK_MODELS[model_name]

    def _get_client(self):
        """Lazy-init the Bedrock Runtime client.

        Supports two auth methods:
        1. Bedrock API Key: Set AWS_BEARER_TOKEN_BEDROCK env var (boto3 auto-detects)
        2. IAM credentials: Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars
        """
        region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
        if region not in BedrockFieldClassifier._clients:
            import boto3

            bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
            aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
            aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

            if bearer_token:
                # Bedrock API Key auth — boto3 auto-detects AWS_BEARER_TOKEN_BEDROCK
                logger.info(
                    f"Initializing Bedrock classifier client in {region} "
                    f"using API key (prefix: {bearer_token[:12]}...)"
                )
                BedrockFieldClassifier._clients[region] = boto3.client(
                    "bedrock-runtime",
                    region_name=region,
                )
            elif aws_key and aws_secret:
                # IAM credentials auth
                logger.info(
                    f"Initializing Bedrock classifier client in {region} "
                    f"using IAM key (prefix: {aws_key[:8]}...)"
                )
                BedrockFieldClassifier._clients[region] = boto3.client(
                    "bedrock-runtime",
                    region_name=region,
                    aws_access_key_id=aws_key,
                    aws_secret_access_key=aws_secret,
                )
            else:
                raise RuntimeError(
                    "Either AWS_BEARER_TOKEN_BEDROCK or "
                    "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY must be set"
                )
        return BedrockFieldClassifier._clients[region]

    def _resize_for_api(self, image: Image.Image) -> Image.Image:
        """Resize image to stay within Bedrock API limits."""
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(
                f"Resized image from {w}x{h} to {new_w}x{new_h} "
                f"for classification ({self._model_name})"
            )
        return image

    def classify_fields(
        self,
        ocr_text: str,
        image: Optional[Image.Image] = None,
        field_types: Optional[List[str]] = None,
        prompt_template: Optional[str] = None,
    ) -> dict:
        """
        Classify fields in OCR text using a Bedrock vision model.

        Same interface as ClaudeFieldClassifier.classify_fields().
        """
        types = field_types if field_types else DEFAULT_FIELD_TYPES

        try:
            client = self._get_client()
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Failed to initialize Bedrock client: {e}",
            }

        content = []

        # Include image if provided for visual context
        if image is not None:
            if image.mode != "RGB":
                image = image.convert("RGB")
            image = self._resize_for_api(image)

            # Convert to PNG bytes
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            image_format = "png"

            # Fall back to JPEG if too large
            if len(image_bytes) > 3_500_000:
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=85)
                image_bytes = buffer.getvalue()
                image_format = "jpeg"
                if len(image_bytes) > 3_500_000:
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=60)
                    image_bytes = buffer.getvalue()

            logger.info(
                f"Classification image ({self._model_name}): "
                f"{image.width}x{image.height}, {len(image_bytes)} bytes"
            )
            content.append(
                {
                    "image": {
                        "format": image_format,
                        "source": {"bytes": image_bytes},
                    }
                }
            )

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
                '    {"field_type": "...", "value": "...", "context": "nearby label or description", "confidence": 0.0-1.0}\n'
                "  ]\n"
                "}\n\n"
                "OCR Text:\n"
                "---\n"
                f"{ocr_text}\n"
                "---"
            )

        content.append({"text": prompt})

        logger.info(
            f"Bedrock classification request ({self._model_name}): "
            f"{len(ocr_text)} chars of text, "
            f"image={'yes' if image is not None else 'no'}, field_types={types}"
        )

        # Build Converse API message
        messages = [{"role": "user", "content": content}]

        try:
            response = client.converse(
                modelId=self._model_id,
                messages=messages,
                inferenceConfig={"maxTokens": 2048},
            )

            # Extract text from response
            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])

            response_text = ""
            for block in content_blocks:
                if "text" in block:
                    response_text += block["text"]

            response_text = response_text.strip()

        except Exception as e:
            logger.error(
                f"Bedrock classification error ({self._model_name}): "
                f"{type(e).__name__}: {e}"
            )
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Bedrock API error ({self._model_name}): {type(e).__name__}: {e}",
            }

        logger.info(
            f"Bedrock classification response ({self._model_name}, "
            f"{len(response_text)} chars): {response_text[:200]}"
        )

        if not response_text:
            logger.error(
                f"Bedrock returned empty response for classification ({self._model_name})"
            )
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Bedrock ({self._model_name}) returned an empty response",
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
            logger.error(
                f"Bedrock classification returned invalid JSON ({self._model_name}): {e}"
            )
            logger.error(f"Raw response was: {response_text[:500]}")
            return {
                "form_type": "unknown",
                "classified_fields": [],
                "field_types_used": types,
                "raw_response": response_text,
            }
