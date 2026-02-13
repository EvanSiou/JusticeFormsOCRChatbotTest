"""
DocTR OCR engine implementation.

Uses docTR's recognition_predictor with the parseq architecture
for text recognition on cropped regions from layout detection.
"""
from typing import List
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class DocTROCREngine(OCREngineBase):
    """OCR engine using docTR recognition (parseq model)."""

    _model = None

    @property
    def name(self) -> str:
        return "doctr"

    def _load_model(self):
        """Lazy load the recognition model."""
        if DocTROCREngine._model is None:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context

            from doctr.models import recognition_predictor

            DocTROCREngine._model = recognition_predictor(
                arch='parseq',
                pretrained=True
            )
        return DocTROCREngine._model

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text from all regions by cropping each region
        and running docTR recognition in a single batch.
        """
        model = self._load_model()

        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Crop all regions and batch them
        cropped_images = []
        for region in regions:
            bbox = region.bbox
            cropped = image.crop((bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]))
            cropped_images.append(np.array(cropped))

        if not cropped_images:
            return []

        # Run recognition on all crops in one batch
        predictions = model(cropped_images)

        # Build results
        results = []
        for i, region in enumerate(regions):
            if i < len(predictions):
                text, confidence = predictions[i]
                text = text.strip()
            else:
                text, confidence = "", 0.0

            lines = []
            if text:
                lines.append(TextLine(
                    text=text,
                    confidence=round(float(confidence), 4),
                    bbox_in_region={
                        "x1": 0,
                        "y1": 0,
                        "x2": region.bbox["x2"] - region.bbox["x1"],
                        "y2": region.bbox["y2"] - region.bbox["y1"],
                    }
                ))

            results.append(OCRResult(
                region_id=region.id,
                full_text=text,
                lines=lines,
            ))

        return results

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """Process a single cropped image with docTR recognition."""
        model = self._load_model()

        if image.mode != 'RGB':
            image = image.convert('RGB')

        image_array = np.array(image)
        predictions = model([image_array])

        text, confidence = "", 0.0
        if predictions:
            text, confidence = predictions[0]
            text = text.strip()

        lines = []
        if text:
            lines.append(TextLine(
                text=text,
                confidence=round(float(confidence), 4),
                bbox_in_region={
                    "x1": 0,
                    "y1": 0,
                    "x2": image.width,
                    "y2": image.height,
                }
            ))

        return OCRResult(
            region_id=region_id,
            full_text=text,
            lines=lines,
        )
