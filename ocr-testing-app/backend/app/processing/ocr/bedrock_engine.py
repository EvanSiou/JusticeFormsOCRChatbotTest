"""
Amazon Bedrock OCR engine implementation.

Uses the boto3 Converse API for unified access to all Bedrock vision models.
A single engine class handles Claude, Nova, Pixtral, Llama, etc.
"""
import io
import os
import time
import logging
from typing import List, Optional
from PIL import Image

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region

logger = logging.getLogger(__name__)

# Model registry: engine_name -> Bedrock model ID
BEDROCK_MODELS = {
    "claude_bedrock": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude_haiku_bedrock": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "nova_pro_bedrock": "us.amazon.nova-pro-v1:0",
    "nova_lite_bedrock": "us.amazon.nova-lite-v1:0",
    "pixtral_large_bedrock": "us.mistral.pixtral-large-2502-v1:0",
    "llama4_maverick_bedrock": "us.meta.llama4-maverick-17b-instruct-v1:0",
    "llama4_scout_bedrock": "us.meta.llama4-scout-17b-instruct-v1:0",
}

# Max tokens per model (some models have different limits)
MODEL_MAX_TOKENS = {
    "claude_bedrock": 4096,
    "claude_haiku_bedrock": 4096,
    "nova_pro_bedrock": 4096,
    "nova_lite_bedrock": 4096,
    "pixtral_large_bedrock": 4096,
    "llama4_maverick_bedrock": 4096,
    "llama4_scout_bedrock": 4096,
}

# Default confidence scores per model family
MODEL_CONFIDENCE = {
    "claude_bedrock": 0.95,
    "claude_haiku_bedrock": 0.90,
    "nova_pro_bedrock": 0.90,
    "nova_lite_bedrock": 0.85,
    "pixtral_large_bedrock": 0.92,
    "llama4_maverick_bedrock": 0.90,
    "llama4_scout_bedrock": 0.88,
}

# Minimum delay (seconds) between consecutive API calls per model.
# Models with very low rate limits need longer gaps.
MODEL_REQUEST_DELAY = {
    "pixtral_large_bedrock": 15,
    "llama4_maverick_bedrock": 10,
    "llama4_scout_bedrock": 10,
}

# Module-level last-request tracker shared across OCR engine and classifier
_bedrock_last_request_time = {}


