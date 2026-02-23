"""
Prompt data models for custom OCR and classification prompts.
"""
from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel


class PromptType(str, Enum):
    OCR = "ocr"
    CLASSIFICATION = "classification"
    JUDGE = "judge"
    UNIFIED = "unified"


class PromptInDB(BaseModel):
    """Prompt model as stored in database."""
    id: str
    name: str
    prompt_type: PromptType
    prompt_text: str
    is_default: bool = False
    created_by: str
    created_by_name: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreatePromptRequest(BaseModel):
    """Request to create a new prompt."""
    name: str
    prompt_type: PromptType
    prompt_text: str


class UpdatePromptRequest(BaseModel):
    """Request to update a prompt."""
    name: Optional[str] = None
    prompt_text: Optional[str] = None
