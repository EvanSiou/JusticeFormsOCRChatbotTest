"""
Classification data models.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class RunClassificationRequest(BaseModel):
    """Request to run classification on a document."""
    field_types: Optional[List[str]] = None
    use_cleaned_text: bool = True


class SaveClassificationRequest(BaseModel):
    """Request to save classification results."""
    classification_results: Dict[str, Any]
