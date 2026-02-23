"""
Results viewing routes.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from fastapi.responses import Response
from typing import Optional, List

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from app.auth.dependencies import get_current_user_id
from app.models.result import ResultResponse, ResultListResponse, DocumentResult
from app.services.firestore import FirestoreService
from app.services.storage import StorageService

router = APIRouter()


@router.get("", response_model=ResultListResponse)
async def list_results(
    test_run_id: Optional[str] = Query(None),
    batch_id: Optional[str] = Query(None),
    current_user_id: str = Depends(get_current_user_id)
):
    """
    List results with optional filtering.
    Filter by test_run_id and/or batch_id.
    """
    firestore = FirestoreService()

    if test_run_id:
        # Get results for specific test run
        results = await firestore.get_results_by_test_run(test_run_id)

        # Filter by batch_id if provided
        if batch_id:
            results = [r for r in results if r.batch_id == batch_id]
    else:
        # Without test_run_id, we'd need to implement a more general query
        # For now, return empty if no test_run_id
        results = []

    return ResultListResponse(
        results=[ResultResponse(**r.model_dump()) for r in results],
        total=len(results)
    )


@router.get("/{test_run_id}", response_model=ResultListResponse)
async def get_results_for_test_run(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get all results for a specific test run."""
    firestore = FirestoreService()

    # Verify test run exists
    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found"
        )

    results = await firestore.get_results_by_test_run(test_run_id)

    return ResultListResponse(
        results=[ResultResponse(**r.model_dump()) for r in results],
        total=len(results)
    )


