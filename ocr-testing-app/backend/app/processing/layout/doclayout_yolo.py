"""
DocLayout-YOLO layout detector implementation.
"""
from typing import List
from PIL import Image
import numpy as np

from .base import LayoutDetectorBase, Region


class DocLayoutYOLODetector(LayoutDetectorBase):
    """Layout detector using DocLayout-YOLO."""

    _model = None

    @property
    def name(self) -> str:
        return "doclayout_yolo"

    def _load_model(self):
        """Lazy load the model."""
        if DocLayoutYOLODetector._model is None:
            from huggingface_hub import hf_hub_download
            from doclayout_yolo import YOLOv10

            filepath = hf_hub_download(
                repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
                filename="doclayout_yolo_docstructbench_imgsz1024.pt"
            )
            DocLayoutYOLODetector._model = YOLOv10(filepath)
        return DocLayoutYOLODetector._model

    def detect(self, image: Image.Image) -> List[Region]:
        """Detect layout regions using DocLayout-YOLO."""
        model = self._load_model()

        # Convert PIL to numpy array
        image_array = np.array(image)

        # Detect GPU availability
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Run detection
        results = model.predict(
            image_array,
            imgsz=1024,
            conf=0.2,
            device=device
        )

        regions = []

        for idx, result in enumerate(results):
            boxes = result.boxes

            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])

                # Get class name
                class_name = result.names.get(class_id, f"class_{class_id}")

                regions.append(Region(
                    id=i + 1,
                    type=class_name,
                    confidence=confidence,
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
