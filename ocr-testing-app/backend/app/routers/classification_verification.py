"""
Classification verification routes.
Allows users to review and verify classification results.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import Response

from app.auth.dependencies import get_current_user_id
from app.models.classification import VerifyClassificationRequest
from app.services.firestore import FirestoreService
from app.services.storage import StorageService

router = APIRouter()


@router.get("/{test_run_id}/documents")
async def list_documents_for_classification_verification(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """List documents in a test run with classification and verification status."""
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
        has_classification = result.classification_results is not None
        classification_verified = result.classification_verified_by is not None

        # Extract classifier model from saved classification
        classifier_model = None
        if has_classification:
            classifier_model = result.classification_results.get("classifier_model")

        documents.append({
            "result_id": result.id,
            "document_id": result.document_id,
            "batch_id": result.batch_id,
            "has_classification": has_classification,
            "classification_verified": classification_verified,
            "classification_verified_accuracy": result.classification_verified_accuracy,
            "classifier_model": classifier_model,
        })

    return {
        "test_run_id": test_run_id,
        "layout_library": test_run.layout_library,
        "ocr_library": test_run.ocr_library,
        "documents": documents,
        "total": len(documents),
        "classified": sum(1 for d in documents if d["has_classification"]),
        "verified": sum(1 for d in documents if d["classification_verified"]),
    }


@router.get("/{test_run_id}/document/{document_id}")
async def get_document_for_classification_verification(
    test_run_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get classification data for verification."""
    firestore = FirestoreService()

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    if not result.classification_results:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No classification results for this document. Run classification first.",
        )

    return {
        "result_id": result.id,
        "document_id": document_id,
        "batch_id": result.batch_id,
        "classification_results": result.classification_results,
        "classification_verified_accuracy": result.classification_verified_accuracy,
        "image_url": f"/api/classify-verify/{test_run_id}/document/{document_id}/image",
    }


@router.get("/{test_run_id}/document/{document_id}/image")
async def get_document_image(
    test_run_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Proxy endpoint to serve document image for classification verification."""
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


@router.put("/{test_run_id}/document/{document_id}/verify")
async def verify_classification(
    test_run_id: str,
    document_id: str,
    request: VerifyClassificationRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Submit verification for classification results."""
    firestore = FirestoreService()

    user = await firestore.get_user_by_id(current_user_id)
    verified_by_name = user.email if user else ""

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    if not result.classification_results:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No classification results to verify.",
        )

    # Calculate accuracy: correct / (total_classified + missed)
    total_classified = len(request.field_verifications)
    correct_count = sum(1 for fv in request.field_verifications if fv.is_correct)
    missed_count = len(request.missed_fields)
    denominator = total_classified + missed_count

    verified_accuracy = correct_count / denominator if denominator > 0 else 0.0

    # Embed verification data into classification_results
    classification_results = dict(result.classification_results)
    classification_results["verification"] = {
        "field_verifications": [fv.model_dump() for fv in request.field_verifications],
        "missed_fields": [mf.model_dump() for mf in request.missed_fields],
        "verified_accuracy": round(verified_accuracy, 4),
        "verified_by": current_user_id,
        "verified_by_name": verified_by_name,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }

    success = await firestore.update_result_classification_verification(
        result_id=result.id,
        classification_results=classification_results,
        verified_accuracy=verified_accuracy,
        verified_by=current_user_id,
        verified_by_name=verified_by_name,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save classification verification",
        )

    return {
        "message": "Classification verification submitted",
        "verified_accuracy": round(verified_accuracy, 4),
        "total_fields": total_classified,
        "correct_fields": correct_count,
        "missed_fields": missed_count,
    }


@router.get("/{test_run_id}/summary")
async def get_classification_verification_summary(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get classification verification progress for a test run."""
    firestore = FirestoreService()

    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found",
        )

    results = await firestore.get_results_by_test_run(test_run_id)

    total_classified = 0
    verified = 0

    for result in results:
        if result.classification_results is not None:
            total_classified += 1
            if result.classification_verified_by is not None:
                verified += 1

    return {
        "test_run_id": test_run_id,
        "total_classified": total_classified,
        "verified": verified,
        "unverified": total_classified - verified,
        "progress_percent": (
            (verified / total_classified * 100) if total_classified > 0 else 0
        ),
    }
