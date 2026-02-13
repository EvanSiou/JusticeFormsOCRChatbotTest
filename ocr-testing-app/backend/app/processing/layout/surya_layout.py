"""
Surya layout detector implementation.

Uses Surya's LayoutPredictor for semantic layout analysis with ~15 categories
(Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture,
Figure, Section-header, Table, Form, Table-of-contents, Handwriting, Text, etc.).
"""
from typing import List
from PIL import Image

from .base import LayoutDetectorBase, Region


class SuryaLayoutDetector(LayoutDetectorBase):
    """Layout detector using Surya LayoutPredictor."""

    _predictor = None

    @property
    def name(self) -> str:
        return "surya"

    def _load_model(self):
        """Lazy load the model."""
        if SuryaLayoutDetector._predictor is None:
            from surya.foundation import FoundationPredictor
            from surya.layout import LayoutPredictor
            from surya.settings import settings

            SuryaLayoutDetector._predictor = LayoutPredictor(
                FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
            )
        return SuryaLayoutDetector._predictor

    def detect(self, image: Image.Image) -> List[Region]:
        """Detect layout regions using Surya LayoutPredictor."""
        predictor = self._load_model()

        # Run layout detection
        results = predictor([image])

        regions = []

        if results and len(results) > 0:
            page_result = results[0]

            # LayoutPredictor returns bboxes with semantic labels
            for i, bbox_obj in enumerate(page_result.bboxes):
                bbox = bbox_obj.bbox  # [x1, y1, x2, y2]
                confidence = getattr(bbox_obj, 'confidence', 0.5)
                label = getattr(bbox_obj, 'label', 'text')

                regions.append(Region(
                    id=i + 1,
                    type=str(label).lower(),
                    confidence=float(confidence),
                    bbox={
                        "x1": int(bbox[0]),
                        "y1": int(bbox[1]),
                        "x2": int(bbox[2]),
                        "y2": int(bbox[3])
                    }
                ))

        # Sort by y-coordinate then x-coordinate
        regions.sort(key=lambda r: (r.bbox["y1"], r.bbox["x1"]))

        # Re-assign IDs after sorting
        for i, region in enumerate(regions):
            region.id = i + 1

        return regions
