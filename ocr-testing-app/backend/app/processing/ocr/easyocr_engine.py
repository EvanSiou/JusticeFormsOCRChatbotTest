"""
EasyOCR engine implementation.

Runs OCR once on the full document image, then maps detected text
back to layout regions by bounding box overlap. This avoids redundant
text detection on each cropped region.
"""
from typing import List, Optional
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class EasyOCREngine(OCREngineBase):
    """OCR engine using EasyOCR."""

    _reader = None

    @property
    def name(self) -> str:
        return "easyocr"

    def _load_model(self):
        """Lazy load the model."""
        if EasyOCREngine._reader is None:
            import easyocr
            import torch

            EasyOCREngine._reader = easyocr.Reader(
                ['en'],
                gpu=torch.cuda.is_available(),
                verbose=False
            )
        return EasyOCREngine._reader

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region],
        prompt: Optional[str] = None
    ) -> List[OCRResult]:
        """
        Extract text by running EasyOCR once on the full image,
        then mapping results to layout regions.
        """
        reader = self._load_model()
        image_array = np.array(image)

        # Run OCR once on the full document image
        ocr_result = reader.readtext(image_array)

        # Collect all detections with full-image bboxes
        detections = []
        for detection in ocr_result:
            bbox_points, text, confidence = detection
            # bbox_points is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
            x_coords = [p[0] for p in bbox_points]
            y_coords = [p[1] for p in bbox_points]

            detections.append({
                "text": text,
                "confidence": round(float(confidence), 4),
                "bbox": {
                    "x1": int(min(x_coords)),
                    "y1": int(min(y_coords)),
                    "x2": int(max(x_coords)),
                    "y2": int(max(y_coords)),
                },
            })

        # Map detections to layout regions and build results
        region_map = self._map_detections_to_regions(detections, regions)
        return self._build_results_from_map(region_map, regions)

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """Process a cropped image with EasyOCR (fallback for single-region)."""
        reader = self._load_model()
        image_array = np.array(image)
        ocr_result = reader.readtext(image_array)

        lines = []
        full_text_parts = []

        for detection in ocr_result:
            bbox_points, text, confidence = detection
            x_coords = [p[0] for p in bbox_points]
            y_coords = [p[1] for p in bbox_points]

            lines.append(TextLine(
                text=text,
                confidence=round(float(confidence), 4),
                bbox_in_region={
                    "x1": int(min(x_coords)),
                    "y1": int(min(y_coords)),
                    "x2": int(max(x_coords)),
                    "y2": int(max(y_coords))
                }
            ))
            full_text_parts.append(text)

        return OCRResult(
            region_id=region_id,
            full_text=" ".join(full_text_parts),
            lines=lines
        )
