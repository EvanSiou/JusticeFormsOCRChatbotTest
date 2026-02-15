"""
Classification routes.
Allows users to classify fields in verified OCR results using Claude.
"""
import io
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import Response
from PIL import Image

from app.auth.dependencies import get_current_user_id
from app.models.classification import (
    RunClassificationRequest,
    SaveClassificationRequest,
)
from app.models.result import VerificationStatus
from app.services.firestore import FirestoreService
from app.services.storage import StorageService

router = APIRouter()


@router.get("/{test_run_id}/documents")
async def list_documents_for_classification(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """List documents in a test run with verification and classification status."""
    firestore = FirestoreService()

    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found",
        )

    results = await firestore.get_results_by_test_run(test_run_id)

    documents = []
    for result in results:
        # Determine verification status
        is_handwritten = (
            not result.extracted_fields
            and result.ocr_results
            and result.ocr_results.get("full_text") is not None
        )

        if is_handwritten:
            if result.verified_by:
                doc_status = "verified"
            else:
                doc_status = "unverified"
        elif not result.extracted_fields:
            doc_status = "unverified"
        elif all(
            ef.verification_status != VerificationStatus.UNVERIFIED
            for ef in result.extracted_fields
        ):
            doc_status = "verified"
        else:
            doc_status = "unverified"

        documents.append({
            "result_id": result.id,
            "document_id": result.document_id,
            "batch_id": result.batch_id,
            "verification_status": doc_status,
            "has_classification": result.classification_results is not None,
            "has_cleaned_text": bool(result.ocr_results.get("cleaned_text")),
        })

    return {
        "test_run_id": test_run_id,
        "layout_library": test_run.layout_library,
        "ocr_library": test_run.ocr_library,
        "documents": documents,
        "total": len(documents),
    }


@router.get("/{test_run_id}/document/{document_id}")
async def get_document_for_classification(
    test_run_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get document data for classification."""
    firestore = FirestoreService()

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    # Build the important text from verified results
    important_text_parts = []

    # Check if handwritten (text_regions based)
    is_handwritten = (
        not result.extracted_fields
        and result.ocr_results
        and result.ocr_results.get("full_text") is not None
    )

    if is_handwritten:
        text_regions = result.ocr_results.get("text_regions", [])
        for region in text_regions:
            if region.get("is_important"):
                text = region.get("corrected_value") or region.get("text", "")
                if text:
                    important_text_parts.append(text)
    else:
        for ef in result.extracted_fields:
            if ef.is_important:
                value = ef.corrected_value or ef.extracted_value
                if value:
                    important_text_parts.append(value)

    important_text = "\n".join(important_text_parts)

    return {
        "result_id": result.id,
        "document_id": document_id,
        "batch_id": result.batch_id,
        "important_text": important_text,
        "full_text": result.ocr_results.get("full_text", ""),
        "cleaned_text": result.ocr_results.get("cleaned_text", ""),
        "existing_classification": result.classification_results,
        "image_url": f"/api/classify/{test_run_id}/document/{document_id}/image",
    }


@router.post("/{test_run_id}/document/{document_id}/run")
async def run_classification(
    test_run_id: str,
    document_id: str,
    request: RunClassificationRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Run Claude classification on a document."""
    firestore = FirestoreService()
    storage = StorageService()

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    # Always use full OCR text + cleaned text if available
    full_text = result.ocr_results.get("full_text", "")
    cleaned_text = result.ocr_results.get("cleaned_text", "")

    # Prefer cleaned text if available and requested, otherwise use full text
    text_source = "none"
    if request.use_cleaned_text and cleaned_text.strip():
        classify_text = cleaned_text
        text_source = "cleaned"
    elif full_text.strip():
        classify_text = full_text
        text_source = "full"
    else:
        classify_text = ""
        text_source = "none"

    if not classify_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OCR text available for classification. Run OCR first.",
        )

    # Always load document image for visual context
    batch = await firestore.get_batch_by_id(result.batch_id)
    doc_image = None
    if batch:
        for doc in batch.documents:
            if doc.id == document_id:
                try:
                    image_bytes = await storage.download_file(doc.storage_path)
                    doc_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                except Exception as img_err:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to load image: {img_err}")
                break

    # Run classification with selected model
    BEDROCK_CLASSIFIERS = {
        "claude_bedrock", "claude_haiku_bedrock",
        "nova_pro", "nova_lite",
        "pixtral_large",
        "llama4_maverick_bedrock", "llama4_scout",
    }

    VERTEX_CLASSIFIERS = {
        "llama4_maverick_vertex", "llama4_scout_vertex",
    }

    if request.classifier_model == "claude":
        from app.processing.classification.claude_classifier import ClaudeFieldClassifier
        classifier = ClaudeFieldClassifier()
    elif request.classifier_model in BEDROCK_CLASSIFIERS:
        from app.processing.classification.bedrock_classifier import BedrockFieldClassifier
        classifier = BedrockFieldClassifier(request.classifier_model)
    elif request.classifier_model in VERTEX_CLASSIFIERS:
        from app.processing.classification.vertex_classifier import VertexFieldClassifier
        classifier = VertexFieldClassifier(request.classifier_model)
    elif request.classifier_model in ("gpt5", "gpt5_mini"):
        from app.processing.classification.openai_classifier import OpenAIFieldClassifier
        classifier = OpenAIFieldClassifier(request.classifier_model)
    else:
        # Default to Claude via Anthropic API
        from app.processing.classification.claude_classifier import ClaudeFieldClassifier
        classifier = ClaudeFieldClassifier()

    # Resolve classification prompt if provided
    prompt_template = None
    prompt_name = None
    if request.prompt_id and request.prompt_id != "default":
        prompt_doc = await firestore.get_prompt(request.prompt_id)
        if prompt_doc:
            prompt_template = prompt_doc.prompt_text
            prompt_name = prompt_doc.name

    classification_result = classifier.classify_fields(
        ocr_text=classify_text,
        image=doc_image,
        field_types=request.field_types,
        prompt_template=prompt_template,
    )

    # Include metadata about what was sent
    classification_result["text_source"] = text_source
    classification_result["text_sent"] = classify_text
    classification_result["classifier_model"] = request.classifier_model
    if request.prompt_id and request.prompt_id != "default":
        classification_result["prompt_id"] = request.prompt_id
        classification_result["prompt_name"] = prompt_name

    return classification_result


@router.put("/{test_run_id}/document/{document_id}/save")
async def save_classification(
    test_run_id: str,
    document_id: str,
    request: SaveClassificationRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Save classification results for a document."""
    firestore = FirestoreService()

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    success = await firestore.update_result_classification(
        result.id, request.classification_results
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save classification",
        )

    return {
        "message": "Classification saved",
        "result_id": result.id,
    }


@router.get("/{test_run_id}/document/{document_id}/image")
async def get_document_image(
    test_run_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Proxy endpoint to serve document image for classification."""
    firestore = FirestoreService()
    storage = StorageService()

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    batch = await firestore.get_batch_by_id(result.batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found",
        )

    document = None
    for doc in batch.documents:
        if doc.id == document_id:
            document = doc
            break

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in batch",
        )

    image_bytes = await storage.download_file(document.storage_path)
    return Response(content=image_bytes, media_type="image/png")
