"""
TrOCR (Transformer-based OCR) engine implementation.

Uses microsoft/trocr-base-handwritten for handwritten text recognition.
TrOCR processes single-line text images, so each cropped region is treated
as a text line. For multi-line regions, we split into lines via simple
horizontal projection and process each line individually.
"""
from typing import List, Optional
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class TrOCREngine(OCREngineBase):
    """OCR engine using Microsoft TrOCR (handwritten variant)."""

    _processor = None
    _model = None
    _device = None

    @property
    def name(self) -> str:
        return "trocr"

    def _load_model(self):
        """Lazy load TrOCR model and processor."""
        if TrOCREngine._processor is None:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel

            model_name = "microsoft/trocr-base-handwritten"

            # Use GPU if available
            TrOCREngine._device = "cuda" if torch.cuda.is_available() else "cpu"

            TrOCREngine._processor = TrOCRProcessor.from_pretrained(model_name)
            TrOCREngine._model = VisionEncoderDecoderModel.from_pretrained(model_name)
            TrOCREngine._model.to(TrOCREngine._device)
            TrOCREngine._model.eval()

        return TrOCREngine._processor, TrOCREngine._model

    def _split_into_lines(self, image: Image.Image, min_gap: int = 5):
        """
        Split an image into text line crops using horizontal projection.

        Finds horizontal white-space gaps to split multi-line text regions
        into individual lines for TrOCR (which expects single-line input).

        Returns list of (y_start, y_end) tuples for each detected line.
        """
        gray = np.array(image.convert('L'))
        # Binarize: text is dark, background is light
        threshold = 200
        binary = (gray < threshold).astype(np.uint8)

        # Horizontal projection (sum along x-axis)
        h_proj = binary.sum(axis=1)

        # Find line regions (non-zero projection)
        in_line = False
        lines = []
        start = 0
        for y in range(len(h_proj)):
            if h_proj[y] > 0 and not in_line:
                start = y
                in_line = True
            elif h_proj[y] == 0 and in_line:
                if y - start > min_gap:
                    lines.append((start, y))
                in_line = False

        if in_line:
            if len(h_proj) - start > min_gap:
                lines.append((start, len(h_proj)))

        # If no lines detected, return the full image as one line
        if not lines:
            lines = [(0, image.height)]

        return lines

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region],
        prompt: Optional[str] = None
    ) -> List[OCRResult]:
        """Extract text from all regions."""
        results = []
        for region in regions:
            result = self.extract_from_region(image, region)
            results.append(result)
        return results

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """Process a cropped image with TrOCR."""
        import torch

        processor, model = self._load_model()

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Split into individual text lines
        line_regions = self._split_into_lines(image)

        lines = []
        full_text_parts = []

        for y_start, y_end in line_regions:
            # Crop the line
            line_img = image.crop((0, y_start, image.width, y_end))

            # Skip very thin lines (likely noise)
            if line_img.height < 5:
                continue

            # Process with TrOCR
            pixel_values = processor(
                images=line_img,
                return_tensors="pt"
            ).pixel_values.to(TrOCREngine._device)

            with torch.no_grad():
                generated_ids = model.generate(pixel_values, max_new_tokens=128)

            text = processor.batch_decode(
                generated_ids,
                skip_special_tokens=True
            )[0].strip()

            if not text:
                continue

            lines.append(TextLine(
                text=text,
                confidence=0.9,  # TrOCR doesn't expose per-token confidence easily
                bbox_in_region={
                    "x1": 0,
                    "y1": y_start,
                    "x2": image.width,
                    "y2": y_end,
                }
            ))
            full_text_parts.append(text)

        full_text = " ".join(full_text_parts)

        return OCRResult(
            region_id=region_id,
            full_text=full_text,
            lines=lines,
        )
