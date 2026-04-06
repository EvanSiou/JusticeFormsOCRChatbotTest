"""Base classes for OCR engines (simplified for demo app — no layout detection)."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from PIL import Image


@dataclass
class TextLine:
    """A detected text line."""
    text: str
    confidence: float
    bbox_in_region: Dict[str, int]


@dataclass
class OCRResult:
    """OCR result for a page."""
    region_id: int
    full_text: str
    lines: List[TextLine]


class OCREngineBase(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def extract_text(
        self,
        image: Image.Image,
        regions: list = None,
        prompt: Optional[str] = None,
    ) -> List[OCRResult]:
        pass

    def _process_cropped_image(self, image: Image.Image, region_id: int) -> OCRResult:
        pass

    def to_dict(self, results: List[OCRResult]) -> Dict[str, Any]:
        return {
            "library": self.name,
            "num_regions": len(results),
            "regions": [
                {
                    "region_id": r.region_id,
                    "full_text": r.full_text,
                    "lines": [
                        {"text": l.text, "confidence": l.confidence, "bbox_in_region": l.bbox_in_region}
                        for l in r.lines
                    ],
                }
                for r in results
            ],
        }
