"""
Tesseract 5 OCR engine implementation.

Requires tesseract-ocr system package to be installed.
"""
from typing import List, Optional
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class TesseractEngine(OCREngineBase):
    """OCR engine using Tesseract 5 via pytesseract."""

    @property
    def name(self) -> str:
        return "tesseract"

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
        """Process a cropped image with Tesseract."""
        import pytesseract
        from pytesseract import Output

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Get detailed data with bounding boxes and confidence
        data = pytesseract.image_to_data(
            image,
            output_type=Output.DICT,
            config='--oem 3 --psm 6'  # LSTM engine, uniform block of text
        )

        lines = []
        full_text_parts = []

        # Group words by line number
        line_groups = {}
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])

            # Skip empty text or low-confidence noise (conf == -1 means no text)
            if not text or conf < 0:
                continue

            line_num = data['line_num'][i]
            if line_num not in line_groups:
                line_groups[line_num] = {
                    'words': [],
                    'confs': [],
                    'x1': data['left'][i],
                    'y1': data['top'][i],
                    'x2': data['left'][i] + data['width'][i],
                    'y2': data['top'][i] + data['height'][i],
                }

            group = line_groups[line_num]
            group['words'].append(text)
            group['confs'].append(conf)
            # Expand bounding box to encompass all words in the line
            group['x1'] = min(group['x1'], data['left'][i])
            group['y1'] = min(group['y1'], data['top'][i])
            group['x2'] = max(group['x2'], data['left'][i] + data['width'][i])
            group['y2'] = max(group['y2'], data['top'][i] + data['height'][i])

        # Convert line groups to TextLine objects
        for line_num in sorted(line_groups.keys()):
            group = line_groups[line_num]
            line_text = ' '.join(group['words'])
            avg_conf = sum(group['confs']) / len(group['confs']) / 100.0  # Normalize to 0-1

            lines.append(TextLine(
                text=line_text,
                confidence=round(avg_conf, 4),
                bbox_in_region={
                    "x1": group['x1'],
                    "y1": group['y1'],
                    "x2": group['x2'],
                    "y2": group['y2'],
                }
            ))
            full_text_parts.append(line_text)

        full_text = " ".join(full_text_parts)

        return OCRResult(
            region_id=region_id,
            full_text=full_text,
            lines=lines,
        )
