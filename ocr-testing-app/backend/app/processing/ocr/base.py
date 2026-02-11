"""
Base class for OCR engines.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass
from PIL import Image

from ..layout.base import Region


@dataclass
class TextLine:
    """A detected text line within a region."""
    text: str
    confidence: float
    bbox_in_region: Dict[str, int]


@dataclass
class OCRResult:
    """OCR result for a single region."""
    region_id: int
    full_text: str
    lines: List[TextLine]


class OCREngineBase(ABC):
    """
    Abstract base class for OCR engines.

    To add a new OCR engine:
    1. Create a new file in this directory
    2. Create a class that inherits from OCREngineBase
    3. Implement the `name` property and `extract_text` method
    4. Register it in __init__.py
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the OCR engine."""
        pass

    @abstractmethod
    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text from regions in an image.

        Args:
            image: PIL Image object
            regions: List of Region objects from layout detection

        Returns:
            List of OCRResult objects
        """
        pass

    def extract_from_region(
        self,
        image: Image.Image,
        region: Region
    ) -> OCRResult:
        """
        Extract text from a single region.

        Args:
            image: PIL Image object
            region: Region object

        Returns:
            OCRResult object
        """
        bbox = region.bbox
        cropped = image.crop((
            bbox["x1"],
            bbox["y1"],
            bbox["x2"],
            bbox["y2"]
        ))
        return self._process_cropped_image(cropped, region.id)

    @abstractmethod
    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """
        Process a cropped image and extract text.

        Args:
            image: Cropped PIL Image
            region_id: ID of the region

        Returns:
            OCRResult object
        """
        pass

    @staticmethod
    def _map_detections_to_regions(
        detections: List[Dict],
        regions: List[Region]
    ) -> Dict[int, List[Dict]]:
        """
        Map OCR detections to layout regions by bbox center point.

        Args:
            detections: List of dicts with keys 'text', 'confidence', 'bbox'
                        where bbox is {"x1", "y1", "x2", "y2"} in full-image coords
            regions: Layout regions to map into

        Returns:
            Dict mapping region.id -> list of detection dicts
        """
        region_map = {r.id: [] for r in regions}

        for det in detections:
            bbox = det["bbox"]
            cx = (bbox["x1"] + bbox["x2"]) / 2
            cy = (bbox["y1"] + bbox["y2"]) / 2

            # Find the region whose bbox contains the center point
            best_region = None
            for r in regions:
                rb = r.bbox
                if rb["x1"] <= cx <= rb["x2"] and rb["y1"] <= cy <= rb["y2"]:
                    best_region = r.id
                    break

            if best_region is not None:
                region_map[best_region].append(det)

        return region_map

    @staticmethod
    def _build_results_from_map(
        region_map: Dict[int, List[Dict]],
        regions: List[Region]
    ) -> List[OCRResult]:
        """Build OCRResult list from a region -> detections map."""
        results = []
        for region in regions:
            dets = region_map.get(region.id, [])
            rb = region.bbox
            lines = []
            full_text_parts = []
            for det in dets:
                # Convert bbox from full-image coords to region-relative coords
                db = det["bbox"]
                lines.append(TextLine(
                    text=det["text"],
                    confidence=det["confidence"],
                    bbox_in_region={
                        "x1": int(db["x1"] - rb["x1"]),
                        "y1": int(db["y1"] - rb["y1"]),
                        "x2": int(db["x2"] - rb["x1"]),
                        "y2": int(db["y2"] - rb["y1"]),
                    }
                ))
                full_text_parts.append(det["text"])
            results.append(OCRResult(
                region_id=region.id,
                full_text=" ".join(full_text_parts),
                lines=lines,
            ))
        return results

    def to_dict(self, results: List[OCRResult]) -> Dict[str, Any]:
        """Convert OCR results to dictionary format."""
        return {
            "library": self.name,
            "num_regions": len(results),
            "regions": [
                {
                    "region_id": r.region_id,
                    "full_text": r.full_text,
                    "lines": [
                        {
                            "text": line.text,
                            "confidence": line.confidence,
                            "bbox_in_region": line.bbox_in_region,
                        }
                        for line in r.lines
                    ]
                }
                for r in results
            ]
        }
