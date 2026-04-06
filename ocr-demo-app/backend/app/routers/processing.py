"""Processing workflow API endpoints."""
import io
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from ..services import pipeline, dynamodb, s3_storage
from ..processing.bias_injector import validate_bias_corrections

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF or image document to start processing."""
    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Empty file")

    result = pipeline.upload_document(contents, file.filename)
    return {
        "session_id": result["session_id"],
        "page_count": result["page_count"],
        "filename": file.filename,
        "status": result["status"],
    }


@router.post("/{session_id}/quality-detect")
async def quality_detect(session_id: str):
    """Run LLM-based quality detection on all pages."""
    config = dynamodb.get_config()
    model = config.get("default_model", "claude_bedrock")
    results = pipeline.run_quality_detection(session_id, model_name=model)
    return {"pages": results}


@router.post("/{session_id}/auto-correct")
async def auto_correct(session_id: str):
    """Apply auto-corrections based on quality detection."""
    results = pipeline.run_auto_correction(session_id)
    return {"pages": results}


@router.post("/{session_id}/quality-gate")
async def quality_gate(session_id: str):
    """Evaluate corrected pages against quality threshold."""
    result = pipeline.evaluate_quality_gate(session_id)
    return result


@router.post("/{session_id}/quality-gate/proceed")
async def quality_gate_proceed(session_id: str):
    """User chooses to proceed despite failing quality gate."""
    dynamodb.update_session(session_id, {"status": "quality_gated"})
    return {"message": "Proceeding despite quality gate failure"}


@router.post("/{session_id}/detect-form")
async def detect_form(session_id: str):
    """Detect the form type from the document."""
    config = dynamodb.get_config()
    model = config.get("default_model", "claude_bedrock")
    result = pipeline.run_form_detection(session_id, model_name=model)
    return result


@router.post("/{session_id}/ocr-classify")
async def ocr_classify(session_id: str):
    """Run OCR and field classification."""
    result = pipeline.run_ocr_and_classify(session_id)
    return result


@router.get("/{session_id}/results")
async def get_results(session_id: str):
    """Get processed results including rendered HTML template."""
    result = pipeline.get_results(session_id)
    return result


@router.post("/{session_id}/validate-bias")
async def validate_bias(session_id: str):
    """Validate that user corrected the injected bias errors.

    Checks current display field values against the original (pre-injection) values.
    No need for user to explicitly submit corrections — we compare what's in the
    display fields now vs what was injected.

    Tracks attempt count. After 3 failed attempts, reveals hints.
    """
    session = dynamodb.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    injection_log = session.get("bias_injected_fields", [])
    display_fields = session.get("classified_fields_display", [])
    attempt_count = session.get("bias_attempt_count", 0) + 1
    dynamodb.update_session(session_id, {"bias_attempt_count": attempt_count})

    # Check if the user has corrected the injected values back to the originals
    found = 0
    details = []
    for inj in injection_log:
        idx = int(inj["field_index"])  # DynamoDB returns Decimal
        original = str(inj["original_value"])
        injected = str(inj["injected_value"])

        # Get current display value
        current = display_fields[idx].get("value", "") if idx < len(display_fields) else ""
        current = str(current) if current else ""

        # User corrected it if current value matches original (not the injected value)
        if current.strip() == original.strip():
            found += 1
            details.append({**inj, "user_found": True, "current_value": current})
        else:
            details.append({**inj, "user_found": False, "current_value": current})

    result = {
        "passed": found == len(injection_log),
        "found_count": found,
        "total_errors": len(injection_log),
        "details": details,
        "attempt_count": attempt_count,
        "max_attempts": 3,
    }

    if result["passed"]:
        dynamodb.update_session(session_id, {"bias_challenge_passed": True})
    elif attempt_count >= 3:
        result["hints_revealed"] = True
        result["hints"] = [
            {
                "field_index": int(inj["field_index"]),
                "field_type": str(inj["field_type"]),
                "injected_value": str(inj["injected_value"]),
                "correct_value": str(inj["original_value"]),
            }
            for inj in injection_log
        ]

    return result


@router.post("/{session_id}/field/{field_idx}")
async def update_field(session_id: str, field_idx: int, body: dict):
    """Update a single field value (user edit). Tracks all non-bias corrections."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    fields = session.get("classified_fields_display", [])
    if field_idx < 0 or field_idx >= len(fields):
        raise HTTPException(400, f"Invalid field index: {field_idx}")

    old_value = fields[field_idx].get("value", "")
    new_value = body.get("value", "")
    fields[field_idx]["value"] = new_value

    # Track user corrections (non-bias changes)
    bias_indices = {int(inj["field_index"]) for inj in session.get("bias_injected_fields", [])}
    user_corrections = session.get("user_corrections", [])

    if field_idx not in bias_indices and old_value != new_value:
        user_corrections.append({
            "field_index": field_idx,
            "field_type": fields[field_idx].get("field_type", ""),
            "old_value": old_value,
            "new_value": new_value,
        })

    dynamodb.update_session(session_id, {
        "classified_fields_display": fields,
        "user_corrections": user_corrections,
    })
    return {"ok": True, "field_index": field_idx}


@router.post("/{session_id}/complete")
async def complete_session(session_id: str):
    """Mark session as complete and return summary with correction stats."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Allow completing if bias passed OR if hints were revealed (3+ attempts)
    bias_passed = session.get("bias_challenge_passed", False)
    attempts = session.get("bias_attempt_count", 0)
    if not bias_passed and attempts < 3:
        raise HTTPException(400, "Bias challenge must be passed before completing")

    summary = pipeline.complete_session(session_id)

    # Add correction stats
    user_corrections = session.get("user_corrections", [])
    summary["user_corrections_count"] = len(user_corrections)
    summary["user_corrections"] = user_corrections
    summary["bias_attempts"] = session.get("bias_attempt_count", 0)

    return summary


@router.get("/{session_id}/status")
async def get_status(session_id: str):
    """Get current session status."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "session_id": session_id,
        "status": session.get("status", "unknown"),
        "page_count": session.get("page_count", 0),
        "detected_form_type": session.get("detected_form_type"),
        "selected_model": session.get("selected_model"),
        "bias_challenge_passed": session.get("bias_challenge_passed", False),
    }


@router.get("/{session_id}/page/{page_num}/image")
async def get_page_image(session_id: str, page_num: int, corrected: bool = False):
    """Serve a page image (original or corrected)."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    pages = session.get("pages", [])
    if page_num < 0 or page_num >= len(pages):
        raise HTTPException(400, f"Invalid page number: {page_num}")

    page = pages[page_num]
    key = page.get("s3_key_corrected") if corrected and page.get("s3_key_corrected") else page["s3_key_original"]

    image_bytes = s3_storage.download_bytes(key)
    return StreamingResponse(io.BytesIO(image_bytes), media_type="image/png")
