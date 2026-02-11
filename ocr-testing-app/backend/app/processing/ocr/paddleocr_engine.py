"""
PaddleOCR engine implementation.

Runs OCR once on the full document image, then maps detected text
back to layout regions by bounding box overlap. This avoids redundant
text detection on each cropped region.

PaddleOCR 3.x (PP-OCRv5) returns OCRResult objects that subclass dict.
Keys: rec_texts, rec_scores, rec_boxes, rec_polys, dt_polys, etc.

Note: PaddleOCR 3.x on Python 3.13 requires setting HUB_DATASET_ENDPOINT
environment variable before importing. This is handled in this module.
"""
import os
from typing import List
from PIL import Image
import numpy as np

from .base import OCREngineBase, OCRResult, TextLine
from ..layout.base import Region


def _log(msg: str):
    """Print with flush so Cloud Run captures it immediately."""
    print(f"[PADDLE] {msg}", flush=True)


class PaddleOCREngine(OCREngineBase):
    """OCR engine using PaddleOCR (3.x API)."""

    _ocr = None

    @property
    def name(self) -> str:
        return "paddleocr"

    def _load_model(self):
        """Lazy load the model with Python 3.13 workaround."""
        if PaddleOCREngine._ocr is None:
            os.environ.setdefault(
                'HUB_DATASET_ENDPOINT',
                'https://modelscope.cn/api/v1/datasets'
            )

            import logging
            logging.getLogger('ppocr').setLevel(logging.WARNING)

            use_gpu = False
            try:
                import paddle
                use_gpu = paddle.device.is_compiled_with_cuda()
                paddle.set_device('gpu' if use_gpu else 'cpu')
            except Exception:
                import paddle
                paddle.set_device('cpu')

            if not use_gpu:
                os.environ['FLAGS_use_mkldnn'] = '0'

            from paddleocr import PaddleOCR

            PaddleOCREngine._ocr = PaddleOCR(
                lang='en',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                device='gpu' if use_gpu else 'cpu',
                enable_mkldnn=False,
            )
        return PaddleOCREngine._ocr

    def _extract_from_predict_result(self, results) -> list:
        """
        Extract text detections from PaddleOCR predict() results.

        PaddleOCR 3.x returns a list of OCRResult objects that subclass dict.
        Each result has keys: rec_texts, rec_scores, rec_boxes, rec_polys, etc.
        """
        detections = []

        for res in results:
            texts = []
            scores = []
            boxes = None

            # PaddleOCR 3.x OCRResult subclasses dict
            if isinstance(res, dict):
                texts = res.get('rec_texts', []) or []
                scores = res.get('rec_scores', []) or []
                boxes = res.get('rec_boxes', res.get('rec_polys', None))

            # Fallback: .json property (older PaddleOCR versions)
            elif hasattr(res, 'json'):
                json_val = res.json
                if callable(json_val):
                    json_val = json_val()
                if isinstance(json_val, dict):
                    texts = json_val.get('rec_texts', []) or []
                    scores = json_val.get('rec_scores', []) or []
                    boxes = json_val.get('rec_boxes', json_val.get('rec_polys', None))

            # Fallback: direct attribute access
            if not texts:
                for attr in ['rec_texts', 'rec_text', 'texts']:
                    val = getattr(res, attr, None)
                    if val is not None and hasattr(val, '__len__') and len(val) > 0:
                        texts = list(val) if not isinstance(val, list) else val
                        break

            if not scores:
                for attr in ['rec_scores', 'rec_score', 'scores']:
                    val = getattr(res, attr, None)
                    if val is not None and hasattr(val, '__len__') and len(val) > 0:
                        scores = list(val) if not isinstance(val, list) else val
                        break

            if boxes is None:
                for attr in ['rec_boxes', 'rec_polys', 'dt_polys', 'boxes']:
                    val = getattr(res, attr, None)
                    if val is not None and hasattr(val, '__len__') and len(val) > 0:
                        boxes = val
                        break

            # Build detections from extracted data
            for i, text in enumerate(texts):
                if not text:
                    continue
                text_str = str(text).strip()
                if not text_str:
                    continue
                confidence = float(scores[i]) if i < len(scores) else 0.0
                if boxes is not None and i < len(boxes):
                    box = boxes[i]
                    try:
                        if hasattr(box, '__len__') and len(box) == 4:
                            if hasattr(box[0], '__len__'):
                                xs = [float(p[0]) for p in box]
                                ys = [float(p[1]) for p in box]
                                bbox = {"x1": int(min(xs)), "y1": int(min(ys)), "x2": int(max(xs)), "y2": int(max(ys))}
                            else:
                                bbox = {"x1": int(float(box[0])), "y1": int(float(box[1])), "x2": int(float(box[2])), "y2": int(float(box[3]))}
                        elif hasattr(box, '__len__') and len(box) > 4:
                            xs = [float(box[j]) for j in range(0, len(box), 2)]
                            ys = [float(box[j]) for j in range(1, len(box), 2)]
                            bbox = {"x1": int(min(xs)), "y1": int(min(ys)), "x2": int(max(xs)), "y2": int(max(ys))}
                        else:
                            bbox = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
                    except Exception:
                        bbox = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
                else:
                    bbox = {"x1": 0, "y1": 0, "x2": 0, "y2": 0}

                detections.append({
                    "text": text_str,
                    "confidence": round(confidence, 4),
                    "bbox": bbox,
                })

        _log(f"Extracted {len(detections)} text detections")
        return detections

    def extract_text(
        self,
        image: Image.Image,
        regions: List[Region]
    ) -> List[OCRResult]:
        """
        Extract text by running PaddleOCR once on the full image,
        then mapping results to layout regions.
        """
        ocr = self._load_model()
        image_array = np.array(image)

        _log(f"Running predict on image shape={image_array.shape}")

        results = ocr.predict(image_array)

        # Handle generator — PaddleOCR 3.x predict() returns a generator
        if hasattr(results, '__next__'):
            results = list(results)

        detections = self._extract_from_predict_result(results)

        _log(f"Mapping {len(detections)} detections to {len(regions)} regions")

        region_map = self._map_detections_to_regions(detections, regions)
        return self._build_results_from_map(region_map, regions)

    def _process_cropped_image(
        self,
        image: Image.Image,
        region_id: int
    ) -> OCRResult:
        """Process a cropped image with PaddleOCR 3.x (fallback for single-region)."""
        ocr = self._load_model()
        image_array = np.array(image)
        results = ocr.predict(image_array)

        if hasattr(results, '__next__'):
            results = list(results)

        detections = self._extract_from_predict_result(results)

        lines = []
        full_text_parts = []
        for det in detections:
            lines.append(TextLine(
                text=det["text"],
                confidence=det["confidence"],
                bbox_in_region=det["bbox"],
            ))
            full_text_parts.append(det["text"])

        return OCRResult(
            region_id=region_id,
            full_text=" ".join(full_text_parts),
            lines=lines,
        )
