"""Processing session models."""
from typing import Optional
from pydantic import BaseModel


class PageQuality(BaseModel):
    page_num: int
    skew_angle: float = 0.0
    rotation_needed: int = 0
    degradation_score: float = 0.0
    contrast_quality: float = 1.0
    noise_level: float = 0.0
    overall_quality_score: float = 1.0
    issues: list[str] = []


class BiasInjection(BaseModel):
    field_index: int
    field_type: str
    original_value: str
    injected_value: str
    change_type: str  # letter_swap or digit_swap


class ClassifiedField(BaseModel):
    field_type: str
    value: str = ""
    confidence: float = 0.0
    page: int = 1
    area: str = ""


class SessionStatus(BaseModel):
    session_id: str
    status: str
    current_step: str = "upload"
    page_count: int = 0
    detected_form_type: Optional[str] = None
    selected_model: Optional[str] = None


class CompletionSummary(BaseModel):
    total_fields: int = 0
    avg_confidence: float = 0.0
    low_confidence_count: int = 0
    pages_processed: int = 0
    form_type: str = ""
    model_used: str = ""
    processing_time_seconds: float = 0.0