class BedrockOCREngine(OCREngineBase):
    """OCR engine using Amazon Bedrock Converse API.

    Supports multiple vision models through a single unified interface.
    """

    _clients = {}  # Cache clients per region

    def __init__(self, engine_name: str):
        if engine_name not in BEDROCK_MODELS:
            raise ValueError(
                f"Unknown Bedrock engine: {engine_name}. "
                f"Available: {list(BEDROCK_MODELS.keys())}"
            )
        self._engine_name = engine_name
        self._model_id = BEDROCK_MODELS[engine_name]
        self._max_tokens = MODEL_MAX_TOKENS.get(engine_name, 4096)
        self._confidence = MODEL_CONFIDENCE.get(engine_name, 0.90)
        self._request_delay = MODEL_REQUEST_DELAY.get(engine_name, 0)

    @property
    def name(self) -> str:
        return self._engine_name

    def _get_client(self):
        """Lazy-init the Bedrock Runtime client.

        Supports two auth methods:
        1. Bedrock API Key: Set AWS_BEARER_TOKEN_BEDROCK env var (boto3 auto-detects)
        2. IAM credentials: Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY env vars
        """
        region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
        if region not in BedrockOCREngine._clients:
            import boto3
            from botocore.config import Config

            # Disable botocore's internal retries for throttling —
            # our app-level retry loop uses longer backoffs (15s+)
            # that actually respect per-model rate limits.
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
                    f"Initializing Bedrock client in {region} "
                    f"using API key (prefix: {bearer_token[:12]}...)"
                )
                BedrockOCREngine._clients[region] = boto3.client(
                    "bedrock-runtime",
                    region_name=region,
                    config=boto_config,
                )
            elif aws_key and aws_secret:
                # IAM credentials auth
                logger.info(
                    f"Initializing Bedrock client in {region} "
                    f"using IAM key (prefix: {aws_key[:8]}...)"
                )
                BedrockOCREngine._clients[region] = boto3.client(
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
        return BedrockOCREngine._clients[region]

    DEFAULT_PROMPT = (
        "Extract ALL text from this document image. "
        "Return every word exactly as it appears, preserving line breaks. "
        "Do not add any commentary, formatting, or markdown — only the raw text content."
    )

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region],
        prompt: Optional[str] = None,
    ) -> List[OCRResult]:
        """Process the full page in a single pass via Bedrock."""
        full_page_result = self._process_full_page(image, prompt=prompt)
        return [full_page_result]

    def _resize_for_api(self, image: Image.Image) -> Image.Image:
        """Resize image to stay within API limits.

        Bedrock Converse API: max 3.75MB per image, max 8000px.
        We target 2048px max dimension for good quality/speed balance.
        """
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(
                f"Resized image from {w}x{h} to {new_w}x{new_h} "
                f"for Bedrock ({self._engine_name})"
            )
        return image

    def _process_full_page(
        self, image: Image.Image, prompt: Optional[str] = None
    ) -> OCRResult:
        """Process the full page image via Bedrock Converse API."""
        client = self._get_client()

        # Ensure RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        image = self._resize_for_api(image)

        # Convert to PNG bytes (Converse API accepts raw bytes, no base64 needed)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        # If PNG is too large (>3.5MB), fall back to JPEG
        if len(image_bytes) > 3_500_000:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            image_bytes = buffer.getvalue()
            image_format = "jpeg"
            # If still too large, reduce quality further
            if len(image_bytes) > 3_500_000:
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=60)
                image_bytes = buffer.getvalue()
        else:
            image_format = "png"

        logger.info(
            f"Sending image to Bedrock ({self._engine_name} / {self._model_id}): "
            f"{image.width}x{image.height}, {len(image_bytes)} bytes, {image_format}"
        )

        ocr_prompt = prompt or self.DEFAULT_PROMPT

        # Build Converse API message
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": image_bytes},
                        }
                    },
                    {"text": ocr_prompt},
                ],
            }
        ]

        # Rate-limit: wait between requests for models with low quotas
        if self._request_delay > 0:
            last_t = _bedrock_last_request_time.get(self._engine_name, 0)
            elapsed = time.time() - last_t
            if elapsed < self._request_delay:
                gap = self._request_delay - elapsed
                logger.info(
                    f"Rate-limit delay for {self._engine_name}: "
                    f"waiting {gap:.1f}s before next request"
                )
                time.sleep(gap)

        # Retry with exponential backoff for throttling/timeout errors
        max_retries = 5
        last_error = None
        for attempt in range(max_retries):
            try:
                _bedrock_last_request_time[self._engine_name] = time.time()
                response = client.converse(
                    modelId=self._model_id,
                    messages=messages,
                    inferenceConfig={"maxTokens": self._max_tokens},
                )

                # Extract text from response
                output = response.get("output", {})
                message = output.get("message", {})
                content_blocks = message.get("content", [])

                full_text = ""
                for block in content_blocks:
                    if "text" in block:
                        full_text += block["text"]

                full_text = full_text.strip()
                break  # Success

            except Exception as e:
                last_error = e
                error_name = type(e).__name__
                retryable = "Throttling" in error_name or "Throttling" in str(e) or \
                            "ModelTimeout" in error_name or "ModelTimeout" in str(e) or \
                            "ServiceUnavailable" in str(e)
                if retryable and attempt < max_retries - 1:
                    wait = (2 ** attempt) * 15  # 15s, 30s, 60s, 120s
                    logger.warning(
                        f"Bedrock retryable error ({self._engine_name}), "
                        f"attempt {attempt + 1}/{max_retries}, waiting {wait}s: "
                        f"{error_name}: {e}"
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    f"Bedrock API error ({self._engine_name}): "
                    f"{error_name}: {e}"
                )
                raise RuntimeError(
                    f"Bedrock API call failed ({self._engine_name}): "
                    f"{error_name}: {e}"
                ) from e

        # Split into lines
        lines = []
        if full_text:
            for line_text in full_text.split("\n"):
                line_text = line_text.strip()
                if not line_text:
                    continue
                lines.append(
                    TextLine(
                        text=line_text,
                        confidence=self._confidence,
                        bbox_in_region={
                            "x1": 0,
                            "y1": 0,
                            "x2": image.width,
                            "y2": image.height,
                        },
                    )
                )

        return OCRResult(
            region_id=0,
            full_text=full_text,
            lines=lines,
        )

    def _process_cropped_image(
        self, image: Image.Image, region_id: int
    ) -> OCRResult:
        """Process a cropped image — delegates to full-page processing."""
        result = self._process_full_page(image)
        result.region_id = region_id
        return result
