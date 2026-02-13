"""
Claude OCR engine implementation.

Uses Anthropic's Claude vision API for full-page text extraction.
This is a VLM-style engine that processes the full page in a single pass,
similar to GOT-OCR and MinerU.
"""
import io
import base64
import logging
from typing import List
from PIL import Image

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region

logger = logging.getLogger(__name__)


class ClaudeOCREngine(OCREngineBase):
    """OCR engine using Claude's vision API."""

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

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text from the full page in a single pass.

        Claude is a VLM that processes full documents efficiently.
        Layout regions are ignored — the entire page is processed at once.
        """
        full_page_result = self._process_full_page(image)
        return [full_page_result]

    def _process_full_page(self, image: Image.Image) -> OCRResult:
        """Process the full page image with Claude's vision API."""
        client = self._get_client()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Convert PIL Image to base64 PNG
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')

        try:
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64_image,
                            }
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract ALL text from this document image. "
                                "Return every word exactly as it appears, preserving line breaks. "
                                "Do not add any commentary, formatting, or markdown — only the raw text content."
                            )
                        }
                    ]
                }]
            )

            full_text = message.content[0].text.strip()

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return OCRResult(region_id=0, full_text="", lines=[])

        # Split into lines
        lines = []
        if full_text:
            text_lines = full_text.split('\n')
            for line_text in text_lines:
                line_text = line_text.strip()
                if not line_text:
                    continue

                lines.append(TextLine(
                    text=line_text,
                    confidence=0.95,
                    bbox_in_region={
                        "x1": 0,
                        "y1": 0,
                        "x2": image.width,
                        "y2": image.height,
                    }
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
        """
        Process a cropped image with Claude.

        Note: extract_text() uses full-page processing for efficiency.
        This is kept for compatibility with the base class.
        """
        result = self._process_full_page(image)
        result.region_id = region_id
        return result
