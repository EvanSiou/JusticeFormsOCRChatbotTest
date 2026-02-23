"""
Result data models.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class VerificationStatus(str, Enum):
    """Verification status for an extracted field."""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CORRECTED = "corrected"


class ExtractedField(BaseModel):
    """An extracted field from OCR."""
    field_name: str
    expected_value: str
    extracted_value: str  # Best matching OCR text snippet
    confidence: float  # OCR confidence for extracted_value
    match_score: float  # 0.0 to 1.0 — OCR match score
    is_important: bool = False
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    corrected_value: Optional[str] = None
    classified_field_type: Optional[str] = None  # Classifier's field name that matched
    classified_value: Optional[str] = None
    classification_match_score: Optional[float] = None
    classification_confidence: Optional[float] = None
    judge_score: Optional[float] = None  # LLM judge score for this field
    judge_reasoning: Optional[str] = None  # Judge's reasoning


class ResultBase(BaseModel):
    """Base result model."""
    test_run_id: str
    document_id: str


class ResultInDB(ResultBase):
    """Result model as stored in database."""
    id: str
    batch_id: str
    layout_results: Dict[str, Any]  # Raw layout detection output
    ocr_results: Dict[str, Any]  # Raw OCR output
    extracted_fields: List[ExtractedField]
    overall_accuracy: float
    classification_results: Optional[Dict[str, Any]] = None
    classification_verified_accuracy: Optional[float] = None
    classification_verified_by: Optional[str] = None
    classification_verified_by_name: Optional[str] = None
    classification_verified_at: Optional[datetime] = None
    ocr_accuracy: Optional[float] = None
    classification_accuracy: Optional[float] = None
    judge_results: Optional[Dict[str, Any]] = None
    judge_model: Optional[str] = None
    judge_overall_score: Optional[float] = None
    verified_accuracy: Optional[float] = None
    verified_by: Optional[str] = None
    verified_by_name: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime


class ResultResponse(ResultInDB):
    """Result model for API responses."""
    document_storage_path: Optional[str] = None


class ResultListResponse(BaseModel):
    """Response for listing results."""
    results: List[ResultResponse]
    total: int


class DocumentResult(BaseModel):
    """Detailed result for a single document."""
    document_id: str
    document_path: str
    extracted_fields: List[ExtractedField]
    overall_accuracy: float
    layout_regions: List[Dict[str, Any]]
    ocr_text_by_region: List[Dict[str, Any]]


class VerifyFieldRequest(BaseModel):
    """Request to verify/correct a single extracted field."""
    field_name: str
    verification_status: VerificationStatus
    corrected_value: Optional[str] = None
    is_important: bool = True


class TextRegionVerification(BaseModel):
    """Verification data for a single OCR text region (handwritten docs)."""
    region_index: int
    text: str
    is_important: bool = False
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    corrected_value: Optional[str] = None


class VerifyDocumentRequest(BaseModel):
    """Request to verify/correct all fields for a document result."""
    fields: List[VerifyFieldRequest] = []
    text_regions: Optional[List[TextRegionVerification]] = None
    added_regions: Optional[List[dict]] = None