@router.get("/{test_run_id}/document/{document_id}")
async def get_document_result(
    test_run_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get detailed result for a specific document."""
    firestore = FirestoreService()

    # Get result
    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found"
        )

    # Get batch to find document storage path
    batch = await firestore.get_batch_by_id(result.batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )

    # Find document in batch
    document = None
    for doc in batch.documents:
        if doc.id == document_id:
            document = doc
            break

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in batch"
        )

    # Build proxy URL for the document image (avoids signed URL issues on Cloud Run)
    document_url = f"/api/results/{test_run_id}/document/{document_id}/image"

    # Determine page count for multi-page PDFs
    page_count = 1
    if document.storage_path.lower().endswith('.pdf') and PYMUPDF_AVAILABLE:
        storage = StorageService()
        try:
            file_bytes = await storage.download_file(document.storage_path)
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = len(pdf_doc)
            pdf_doc.close()
        except Exception:
            full_text = result.ocr_results.get("full_text", "") if result.ocr_results else ""
            markers = full_text.count("--- Page ")
            if markers > 1:
                page_count = markers

    return {
        "document_id": document_id,
        "document_url": document_url,
        "expected_field_values": document.field_values,
        "extracted_fields": [ef.model_dump() for ef in result.extracted_fields],
        "overall_accuracy": result.overall_accuracy,
        "verified_accuracy": result.verified_accuracy,
        "layout_results": result.layout_results,
        "ocr_results": result.ocr_results,
        "page_count": page_count,
        "ocr_accuracy": result.ocr_accuracy,
        "classification_accuracy": result.classification_accuracy,
        "classification_results": result.classification_results,
        "judge_results": result.judge_results,
        "judge_model": result.judge_model,
        "judge_overall_score": result.judge_overall_score,
    }


@router.get("/{test_run_id}/document/{document_id}/image")
async def get_document_image(
    test_run_id: str,
    document_id: str,
    page: int = Query(0, ge=0, description="Page number (0-indexed) for multi-page documents"),
    current_user_id: str = Depends(get_current_user_id)
):
    """Proxy endpoint to serve document images directly from GCS.
    For multi-page PDF documents, converts the requested page to PNG."""
    firestore = FirestoreService()
    storage = StorageService()

    # Get result to find batch_id
    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found"
        )

    # Get batch to find document storage path
    batch = await firestore.get_batch_by_id(result.batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )

    # Find document in batch
    document = None
    for doc in batch.documents:
        if doc.id == document_id:
            document = doc
            break

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in batch"
        )

    # Download image bytes from GCS and serve directly
    image_bytes = await storage.download_file(document.storage_path)

    # If it's a PDF, convert the requested page to PNG
    if document.storage_path.lower().endswith('.pdf') and PYMUPDF_AVAILABLE:
        pdf_doc = fitz.open(stream=image_bytes, filetype="pdf")
        if page >= len(pdf_doc):
            pdf_doc.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Page {page} out of range (0-{len(pdf_doc)-1})"
            )
        page_obj = pdf_doc[page]
        mat = fitz.Matrix(2, 2)
        pix = page_obj.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        pdf_doc.close()
        return Response(content=png_bytes, media_type="image/png")

    return Response(content=image_bytes, media_type="image/png")


@router.get("/{test_run_id}/summary")
async def get_test_run_summary(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get summary statistics for a test run."""
    firestore = FirestoreService()

    # Get test run
    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found"
        )

    # Get all results
    results = await firestore.get_results_by_test_run(test_run_id)

    if not results:
        return {
            "test_run_id": test_run_id,
            "total_documents": 0,
            "average_accuracy": 0.0,
            "field_accuracies": {},
            "accuracy_distribution": {}
        }

    # Calculate statistics - prefer verified_accuracy over overall_accuracy
    def best_accuracy(r):
        if r.verified_accuracy is not None:
            return r.verified_accuracy
        return r.overall_accuracy

    total_accuracy = sum(best_accuracy(r) for r in results)
    avg_accuracy = total_accuracy / len(results)

    # Per-field accuracy (only for important fields)
    field_scores = {}
    field_counts = {}

    for result in results:
        for field in result.extracted_fields:
            if not field.is_important:
                continue
            if field.field_name not in field_scores:
                field_scores[field.field_name] = 0.0
                field_counts[field.field_name] = 0

            field_scores[field.field_name] += field.match_score
            field_counts[field.field_name] += 1

    # Fallback: if no fields have is_important, use all fields (legacy data)
    if not field_scores:
        for result in results:
            for field in result.extracted_fields:
                if field.field_name not in field_scores:
                    field_scores[field.field_name] = 0.0
                    field_counts[field.field_name] = 0
                field_scores[field.field_name] += field.match_score
                field_counts[field.field_name] += 1

    field_accuracies = {
        name: field_scores[name] / field_counts[name]
        for name in field_scores
    }

    # Accuracy distribution (buckets)
    distribution = {
        "0-20%": 0,
        "20-40%": 0,
        "40-60%": 0,
        "60-80%": 0,
        "80-100%": 0
    }

    for result in results:
        acc = best_accuracy(result) * 100
        if acc < 20:
            distribution["0-20%"] += 1
        elif acc < 40:
            distribution["20-40%"] += 1
        elif acc < 60:
            distribution["40-60%"] += 1
        elif acc < 80:
            distribution["60-80%"] += 1
        else:
            distribution["80-100%"] += 1

    # Compute average OCR accuracy (from unified pipeline)
    ocr_acc_values = [r.ocr_accuracy for r in results if r.ocr_accuracy is not None]
    avg_ocr_accuracy = round(sum(ocr_acc_values) / len(ocr_acc_values), 4) if ocr_acc_values else None

    # Compute average classification accuracy
    cls_acc_values = [r.classification_accuracy for r in results if r.classification_accuracy is not None]
    avg_classification_accuracy = round(sum(cls_acc_values) / len(cls_acc_values), 4) if cls_acc_values else None

    # Compute average judge score
    judge_values = [r.judge_overall_score for r in results if r.judge_overall_score is not None]
    avg_judge_score = round(sum(judge_values) / len(judge_values), 4) if judge_values else None

    return {
        "test_run_id": test_run_id,
        "layout_library": test_run.layout_library,
        "ocr_library": test_run.ocr_library,
        "classifier_model": test_run.classifier_model,
        "judge_model": test_run.judge_model,
        "is_unified": test_run.is_unified,
        "total_documents": len(results),
        "average_accuracy": round(avg_accuracy, 4),
        "average_ocr_accuracy": avg_ocr_accuracy,
        "average_classification_accuracy": avg_classification_accuracy,
        "average_judge_score": avg_judge_score,
        "field_accuracies": {k: round(v, 4) for k, v in field_accuracies.items()},
        "accuracy_distribution": distribution
    }
