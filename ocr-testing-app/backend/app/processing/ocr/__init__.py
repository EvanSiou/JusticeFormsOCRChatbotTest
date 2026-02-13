# OCR Engines
from .base import OCREngineBase, OCRResult

# VLM engines skip layout detection and process the full page in a single pass
VLM_ENGINES = ['got_ocr', 'mineru', 'claude']

# Lazy registry - only import implementations when requested
_OCR_ENGINE_NAMES = ["easyocr", "surya", "paddleocr", "tesseract", "trocr", "doctr", "got_ocr", "mineru", "claude"]

def get_ocr_engine(name: str) -> OCREngineBase:
    """Get an OCR engine by name (lazy import)."""
    if name == "easyocr":
        from .easyocr_engine import EasyOCREngine
        return EasyOCREngine()
    elif name == "surya":
        from .surya_ocr import SuryaOCREngine
        return SuryaOCREngine()
    elif name == "paddleocr":
        from .paddleocr_engine import PaddleOCREngine
        return PaddleOCREngine()
    elif name == "tesseract":
        from .tesseract_engine import TesseractEngine
        return TesseractEngine()
    elif name == "trocr":
        from .trocr_engine import TrOCREngine
        return TrOCREngine()
    elif name == "doctr":
        from .doctr_engine import DocTROCREngine
        return DocTROCREngine()
    elif name == "got_ocr":
        from .got_ocr_engine import GotOCREngine
        return GotOCREngine()
    elif name == "mineru":
        from .mineru_engine import MinerUEngine
        return MinerUEngine()
    elif name == "claude":
        from .claude_engine import ClaudeOCREngine
        return ClaudeOCREngine()
    else:
        raise ValueError(f"Unknown OCR engine: {name}. Available: {_OCR_ENGINE_NAMES}")

def list_ocr_engines() -> list[str]:
    """List available OCR engine names."""
    return _OCR_ENGINE_NAMES
