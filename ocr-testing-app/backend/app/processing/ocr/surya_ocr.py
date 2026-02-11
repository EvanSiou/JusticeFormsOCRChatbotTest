"""
Surya OCR engine implementation.

Uses Surya's batch processing to pass all region bboxes in a single call
instead of processing each region separately.
"""
from typing import List
from PIL import Image

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


class SuryaOCREngine(OCREngineBase):
    """OCR engine using Surya."""

    _foundation_predictor = None
    _recognition_predictor = None

    @property
    def name(self) -> str:
        return "surya"

    def _load_model(self):
        """Lazy load the model."""
        if SuryaOCREngine._recognition_predictor is None:
            from surya.recognition import RecognitionPredictor, FoundationPredictor

            SuryaOCREngine._foundation_predictor = FoundationPredictor()
            SuryaOCREngine._recognition_predictor = RecognitionPredictor(
                SuryaOCREngine._foundation_predictor
            )
        return SuryaOCREngine._recognition_predictor

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text from all regions in a single batch call.
        Surya supports passing multiple bboxes at once.
        """
        predictor = self._load_model()

        # Build list of bboxes for all regions
        all_bboxes = []
        for region in regions:
            b = region.bbox
            all_bboxes.append([b["x1"], b["y1"], b["x2"], b["y2"]])

        # Single batch call with all region bboxes
        surya_results = predictor([image], bboxes=[all_bboxes])

        results = []
        if surya_results and len(surya_results) > 0:
            page_result = surya_results[0]
            text_lines = page_result.text_lines

            # Map Surya text lines back to regions by bbox center point
            region_lines = {r.id: [] for r in regions}

            for text_line in text_lines:
                text = text_line.text
                confidence = getattr(text_line, 'confidence', 0.5)
                bbox = getattr(text_line, 'bbox', [0, 0, image.width, image.height])

                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2

                # Find containing region
                matched = None
                for r in regions:
                    rb = r.bbox
                    if rb["x1"] <= cx <= rb["x2"] and rb["y1"] <= cy <= rb["y2"]:
                        matched = r.id
                        break

                if matched is not None:
                    region_lines[matched].append({
                        "text": text,
                        "confidence": round(float(confidence), 4),
                        "bbox": {
                            "x1": int(bbox[0]),
                            "y1": int(bbox[1]),
                            "x2": int(bbox[2]),
                            "y2": int(bbox[3]),
                        },
                    })

            # Build OCRResults
            for region in regions:
                dets = region_lines.get(region.id, [])
                rb = region.bbox
                lines = []
                full_text_parts = []
                for det in dets:
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
        else:
            # Fallback: empty results for all regions
            for region in regions:
                results.append(OCRResult(
                    region_id=region.id,
                    full_text="",
                    lines=[],
                ))

        return results

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """Process a cropped image with Surya OCR (fallback for single-region)."""
        predictor = self._load_model()

        width, height = image.size
        full_region_bbox = [[0, 0, width, height]]

        results = predictor([image], bboxes=[full_region_bbox])

        lines = []
        full_text_parts = []

        if results and len(results) > 0:
            page_result = results[0]
            for text_line in page_result.text_lines:
                text = text_line.text
                confidence = getattr(text_line, 'confidence', 0.5)
                bbox = getattr(text_line, 'bbox', [0, 0, width, height])

                lines.append(TextLine(
                    text=text,
                    confidence=round(float(confidence), 4),
                    bbox_in_region={
                        "x1": int(bbox[0]),
                        "y1": int(bbox[1]),
                        "x2": int(bbox[2]),
                        "y2": int(bbox[3])
                    }
                ))
                full_text_parts.append(text)

        return OCRResult(
            region_id=region_id,
            full_text=" ".join(full_text_parts),
            lines=lines
        )
