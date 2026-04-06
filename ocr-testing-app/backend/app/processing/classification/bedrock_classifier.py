"""
Amazon Bedrock field classifier implementation.

Uses the boto3 Converse API for unified access to all Bedrock vision models.
A single classifier class handles Claude, Nova, Pixtral, Llama, etc.
Same interface as ClaudeFieldClassifier and other classifiers.
"""
import io
import os
import json
import time
import logging
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

# Model registry: engine_name -> Bedrock model ID
BEDROCK_MODELS = {
    "claude_bedrock": "us.anthropic.claude-sonnet-4-6",
    "claude_haiku_bedrock": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "nova_pro_bedrock": "us.amazon.nova-pro-v1:0",
    "nova_lite_bedrock": "us.amazon.nova-lite-v1:0",
    "pixtral_large_bedrock": "us.mistral.pixtral-large-2502-v1:0",
    "llama4_maverick_bedrock": "us.meta.llama4-maverick-17b-instruct-v1:0",
    "llama4_scout_bedrock": "us.meta.llama4-scout-17b-instruct-v1:0",
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

# Model-specific max output token limits
BEDROCK_MAX_TOKENS = {
    "claude_bedrock": 4096,
    "claude_haiku_bedrock": 4096,
    "nova_pro_bedrock": 4096,
    "nova_lite_bedrock": 4096,
    "pixtral_large_bedrock": 4096,
    "llama4_maverick_bedrock": 4096,
    "llama4_scout_bedrock": 4096,
}

# Minimum delay (seconds) between consecutive API calls per model.
MODEL_REQUEST_DELAY = {
    "pixtral_large_bedrock": 15,
    "llama4_maverick_bedrock": 10,
    "llama4_scout_bedrock": 10,
}

# Import shared rate-limit tracker (shared with OCR engine)
from app.processing.ocr.bedrock_engine import _bedrock_last_request_time


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
        self._request_delay = MODEL_REQUEST_DELAY.get(model_name, 0)

    def _get_client(self):
        """Lazy-init the Bedrock Runtime client.

        Supports two auth methods:
        1. Bedrock API Key: Set AWS_BEARER_TOKEN_BEDROCK env var (boto3 auto-detects)
        2. IAM credentials: Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars
        """
        region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
        if region not in BedrockFieldClassifier._clients:
            import boto3
            from botocore.config import Config

            # Disable botocore's internal retries for throttling —
            # our app-level retry loop uses longer backoffs (15s+)
            boto_config = Config(
                read_timeout=300,
                connect_timeout=10,
                retries={"max_attempts": 0},
            )

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
                    config=boto_config,
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
                    config=boto_config,
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

    def _image_to_content_block(self, image: Image.Image, label: str = "") -> dict:
        """Convert a PIL image to a Bedrock Converse API image content block."""
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
            f"Classification image {label}({self._model_name}): "
            f"{image.width}x{image.height}, {len(image_bytes)} bytes"
        )
        return {
            "image": {
                "format": image_format,
                "source": {"bytes": image_bytes},
            }
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
        Classify fields in OCR text using a Bedrock vision model.

        Args:
            ocr_text: OCR extracted text (may span multiple pages)
            image: Single page image for visual context (used if images not provided)
            field_types: List of field types to extract
            prompt_template: Optional custom prompt template
            images: List of page images for multi-page documents
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

        content.append({"text": prompt})

        logger.info(
            f"Bedrock classification request ({self._model_name}): "
            f"{len(ocr_text)} chars of text, "
            f"image={'yes' if image is not None else 'no'}, field_types={types}"
        )

        # Build Converse API message
        messages = [{"role": "user", "content": content}]

        # Rate-limit: wait between requests for models with low quotas
        if self._request_delay > 0:
            last_t = _bedrock_last_request_time.get(self._model_name, 0)
            elapsed = time.time() - last_t
            if elapsed < self._request_delay:
                gap = self._request_delay - elapsed
                logger.info(
                    f"Rate-limit delay for classifier {self._model_name}: "
                    f"waiting {gap:.1f}s before next request"
                )
                time.sleep(gap)

        # Retry with exponential backoff for throttling/timeout errors
        max_retries = 5
        max_tokens = BEDROCK_MAX_TOKENS.get(self._model_name, 8192)
        response_text = ""
        stop_reason = "unknown"
        for attempt in range(max_retries):
            try:
                _bedrock_last_request_time[self._model_name] = time.time()
                response = client.converse(
                    modelId=self._model_id,
                    messages=messages,
                    inferenceConfig={"maxTokens": max_tokens},
                )

                # Extract text from response
                output = response.get("output", {})
                message = output.get("message", {})
                content_blocks = message.get("content", [])
                stop_reason = response.get("stopReason", "unknown")

                response_text = ""
                for block in content_blocks:
                    if "text" in block:
                        response_text += block["text"]

                response_text = response_text.strip()
                break  # Success

            except Exception as e:
                error_name = type(e).__name__
                retryable = "Throttling" in error_name or "Throttling" in str(e) or \
                            "ModelTimeout" in error_name or "ModelTimeout" in str(e) or \
                            "ServiceUnavailable" in str(e)
                if retryable and attempt < max_retries - 1:
                    wait = (2 ** attempt) * 15  # 15s, 30s, 60s, 120s
                    logger.warning(
                        f"Bedrock classification retryable error ({self._model_name}), "
                        f"attempt {attempt + 1}/{max_retries}, waiting {wait}s: "
                        f"{error_name}: {e}"
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    f"Bedrock classification error ({self._model_name}): "
                    f"{error_name}: {e}"
                )
                return {
                    "form_type": "error",
                    "classified_fields": [],
                    "field_types_used": types,
                    "error": f"Bedrock API error ({self._model_name}): {error_name}: {e}",
                }

        logger.info(
            f"Bedrock classification response ({self._model_name}, "
            f"stop_reason={stop_reason}, {len(response_text)} chars): {response_text[:500]}"
        )

        if stop_reason == "max_tokens":
            logger.warning(f"Bedrock response was truncated due to max_tokens limit ({self._model_name})")
            return {
                "form_type": "error",
                "classified_fields": [],
                "field_types_used": types,
                "error": f"Response was truncated (hit max_tokens limit). The model produced too much output ({len(response_text)} chars). Try simplifying your prompt or reducing the number of field types.",
                "raw_response": response_text,
            }

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

            from app.processing.classification.normalize import normalize_classification_response
            normalize_classification_response(result)

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
                "error": f"Model response was not valid JSON (possible truncation). JSON error: {e}",
                "raw_response": response_text,
            }
