# Layout Detection Processors
from .base import LayoutDetectorBase, Region

# Lazy registry - only import implementations when requested
_LAYOUT_DETECTOR_NAMES = ["doclayout_yolo", "doctr", "paddleocr", "surya"]

def get_layout_detector(name: str) -> LayoutDetectorBase:
    """Get a layout detector by name (lazy import)."""
    if name == "doclayout_yolo":
        from .doclayout_yolo import DocLayoutYOLODetector
        return DocLayoutYOLODetector()
    elif name == "doctr":
        from .doctr_layout import DocTRLayoutDetector
        return DocTRLayoutDetector()
    elif name == "paddleocr":
        from .paddleocr_layout import PaddleOCRLayoutDetector
        return PaddleOCRLayoutDetector()
    elif name == "surya":
        from .surya_layout import SuryaLayoutDetector
        return SuryaLayoutDetector()
    else:
        raise ValueError(f"Unknown layout detector: {name}. Available: {_LAYOUT_DETECTOR_NAMES}")

def list_layout_detectors() -> list[str]:
    """List available layout detector names."""
    return _LAYOUT_DETECTOR_NAMES
