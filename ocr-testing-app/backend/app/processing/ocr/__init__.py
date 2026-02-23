# OCR Engines
from .base import OCREngineBase, OCRResult

# VLM engines skip layout detection and process the full page in a single pass
VLM_ENGINES = [
    'got_ocr', 'mineru',
    # Claude (Anthropic direct)
    'claude',
    # Claude (Bedrock)
    'claude_bedrock', 'claude_haiku_bedrock',
    # Amazon Nova (Bedrock)
    'nova_pro_bedrock', 'nova_lite_bedrock',
    # Mistral Pixtral (Bedrock)
    'pixtral_large_bedrock',
    # Llama 4 (Bedrock)
    'llama4_maverick_bedrock', 'llama4_scout_bedrock',
    # Llama 4 (Vertex AI)
    'llama4_maverick_vertex', 'llama4_scout_vertex',
    # OpenAI
    'gpt5', 'gpt5_mini',
]

# Bedrock engine names (all use BedrockOCREngine)
BEDROCK_ENGINE_NAMES = {
    'claude_bedrock', 'claude_haiku_bedrock',
    'nova_pro_bedrock', 'nova_lite_bedrock',
    'pixtral_large_bedrock',
    'llama4_maverick_bedrock', 'llama4_scout_bedrock',
}

# Vertex AI engine names (all use VertexOCREngine)
VERTEX_ENGINE_NAMES = {
    'llama4_maverick_vertex', 'llama4_scout_vertex',
}

# Lazy registry - only import implementations when requested
_OCR_ENGINE_NAMES = [
    "easyocr", "surya", "paddleocr", "tesseract", "trocr", "doctr",
    "got_ocr", "mineru",
    "claude",
    "claude_bedrock", "claude_haiku_bedrock",
    "nova_pro_bedrock", "nova_lite_bedrock",
    "pixtral_large_bedrock",
    "llama4_maverick_bedrock", "llama4_scout_bedrock",
    "llama4_maverick_vertex", "llama4_scout_vertex",
    "gpt5", "gpt5_mini",
]

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
    elif name in BEDROCK_ENGINE_NAMES:
        from .bedrock_engine import BedrockOCREngine
        return BedrockOCREngine(name)
    elif name in VERTEX_ENGINE_NAMES:
        from .vertex_engine import VertexOCREngine
        return VertexOCREngine(name)
    elif name in ("gpt5", "gpt5_mini"):
        from .openai_engine import OpenAIVisionEngine
        return OpenAIVisionEngine(name)
    else:
        raise ValueError(f"Unknown OCR engine: {name}. Available: {_OCR_ENGINE_NAMES}")

def list_ocr_engines() -> list[str]:
    """List available OCR engine names."""
    return _OCR_ENGINE_NAMES
