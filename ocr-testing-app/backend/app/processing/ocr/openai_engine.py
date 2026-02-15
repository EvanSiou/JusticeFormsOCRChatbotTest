"""
OpenAI Vision OCR engine implementation.

Uses OpenAI's GPT-5/GPT-5-mini vision API for full-page text extraction.
A single parameterized engine class serving multiple model variants.
This is a VLM-style engine that processes the full page in a single pass.
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

# Model ID mapping
OPENAI_MODELS = {
    "gpt5": "gpt-5",
    "gpt5_mini": "gpt-5-mini",
}


class OpenAIVisionEngine(OCREngineBase):
    """OCR engine using OpenAI Vision API. Parameterized by model name."""

    _client = None

    def __init__(self, engine_name: str = "gpt5"):
        self._engine_name = engine_name
        self._model_id = OPENAI_MODELS.get(engine_name, "gpt-5")

    @property
    def name(self) -> str:
        return self._engine_name

    def _get_client(self):
        """Lazy-init the OpenAI client."""
        if OpenAIVisionEngine._client is None:
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                logger.error("OPENAI_API_KEY environment variable is not set")
                raise RuntimeError("OPENAI_API_KEY is not set")

            logger.info(f"Initializing OpenAI client (key prefix: {api_key[:8]}...)")
            OpenAIVisionEngine._client = OpenAI(api_key=api_key)
        return OpenAIVisionEngine._client

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
        """Process the full page in a single pass."""
        full_page_result = self._process_full_page(image, prompt=prompt)
        return [full_page_result]

    def _resize_for_api(self, image: Image.Image) -> Image.Image:
        """Resize image if needed to stay within OpenAI API limits."""
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(f"Resized image from {w}x{h} to {new_w}x{new_h} for OpenAI API")
        return image

    def _process_full_page(self, image: Image.Image, prompt: Optional[str] = None) -> OCRResult:
        """Process the full page image with OpenAI's vision API."""
        client = self._get_client()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Resize to stay within API limits
        image = self._resize_for_api(image)

        # Convert to JPEG
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        image_bytes = buffer.getvalue()

        # If still too large, reduce quality
        if len(image_bytes) > 5_000_000:
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=60)
            image_bytes = buffer.getvalue()
            logger.info(f"Reduced JPEG quality to 60, size: {len(image_bytes)} bytes")

        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        logger.info(
            f"Sending image to OpenAI {self._model_id}: "
            f"{image.width}x{image.height}, {len(image_bytes)} bytes"
        )

        try:
            response = client.chat.completions.create(
                model=self._model_id,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                        },
                        {
                            "type": "text",
                            "text": prompt or self.DEFAULT_PROMPT,
                        },
                    ],
                }],
                max_completion_tokens=4096,
            )
            full_text = response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"OpenAI API error ({self._model_id}): {type(e).__name__}: {e}")
            raise RuntimeError(f"OpenAI API call failed: {type(e).__name__}: {e}") from e

        # Split into lines
        lines = []
        if full_text:
            for line_text in full_text.split('\n'):
                line_text = line_text.strip()
                if not line_text:
                    continue
                lines.append(TextLine(
                    text=line_text,
                    confidence=0.92,
                    bbox_in_region={
                        "x1": 0, "y1": 0,
                        "x2": image.width, "y2": image.height,
                    },
                ))

        return OCRResult(
            region_id=0,
            full_text=full_text,
            lines=lines,
        )

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """Process a cropped image — delegates to full-page processing."""
        result = self._process_full_page(image)
        result.region_id = region_id
        return result
