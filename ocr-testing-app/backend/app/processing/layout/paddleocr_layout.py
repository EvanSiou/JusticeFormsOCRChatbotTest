"""
PaddleOCR PP-DocLayout layout detector implementation.

Uses PaddleOCR's LayoutDetection class with PP-DocLayout_plus-L model
for semantic document layout analysis with 20 region categories
(title, text, table, figure, formula, header, footer, etc.).
"""
from typing import List
from PIL import Image
import numpy as np

from .base import LayoutDetectorBase, Region


class PaddleOCRLayoutDetector(LayoutDetectorBase):
    """Layout detector using PaddleOCR PP-DocLayout."""

    _model = None

    @property
    def name(self) -> str:
        return "paddleocr"

    def _load_model(self):
        """Lazy load the PP-DocLayout model."""
        if PaddleOCRLayoutDetector._model is None:
            from paddleocr import LayoutDetection

            PaddleOCRLayoutDetector._model = LayoutDetection(
                model_name="PP-DocLayout_plus-L",
                threshold=0.3,
                layout_nms=True,
            )
        return PaddleOCRLayoutDetector._model

    def detect(self, image: Image.Image) -> List[Region]:
        """Detect layout regions using PP-DocLayout."""
        model = self._load_model()

        # Convert PIL to numpy array
        image_array = np.array(image)

        # Run detection - returns a generator of result objects
        output = model.predict(image_array, batch_size=1)

        regions = []

        for result in output:
            # Access via dict-style: result['res']['boxes']
            res_data = result.get('res', result) if isinstance(result, dict) else getattr(result, 'res', None)
            if res_data is None:
                # Try dict-style access on the result object directly
                try:
                    res_data = result['res']
                except (TypeError, KeyError):
                    continue

            boxes = res_data.get('boxes', []) if isinstance(res_data, dict) else []

            for i, box in enumerate(boxes):
                label = box.get('label', 'text')
                score = box.get('score', 0.5)
                coordinate = box.get('coordinate', None)

                if coordinate is None or len(coordinate) != 4:
                    continue

                x1, y1, x2, y2 = coordinate

                regions.append(Region(
                    id=i + 1,
                    type=str(label),
                    confidence=float(score),
                    bbox={
                        "x1": int(x1),
                        "y1": int(y1),
                        "x2": int(x2),
                        "y2": int(y2)
                    }
                ))

        # Sort by y-coordinate (top to bottom), then x-coordinate (left to right)
        regions.sort(key=lambda r: (r.bbox["y1"], r.bbox["x1"]))

        # Re-assign IDs after sorting
        for i, region in enumerate(regions):
            region.id = i + 1

        return regions
