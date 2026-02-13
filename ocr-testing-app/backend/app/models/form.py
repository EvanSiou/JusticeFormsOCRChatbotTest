"""
Form (base template) data models.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class FormType(str, Enum):
    """Type of form template."""
    EMPTY = "empty"
    HANDWRITTEN = "handwritten"


class FieldType(str, Enum):
    """Type of field for synthetic data generation."""
    NUMERIC_SHORT = "numeric_short"
    TEXT_SHORT = "text_short"
    SENTENCE = "sentence"
    FULL_NAME = "full_name"
    DAY_MONTH = "day_month"
    TWO_DIGIT_YEAR = "2_digit_year"
    FOUR_DIGIT_YEAR = "4_digit_year"


class FieldMapping(BaseModel):
    """A field mapping with coordinates on the form."""
    name: str
    x: int
    y: int
    width: int
    height: int
    font_size: int = 12
    font_color: str = "#000000"
    field_type: FieldType = FieldType.TEXT_SHORT


class FormBase(BaseModel):
    """Base form model."""
    name: str


class FormCreate(FormBase):
    """Model for creating a new form."""
    form_type: FormType = FormType.EMPTY


class FormInDB(FormBase):
    """Form model as stored in database."""
    id: str
    form_type: FormType = FormType.EMPTY
    storage_path: str
    uploaded_by: str
    uploaded_by_name: str = ""
    uploaded_at: datetime
    field_mappings: List[FieldMapping] = []
    template_words: Optional[List[str]] = None
    thumbnail_path: Optional[str] = None


class FormResponse(FormInDB):
    """Form model for API responses."""
    pass


class FormListResponse(BaseModel):
    """Response for listing forms."""
    forms: List[FormResponse]
    total: int


class UpdateFieldMappingsRequest(BaseModel):
    """Request to update field mappings."""
    field_mappings: List[FieldMapping]


class UpdateFieldMappingsWithConfigRequest(BaseModel):
    """Request to import field config from notebook format."""
    fields: List[dict]  # Accepts notebook-style [{name, x, y, ...}]


class UpdateTemplateWordsRequest(BaseModel):
    """Request to update template words for text cleanup."""
    template_words: List[str]
