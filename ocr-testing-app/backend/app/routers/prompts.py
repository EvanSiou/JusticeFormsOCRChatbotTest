"""
Prompts router - CRUD for custom OCR and classification prompts.
"""
from fastapi import APIRouter, HTTPException, Depends

from app.auth.dependencies import get_current_user_id, get_current_user_name
from app.models.prompt import CreatePromptRequest, UpdatePromptRequest
from app.services.firestore import FirestoreService

router = APIRouter()

# Default prompt texts (hardcoded in the engines)
DEFAULT_OCR_PROMPT = (
    "Extract ALL text from this document image. "
    "Return every word exactly as it appears, preserving line breaks. "
    "Do not add any commentary, formatting, or markdown — only the raw text content."
)

DEFAULT_CLASSIFICATION_PROMPT = (
    "You are analyzing a court form document. "
    "Use BOTH the image and the OCR text below to extract specific data fields.\n\n"
    "Extract the following fields:\n"
    "{field_types}\n\n"
    "Field descriptions:\n"
    "- defendant_name: The defendant's full name (first and last name)\n"
    "- county: The county name where the court is located\n"
    "- cause_number: The cause/case number\n"
    "- charge: The criminal charge or offense described\n"
    "- condition_order: Any conditions of release or court orders listed\n"
    "- assessed_amount: Any monetary amount assessed (bond fee, fine, etc.)\n"
    "- address: Any address mentioned in the document\n\n"
    "IMPORTANT:\n"
    "- Extract the ACTUAL HANDWRITTEN or FILLED-IN values, not the template labels.\n"
    "- Use the image to read any handwritten text that the OCR may have missed.\n"
    "- Return the classified_fields array in document order (top to bottom).\n"
    "- If a field appears multiple times, include each occurrence.\n\n"
    'Return ONLY valid JSON (no markdown, no code fences) in this format:\n'
    '{\n'
    '  "form_type": "descriptive name of the form type",\n'
    '  "classified_fields": [\n'
    '    {"field_type": "...", "value": "...", "context": "nearby label or description", "confidence": 0.0-1.0}\n'
    '  ]\n'
    '}\n\n'
    "OCR Text:\n"
    "---\n"
    "{ocr_text}\n"
    "---"
)


@router.get("/defaults")
async def get_default_prompts(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get the built-in default prompt texts for reference."""
    return {
        "ocr": DEFAULT_OCR_PROMPT,
        "classification": DEFAULT_CLASSIFICATION_PROMPT,
    }


@router.get("")
async def list_prompts(
    prompt_type: str = None,
    current_user_id: str = Depends(get_current_user_id),
):
    """List all prompts, optionally filtered by type."""
    firestore = FirestoreService()
    prompts = await firestore.list_prompts(prompt_type=prompt_type)
    return {"prompts": [p.model_dump() for p in prompts]}


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a single prompt by ID."""
    firestore = FirestoreService()
    prompt = await firestore.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt.model_dump()


@router.post("")
async def create_prompt(
    request: CreatePromptRequest,
    current_user_id: str = Depends(get_current_user_id),
    current_user_name: str = Depends(get_current_user_name),
):
    """Create a new custom prompt."""
    firestore = FirestoreService()
    prompt = await firestore.create_prompt(
        name=request.name,
        prompt_type=request.prompt_type,
        prompt_text=request.prompt_text,
        created_by=current_user_id,
        created_by_name=current_user_name,
    )
    return prompt.model_dump()


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: str,
    request: UpdatePromptRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Update a custom prompt."""
    firestore = FirestoreService()
    prompt = await firestore.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if prompt.is_default:
        raise HTTPException(status_code=400, detail="Cannot edit default prompts")

    success = await firestore.update_prompt(
        prompt_id,
        name=request.name,
        prompt_text=request.prompt_text,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update prompt")
    return {"status": "updated"}


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Delete a custom prompt."""
    firestore = FirestoreService()
    prompt = await firestore.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if prompt.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default prompts")

    success = await firestore.delete_prompt(prompt_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete prompt")
    return {"status": "deleted"}
