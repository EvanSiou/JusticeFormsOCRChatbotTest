"""
Cleaning data models.
"""
from typing import List, Optional
from pydantic import BaseModel


class CleanPreviewRequest(BaseModel):
    """Request to preview text cleaning on a test run."""
    test_run_id: str
    use_standard_patterns: bool = True
    custom_words: Optional[List[str]] = None


class CleanSaveRequest(BaseModel):
    """Request to save cleaned text for a test run."""
    test_run_id: str
    use_standard_patterns: bool = True
    custom_words: Optional[List[str]] = None


class CleanedDocumentPreview(BaseModel):
    """Preview of cleaning for a single document."""
    document_id: str
    result_id: str
    original_text: str
    cleaned_text: str


class CleanPreviewResponse(BaseModel):
    """Response for cleaning preview."""
    documents: List[CleanedDocumentPreview]
    total: int
    words_used: List[str]
