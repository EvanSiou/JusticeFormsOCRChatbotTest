"""
Amazon Bedrock OCR engine implementation.

Uses the boto3 Converse API for unified access to all Bedrock vision models.
Copied from eCourtDateOCR with layout detection dependency removed.
"""
import io
import os
import time
import logging
from typing import List, Optional
from PIL import Image

from .base import OCREngineBase, OCRResult, TextLine

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

MODEL_MAX_TOKENS = {k: 4096 for k in BEDROCK_MODELS}
MODEL_MAX_TOKENS["claude_bedrock"] = 16384
MODEL_MAX_TOKENS["claude_haiku_bedrock"] = 16384

MODEL_CONFIDENCE = {
    "claude_bedrock": 0.95, "claude_haiku_bedrock": 0.90,
    "nova_pro_bedrock": 0.90, "nova_lite_bedrock": 0.85,
    "pixtral_large_bedrock": 0.92,
    "llama4_maverick_bedrock": 0.90, "llama4_scout_bedrock": 0.88,
}

MODEL_REQUEST_DELAY = {
    "pixtral_large_bedrock": 15,
    "llama4_maverick_bedrock": 10,
    "llama4_scout_bedrock": 10,
}

# Module-level last-request tracker shared across OCR engine and classifier
_bedrock_last_request_time = {}


def get_bedrock_client():
    """Get or create a shared Bedrock Runtime client."""
    region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
    if not hasattr(get_bedrock_client, "_clients"):
        get_bedrock_client._clients = {}
    if region not in get_bedrock_client._clients:
        import boto3
        from botocore.config import Config

        boto_config = Config(
            read_timeout=300,
            connect_timeout=10,
            retries={"max_attempts": 0},
        )

        bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
        aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
        aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

        if bearer_token:
            get_bedrock_client._clients[region] = boto3.client(
                "bedrock-runtime", region_name=region, config=boto_config,
            )
        elif aws_key and aws_secret:
            get_bedrock_client._clients[region] = boto3.client(
                "bedrock-runtime", region_name=region,
                aws_access_key_id=aws_key, aws_secret_access_key=aws_secret,
                config=boto_config,
            )
        else:
            # Fall back to default credential chain (IAM role, instance profile, etc.)
            logger.info(f"Using default AWS credential chain for Bedrock in {region}")
            get_bedrock_client._clients[region] = boto3.client(
                "bedrock-runtime", region_name=region, config=boto_config,
            )
    return get_bedrock_client._clients[region]


def bedrock_rate_limit(engine_name: str):
    """Enforce rate limiting for a given engine."""
    delay = MODEL_REQUEST_DELAY.get(engine_name, 0)
    if delay > 0:
        last_t = _bedrock_last_request_time.get(engine_name, 0)
        elapsed = time.time() - last_t
        if elapsed < delay:
            gap = delay - elapsed
            logger.info(f"Rate-limit delay for {engine_name}: waiting {gap:.1f}s")
            time.sleep(gap)
    _bedrock_last_request_time[engine_name] = time.time()


def bedrock_converse(client, model_id: str, messages: list, max_tokens: int = 4096,
                     engine_name: str = ""):
    """Call Bedrock Converse API with retry logic. Shared by OCR engine and classifier."""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            bedrock_rate_limit(engine_name)
            response = client.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig={"maxTokens": max_tokens},
            )
            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])

            full_text = ""
            for block in content_blocks:
                if "text" in block:
                    full_text += block["text"]
            return full_text.strip()

        except Exception as e:
            error_name = type(e).__name__
            retryable = any(k in str(e) for k in ("Throttling", "ModelTimeout", "ServiceUnavailable"))
            if retryable and attempt < max_retries - 1:
                wait = (2 ** attempt) * 15
                logger.warning(f"Bedrock retryable error ({engine_name}), attempt {attempt+1}/{max_retries}, waiting {wait}s: {e}")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Bedrock API call failed ({engine_name}): {error_name}: {e}") from e


def prepare_image_for_bedrock(image: Image.Image) -> tuple:
    """Resize and encode an image for the Bedrock Converse API.

    Returns (image_bytes, format_string, width, height).
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    MAX_DIMENSION = 2048
    w, h = image.size
    if max(w, h) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()

    if len(image_bytes) > 3_500_000:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()
        fmt = "jpeg"
        if len(image_bytes) > 3_500_000:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=60)
            image_bytes = buffer.getvalue()
    else:
        fmt = "png"

    return image_bytes, fmt, image.width, image.height


class BedrockOCREngine(OCREngineBase):
    """OCR engine using Amazon Bedrock Converse API."""

    def __init__(self, engine_name: str = "claude_bedrock"):
        if engine_name not in BEDROCK_MODELS:
            raise ValueError(f"Unknown Bedrock engine: {engine_name}. Available: {list(BEDROCK_MODELS.keys())}")
        self._engine_name = engine_name
        self._model_id = BEDROCK_MODELS[engine_name]
        self._max_tokens = MODEL_MAX_TOKENS.get(engine_name, 4096)
        self._confidence = MODEL_CONFIDENCE.get(engine_name, 0.90)

    @property
    def name(self) -> str:
        return self._engine_name

    DEFAULT_PROMPT = (
        "Extract ALL text from this document image. "
        "Return every word exactly as it appears, preserving line breaks. "
        "Do not add any commentary, formatting, or markdown — only the raw text content."
    )

    def extract_text(self, image: Image.Image, regions=None, prompt: Optional[str] = None) -> List[OCRResult]:
        result = self._process_full_page(image, prompt=prompt)
        return [result]

    def _process_full_page(self, image: Image.Image, prompt: Optional[str] = None) -> OCRResult:
        client = get_bedrock_client()
        image_bytes, fmt, w, h = prepare_image_for_bedrock(image)

        logger.info(f"Sending image to Bedrock ({self._engine_name} / {self._model_id}): {w}x{h}, {len(image_bytes)} bytes, {fmt}")

        messages = [{
            "role": "user",
            "content": [
                {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
                {"text": prompt or self.DEFAULT_PROMPT},
            ],
        }]

        full_text = bedrock_converse(client, self._model_id, messages,
                                     max_tokens=self._max_tokens, engine_name=self._engine_name)

        lines = []
        if full_text:
            for line_text in full_text.split("\n"):
                line_text = line_text.strip()
                if line_text:
                    lines.append(TextLine(
                        text=line_text, confidence=self._confidence,
                        bbox_in_region={"x1": 0, "y1": 0, "x2": w, "y2": h},
                    ))

        return OCRResult(region_id=0, full_text=full_text, lines=lines)

    def _process_cropped_image(self, image: Image.Image, region_id: int) -> OCRResult:
        result = self._process_full_page(image)
        result.region_id = region_id
        return result
