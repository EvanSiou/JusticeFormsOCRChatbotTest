"""Setup/configuration API endpoints."""
from fastapi import APIRouter, HTTPException

from ..services import dynamodb
from ..processing.ocr.bedrock_engine import BEDROCK_MODELS
from ..models.setup import AppConfig, PromptCreate, PromptUpdate, FormTypeCreate

router = APIRouter()


@router.get("/system-prompts")
async def get_system_prompts():
    """Return built-in system prompts (read-only, for display on setup page)."""
    from ..processing.quality_detector import QUALITY_DETECTION_PROMPT
    return {
        "prompts": [
            {
                "name": "Quality Detection",
                "prompt_type": "system",
                "description": "Used to analyze document page quality, orientation, and degradation.",
                "prompt_text": QUALITY_DETECTION_PROMPT,
            },
        ]
    }


@router.get("/config")
async def get_config():
    return dynamodb.get_config()


@router.put("/config")
async def update_config(config: AppConfig):
    dynamodb.save_config(config.model_dump())
    return {"message": "Config saved"}


@router.get("/models")
async def list_models():
    return {"models": list(BEDROCK_MODELS.keys())}


@router.get("/prompts")
async def list_prompts(prompt_type: str = None):
    prompts = dynamodb.list_prompts(prompt_type=prompt_type)
    return {"prompts": prompts}


@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str):
    prompt = dynamodb.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    return prompt


@router.post("/prompts")
async def create_prompt(req: PromptCreate):
    return dynamodb.create_prompt(req.model_dump())


@router.put("/prompts/{prompt_id}")
async def update_prompt(prompt_id: str, req: PromptUpdate):
    existing = dynamodb.get_prompt(prompt_id)
    if not existing:
        raise HTTPException(404, "Prompt not found")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updates["prompt_id"] = prompt_id
    dynamodb.update_prompt(prompt_id, {**existing, **updates})
    return {"message": "Prompt updated"}


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str):
    dynamodb.delete_prompt(prompt_id)
    return {"message": "Prompt deleted"}


@router.get("/form-types")
async def list_form_types():
    return {"form_types": dynamodb.list_form_types()}


@router.post("/form-types")
async def create_form_type(req: FormTypeCreate):
    return dynamodb.create_form_type(req.model_dump())


@router.delete("/form-types/{form_type_id}")
async def delete_form_type(form_type_id: str):
    dynamodb.delete_form_type(form_type_id)
    return {"message": "Form type deleted"}
