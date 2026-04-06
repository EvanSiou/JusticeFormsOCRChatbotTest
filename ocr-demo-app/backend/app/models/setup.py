"""Setup/config models."""
from typing import Optional
from pydantic import BaseModel


class AppConfig(BaseModel):
    quality_threshold: float = 0.4
    default_model: str = "claude_bedrock"
    default_ocr_prompt_id: Optional[str] = None
    default_classification_prompt_id: Optional[str] = None


class PromptCreate(BaseModel):
    name: str
    prompt_type: str  # ocr, classification, quality_detection, form_detection
    prompt_text: str
    form_type: Optional[str] = None


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    prompt_text: Optional[str] = None
    form_type: Optional[str] = None


class FormTypeCreate(BaseModel):
    form_type_id: str
    display_name: str
    page_count: int = 1
    field_definitions: list[dict] = []
    html_template_name: str = ""
    default_classification_prompt_id: Optional[str] = None
