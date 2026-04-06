"""Processing pipeline orchestrator.

Manages the full lifecycle: upload → quality detect → auto-correct →
quality gate → form detect → OCR/classify → results → complete.
"""
import io
import time
import logging
from typing import Optional
from PIL import Image

import fitz  # PyMuPDF

from . import s3_storage, dynamodb
from ..processing.quality_detector import detect_page_quality
from ..processing.page_corrector import correct_page
from ..processing.form_detector import detect_form_type
from ..processing.bias_injector import inject_bias_errors
from ..processing.ocr.bedrock_engine import BedrockOCREngine
from ..processing.classification.bedrock_classifier import BedrockFieldClassifier

logger = logging.getLogger(__name__)


def upload_document(file_bytes: bytes, filename: str) -> dict:
    """Upload a document and split into pages.

    Returns session dict with session_id, page_count, etc.
    """
    start_time = time.time()

    # Split PDF into page images
    pages = []
    if filename.lower().endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for i in range(doc.page_count):
            page = doc[i]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            pages.append(img_bytes)
        doc.close()
    else:
        # Single image
        pages.append(file_bytes)

    # Create session
    session = dynamodb.create_session({
        "original_filename": filename,
        "page_count": len(pages),
        "pages": [],
        "start_time": start_time,
    })
    session_id = session["session_id"]

    # Upload pages to S3
    page_info = []
    for i, page_bytes in enumerate(pages):
        key = f"sessions/{session_id}/pages/{i}_original.png"
        s3_storage.upload_bytes(key, page_bytes, content_type="image/png")
        page_info.append({
            "page_num": i,
            "s3_key_original": key,
            "s3_key_corrected": None,
            "quality_score": None,
            "quality_details": None,
            "quality_passed": None,
        })

    dynamodb.update_session(session_id, {"pages": page_info, "status": "uploaded"})
    session["pages"] = page_info
    session["status"] = "uploaded"

    logger.info(f"Uploaded {filename}: {len(pages)} pages, session={session_id}")
    return session


def run_quality_detection(session_id: str, model_name: str = "claude_bedrock") -> list:
    """Run quality detection on all pages. Returns list of quality results."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    pages = session.get("pages", [])
    results = []

    for page in pages:
        img = s3_storage.download_image(page["s3_key_original"])
        quality = detect_page_quality(img, model_name=model_name)
        page["quality_score"] = quality["overall_quality_score"]
        page["quality_details"] = quality
        results.append({"page_num": page["page_num"], **quality})

    dynamodb.update_session(session_id, {"pages": pages, "status": "quality_detected"})
    logger.info(f"Quality detection complete for session {session_id}: {len(results)} pages")
    return results


def run_auto_correction(session_id: str) -> list:
    """Apply auto-corrections to all pages. Returns corrected page info."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    pages = session.get("pages", [])
    results = []

    for page in pages:
        original_img = s3_storage.download_image(page["s3_key_original"])
        quality_data = page.get("quality_details", {})

        corrected_img = correct_page(original_img, quality_data)

        # Upload corrected image
        corrected_key = f"sessions/{session_id}/pages/{page['page_num']}_corrected.png"
        s3_storage.upload_image(corrected_key, corrected_img)
        page["s3_key_corrected"] = corrected_key

        results.append({
            "page_num": page["page_num"],
            "corrections_applied": quality_data.get("issues", []),
        })

    dynamodb.update_session(session_id, {"pages": pages, "status": "auto_corrected"})
    logger.info(f"Auto-correction complete for session {session_id}")
    return results


def evaluate_quality_gate(session_id: str) -> dict:
    """Check corrected pages against quality threshold.

    Returns dict with passed (bool), page_results, threshold.
    """
    session = dynamodb.get_session(session_id)
    config = dynamodb.get_config()
    threshold = config.get("quality_threshold", 0.6)

    pages = session.get("pages", [])
    page_results = []
    all_passed = True

    for page in pages:
        score = page.get("quality_score", 0)
        passed = score >= threshold
        page["quality_passed"] = passed
        if not passed:
            all_passed = False
        page_results.append({
            "page_num": page["page_num"],
            "score": score,
            "threshold": threshold,
            "passed": passed,
        })

    dynamodb.update_session(session_id, {"pages": pages, "status": "quality_gated"})

    return {
        "passed": all_passed,
        "threshold": threshold,
        "page_results": page_results,
    }


