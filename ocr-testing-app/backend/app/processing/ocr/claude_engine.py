"""
Claude OCR engine implementation (direct Anthropic API).

Uses Anthropic's Claude vision API for full-page text extraction.
This is a VLM-style engine that processes the full page in a single pass.
"""
import io
import base64
import logging
from typing import List, Optional
from PIL import Image

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region

logger = logging.getLogger(__name__)


class ClaudeOCREngine(OCREngineBase):
    """OCR engine using Claude's vision API (direct Anthropic)."""

    _client = None

    @property
    def name(self) -> str:
        return "claude"

    def _get_client(self):
        """Lazy-init the Anthropic client."""
        if ClaudeOCREngine._client is None:
            import anthropic

            ClaudeOCREngine._client = anthropic.Anthropic()
        return ClaudeOCREngine._client

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
        """Resize image to stay within API limits."""
        MAX_DIMENSION = 2048
        w, h = image.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
            logger.info(f"Resized image from {w}x{h} to {new_w}x{new_h} for Claude API")
        return image

    def _process_full_page(
        self, image: Image.Image, prompt: Optional[str] = None
    ) -> OCRResult:
        """Process the full page image with Claude's vision API."""
        client = self._get_client()

        # Ensure RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        image = self._resize_for_api(image)

        # Convert PIL Image to base64 PNG
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
            f"Sending image to Claude (Anthropic): "
            f"{image.width}x{image.height}, {len(image_bytes)} bytes"
        )

        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_image,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt or self.DEFAULT_PROMPT,
                            },
                        ],
                    }
                ],
            )

            full_text = message.content[0].text.strip()

        except Exception as e:
            logger.error(f"Claude (Anthropic) API error: {type(e).__name__}: {e}")
            raise RuntimeError(
                f"Claude (Anthropic) API call failed: {type(e).__name__}: {e}"
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
                        confidence=0.95,
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
