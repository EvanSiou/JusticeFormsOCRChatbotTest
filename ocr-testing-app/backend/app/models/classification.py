"""
Classification data models.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class ClassificationErrorReason(str, Enum):
    """Reason why a classified field is incorrect."""
    WRONG_CLASSIFICATION = "wrong_classification"
    WRONG_VALUE = "wrong_value"
    PARTIAL_MATCH = "partial_match"
    NOT_FOUND = "not_found"


class ClassifiedFieldVerification(BaseModel):
    """Verification data for a single classified field."""
    field_index: int
    is_correct: bool
    error_reason: Optional[ClassificationErrorReason] = None
    corrected_field_type: Optional[str] = None
    corrected_value: Optional[str] = None


class MissedField(BaseModel):
    """A field the classifier missed."""
    field_type: str
    value: str


class VerifyClassificationRequest(BaseModel):
    """Request to verify classification results."""
    field_verifications: List[ClassifiedFieldVerification]
    missed_fields: List[MissedField] = []


class RunClassificationRequest(BaseModel):
    """Request to run classification on a document."""
    field_types: Optional[List[str]] = None
    use_cleaned_text: bool = True
    classifier_model: str = "claude"  # "claude", "llama4_maverick", "gpt5", "gpt5_mini", "mistral_medium3"
    prompt_id: Optional[str] = None


class SaveClassificationRequest(BaseModel):
    """Request to save classification results."""
    classification_results: Dict[str, Any]