def run_form_detection(session_id: str, model_name: str = "claude_bedrock") -> dict:
    """Detect the form type from the first page."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    pages = session.get("pages", [])
    if not pages:
        raise ValueError("No pages in session")

    # Use corrected image if available, otherwise original
    first_page = pages[0]
    img_key = first_page.get("s3_key_corrected") or first_page["s3_key_original"]
    img = s3_storage.download_image(img_key)

    # Get known form types
    form_types = dynamodb.list_form_types()

    result = detect_form_type(img, form_types, model_name=model_name)

    # Find matching form type config
    detected_id = result.get("detected_form_type", "unknown")
    form_config = dynamodb.get_form_type(detected_id)

    # Find the classification prompt for this form type
    cls_prompt_id = None
    if form_config:
        cls_prompt_id = form_config.get("default_classification_prompt_id")

    dynamodb.update_session(session_id, {
        "detected_form_type": detected_id,
        "form_detection_result": result,
        "selected_prompt_id": cls_prompt_id,
        "status": "form_detected",
    })

    return {
        **result,
        "form_config": form_config,
        "classification_prompt_id": cls_prompt_id,
    }


def run_ocr_and_classify(session_id: str, model_name: Optional[str] = None) -> dict:
    """Run OCR and classification on all pages."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    config = dynamodb.get_config()
    model = model_name or config.get("default_model", "claude_bedrock")

    pages = session.get("pages", [])

    # Collect page images (corrected if available)
    page_images = []
    for page in pages:
        img_key = page.get("s3_key_corrected") or page["s3_key_original"]
        page_images.append(s3_storage.download_image(img_key))

    # Step 1: OCR — extract text from all pages
    ocr_engine = BedrockOCREngine(model)
    all_ocr_text = []
    for i, img in enumerate(page_images):
        results = ocr_engine.extract_text(img)
        page_text = results[0].full_text if results else ""
        all_ocr_text.append(page_text)
    combined_text = "\n\n--- Page Break ---\n\n".join(all_ocr_text)

    # Step 2: Classification — extract fields
    classifier = BedrockFieldClassifier(model)

    # Get prompt if available
    prompt_id = session.get("selected_prompt_id")
    prompt_text = None
    if prompt_id:
        prompt = dynamodb.get_prompt(prompt_id)
        if prompt:
            prompt_text = prompt.get("prompt_text")

    # Get field types from form config
    form_type_id = session.get("detected_form_type", "unknown")
    form_config = dynamodb.get_form_type(form_type_id)
    field_types = None
    if form_config and form_config.get("field_definitions"):
        field_types = [f["name"] for f in form_config["field_definitions"]]

    cls_result = classifier.classify_fields(
        ocr_text=combined_text,
        images=page_images,
        field_types=field_types,
        prompt_template=prompt_text,
    )

    classified_fields = cls_result.get("classified_fields", [])

    # Step 3: Inject bias errors
    modified_fields, injection_log = inject_bias_errors(classified_fields)

    dynamodb.update_session(session_id, {
        "ocr_text": combined_text,
        "classification_results": cls_result,
        "classified_fields_original": classified_fields,
        "classified_fields_display": modified_fields,
        "bias_injected_fields": injection_log,
        "bias_challenge_passed": False,
        "selected_model": model,
        "status": "ocr_classified",
    })

    logger.info(
        f"OCR+Classification complete: {len(classified_fields)} fields, "
        f"{len(injection_log)} bias errors injected"
    )

    return {
        "form_type": cls_result.get("form_type", "unknown"),
        "field_count": len(classified_fields),
        "bias_errors_injected": len(injection_log),
        "model_used": model,
    }


def get_results(session_id: str) -> dict:
    """Get results for display: rendered HTML + field data."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    form_type_id = session.get("detected_form_type", "unknown")
    fields = session.get("classified_fields_display", [])
    config = dynamodb.get_config()
    threshold = config.get("quality_threshold", 0.6)

    # Render HTML template
    from ..templates.renderer import render_form_template
    rendered_html = render_form_template(form_type_id, fields, threshold)

    return {
        "session_id": session_id,
        "form_type": form_type_id,
        "classified_fields": fields,
        "rendered_html": rendered_html,
        "bias_challenge_passed": session.get("bias_challenge_passed", False),
        "page_count": session.get("page_count", 0),
    }


def complete_session(session_id: str) -> dict:
    """Mark session as complete and return summary."""
    session = dynamodb.get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    fields = session.get("classified_fields_original", [])
    start_time = session.get("start_time", time.time())
    elapsed = time.time() - start_time

    confidences = [f.get("confidence", 0) for f in fields if f.get("confidence")]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0
    config = dynamodb.get_config()
    threshold = config.get("quality_threshold", 0.6)
    low_conf = sum(1 for c in confidences if c < threshold)

    summary = {
        "total_fields": len(fields),
        "avg_confidence": round(avg_conf, 3),
        "low_confidence_count": low_conf,
        "pages_processed": session.get("page_count", 0),
        "form_type": session.get("detected_form_type", "unknown"),
        "model_used": session.get("selected_model", "unknown"),
        "processing_time_seconds": round(elapsed, 1),
    }

    dynamodb.update_session(session_id, {
        "status": "completed",
        "completed_at": time.time(),
        "summary_stats": summary,
    })

    logger.info(f"Session {session_id} completed: {summary}")
    return summary
