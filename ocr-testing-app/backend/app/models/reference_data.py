"""
Reference data models for ground-truth field definitions and templates.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ReferenceField(BaseModel):
    """A single field definition in a reference data template."""
    field_name: str
    description: str = ""
    field_category: str = ""


class ReferenceDataTemplate(BaseModel):
    """Reusable template defining expected fields for a form type."""
    id: str
    name: str
    form_type_description: str = ""
    fields: List[ReferenceField] = []
    created_by: str
    created_by_name: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateReferenceTemplateRequest(BaseModel):
    name: str
    form_type_description: str = ""
    fields: List[ReferenceField]


class UpdateReferenceTemplateRequest(BaseModel):
    name: Optional[str] = None
    form_type_description: Optional[str] = None
    fields: Optional[List[ReferenceField]] = None


class DocumentReferenceData(BaseModel):
    """Reference data for a single document field."""
    field_name: str
    raw_value: str = ""
    resolved_value: str = ""
    page: str = ""
    section: str = ""


class UpdateDocumentReferenceRequest(BaseModel):
    """Request to update reference data for a document in a batch."""
    reference_data: List[DocumentReferenceData]
