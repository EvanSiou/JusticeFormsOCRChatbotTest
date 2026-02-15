"""
Vertex AI OCR engine implementation.

Uses Google Cloud Vertex AI for vision model text extraction.
Supports Llama and Gemini models via Vertex AI's unified API.
"""
import io
import os
import base64
import logging
from typing import List, Optional
from PIL import Image

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region

logger = logging.getLogger(__name__)

# Model registry: engine_name -> Vertex AI model ID
VERTEX_MODELS = {
    "llama4_maverick_vertex": "meta/llama-4-maverick-17b-128e-instruct-maas",
    "llama4_scout_vertex": "meta/llama-4-scout-17b-16e-instruct-maas",
}

# Default confidence per model
MODEL_CONFIDENCE = {
    "llama4_maverick_vertex": 0.90,
    "llama4_scout_vertex": 0.88,
}


class VertexOCREngine(OCREngineBase):
    """OCR engine using Vertex AI (Llama, Gemini, etc.)."""

    _clients = {}

    def __init__(self, engine_name: str):
        if engine_name not in VERTEX_MODELS:
            raise ValueError(
                f"Unknown Vertex AI engine: {engine_name}. "
                f"Available: {list(VERTEX_MODELS.keys())}"
            )
        self._engine_name = engine_name
        self._model_id = VERTEX_MODELS[engine_name]
        self._confidence = MODEL_CONFIDENCE.get(engine_name, 0.90)

    @property
    def name(self) -> str:
        return self._engine_name

    def _get_client(self):
        """Lazy-init the Vertex AI client."""
        project = os.environ.get("GCP_PROJECT_ID", "")
        region = os.environ.get("VERTEX_AI_REGION", "us-central1")
        key = f"{project}:{region}"

        if key not in VertexOCREngine._clients:
            from openai import OpenAI

            # Vertex AI supports OpenAI-compatible endpoint for Llama models
            base_url = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/endpoints/openapi"

            # Use Google auth token
            import google.auth
            import google.auth.transport.requests

            credentials, _ = google.auth.default()
            credentials.refresh(google.auth.transport.requests.Request())
            token = credentials.token

            logger.info(
                f"Initializing Vertex AI client in {region} "
                f"for project {project} (model: {self._model_id})"
            )

            VertexOCREngine._clients[key] = OpenAI(
                base_url=base_url,
                api_key=token,
            )
        return VertexOCREngine._clients[key]

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
        """Process the full page in a single pass via Vertex AI."""
        full_page_result = self._process_full_page(image, prompt=prompt)
        return [full_page_result]

    def _resize_for_api(self, image: Image.Image) -> Image.Image:
        """Resize image to stay within API limits."""
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(
                f"Resized image from {w}x{h} to {new_w}x{new_h} "
                f"for Vertex AI ({self._engine_name})"
            )
        return image

    def _process_full_page(
        self, image: Image.Image, prompt: Optional[str] = None
    ) -> OCRResult:
        """Process the full page image via Vertex AI."""
        client = self._get_client()

        if image.mode != "RGB":
            image = image.convert("RGB")

        image = self._resize_for_api(image)

        # Convert to JPEG for Llama models
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()

        if len(image_bytes) > 5_000_000:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=60)
            image_bytes = buffer.getvalue()

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        logger.info(
            f"Sending image to Vertex AI ({self._engine_name} / {self._model_id}): "
            f"{image.width}x{image.height}, {len(image_bytes)} bytes"
        )

        ocr_prompt = prompt or self.DEFAULT_PROMPT

        try:
            response = client.chat.completions.create(
                model=self._model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}"
                                },
                            },
                            {"type": "text", "text": ocr_prompt},
                        ],
                    }
                ],
                max_completion_tokens=4096,
            )

            full_text = response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(
                f"Vertex AI API error ({self._engine_name}): "
                f"{type(e).__name__}: {e}"
            )
            raise RuntimeError(
                f"Vertex AI API call failed ({self._engine_name}): "
                f"{type(e).__name__}: {e}"
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
