"""
Verification routes.
Allows users to review, confirm, and correct OCR results.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import Response
from typing import Optional

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from app.auth.dependencies import get_current_user_id
from app.models.result import (
    VerifyDocumentRequest,
    VerificationStatus,
    ExtractedField,
)
from app.services.firestore import FirestoreService
from app.services.storage import StorageService

router = APIRouter()


@router.get("/{test_run_id}/documents")
async def list_documents_for_verification(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """List documents in a test run with their verification status."""
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
        # Check if this is a handwritten batch result (no extracted fields, has ocr_results)
        is_handwritten = (
            not result.extracted_fields
            and result.ocr_results
            and result.ocr_results.get("full_text") is not None
        )

        # Determine verification status for the document
        if is_handwritten:
            # Handwritten: check verified_by and text_regions for status
            if result.verified_by:
                text_regions = result.ocr_results.get("text_regions", [])
                has_corrections = any(
                    r.get("verification_status") == VerificationStatus.CORRECTED.value
                    for r in text_regions
                )
                has_added = any(r.get("user_added") for r in text_regions)
                doc_status = "corrected" if (has_corrections or has_added) else "verified"
            else:
                doc_status = "unverified"
        elif not result.extracted_fields:
            doc_status = "unverified"
        elif all(
            ef.verification_status != VerificationStatus.UNVERIFIED
            for ef in result.extracted_fields
        ):
            has_corrections = any(
                ef.verification_status == VerificationStatus.CORRECTED
                for ef in result.extracted_fields
            )
            doc_status = "corrected" if has_corrections else "verified"
        else:
            doc_status = "unverified"

        documents.append({
            "result_id": result.id,
            "document_id": result.document_id,
            "batch_id": result.batch_id,
            "overall_accuracy": result.overall_accuracy,
            "verified_accuracy": result.verified_accuracy,
            "verification_status": doc_status,
            "is_handwritten": is_handwritten,
        })

    return {
        "test_run_id": test_run_id,
        "layout_library": test_run.layout_library,
        "ocr_library": test_run.ocr_library,
        "documents": documents,
        "total": len(documents),
        "verified": sum(1 for d in documents if d["verification_status"] != "unverified"),
    }


@router.get("/{test_run_id}/document/{document_id}")
async def get_document_for_verification(
    test_run_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get document details for verification."""
    firestore = FirestoreService()

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    # Get batch to find document info
    batch = await firestore.get_batch_by_id(result.batch_id)
    document = None
    if batch:
        for doc in batch.documents:
            if doc.id == document_id:
                document = doc
                break

    image_url = f"/api/verify/{test_run_id}/document/{document_id}/image"

    # Determine page count from storage path or OCR text
    page_count = 1
    if document and document.storage_path.lower().endswith('.pdf') and PYMUPDF_AVAILABLE:
        storage = StorageService()
        try:
            file_bytes = await storage.download_file(document.storage_path)
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = len(pdf_doc)
            pdf_doc.close()
        except Exception:
            # Fall back to counting page markers in OCR text
            full_text = result.ocr_results.get("full_text", "") if result.ocr_results else ""
            markers = full_text.count("--- Page ")
            if markers > 1:
                page_count = markers

    return {
        "result_id": result.id,
        "document_id": document_id,
        "document_url": image_url,
        "batch_id": result.batch_id,
        "batch_type": batch.batch_type if batch else "synthetic",
        "expected_field_values": document.field_values if document else {},
        "extracted_fields": [ef.model_dump() for ef in result.extracted_fields],
        "overall_accuracy": result.overall_accuracy,
        "verified_accuracy": result.verified_accuracy,
        "layout_results": result.layout_results,
        "ocr_results": result.ocr_results,
        "page_count": page_count,
    }


@router.get("/{test_run_id}/document/{document_id}/image")
async def get_document_image(
    test_run_id: str,
    document_id: str,
    page: int = Query(0, ge=0, description="Page number (0-indexed) for multi-page documents"),
    current_user_id: str = Depends(get_current_user_id),
):
    """Proxy endpoint to serve document image for verification.
    For multi-page PDF documents, converts the requested page to PNG."""
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


@router.put("/{test_run_id}/document/{document_id}/verify")
async def verify_document(
    test_run_id: str,
    document_id: str,
    request: VerifyDocumentRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Submit verification for a document's extracted fields or text regions."""
    firestore = FirestoreService()

    # Look up user email
    user = await firestore.get_user_by_id(current_user_id)
    verified_by_name = user.email if user else ""

    result = await firestore.get_result_by_document(test_run_id, document_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    # === Handwritten path: text_regions provided ===
    if request.text_regions is not None:
        ocr_results = dict(result.ocr_results)
        existing_regions = list(ocr_results.get("text_regions", []))

        # Update existing regions with verification data
        for tr in request.text_regions:
            if 0 <= tr.region_index < len(existing_regions):
                existing_regions[tr.region_index]["is_important"] = tr.is_important
                existing_regions[tr.region_index]["verification_status"] = tr.verification_status.value
                existing_regions[tr.region_index]["corrected_value"] = tr.corrected_value

        # Append user-added regions
        if request.added_regions:
            for added in request.added_regions:
                existing_regions.append({
                    "text": added.get("text", ""),
                    "confidence": 1.0,
                    "is_important": True,
                    "verification_status": VerificationStatus.VERIFIED.value,
                    "corrected_value": None,
                    "user_added": True,
                })

        ocr_results["text_regions"] = existing_regions

        # Calculate verified accuracy: correct important / total important
        important_regions = [r for r in existing_regions if r.get("is_important")]
        if important_regions:
            correct_count = sum(
                1 for r in important_regions
                if r.get("verification_status") == VerificationStatus.VERIFIED.value
            )
            verified_accuracy = correct_count / len(important_regions)
        else:
            verified_accuracy = 0.0

        success = await firestore.update_result_verification_handwritten(
            result_id=result.id,
            ocr_results=ocr_results,
            verified_accuracy=verified_accuracy,
            verified_by=current_user_id,
            verified_by_name=verified_by_name,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update verification",
            )

        return {
            "message": "Verification submitted successfully",
            "verified_accuracy": verified_accuracy,
            "regions_verified": len(request.text_regions),
            "regions_added": len(request.added_regions) if request.added_regions else 0,
        }

    # === Synthetic path: fields provided ===
    updated_fields = []
    for existing_field in result.extracted_fields:
        # Find matching verification request
        verification = None
        for vf in request.fields:
            if vf.field_name == existing_field.field_name:
                verification = vf
                break

        if verification:
            updated_fields.append(ExtractedField(
                field_name=existing_field.field_name,
                expected_value=existing_field.expected_value,
                extracted_value=existing_field.extracted_value,
                confidence=existing_field.confidence,
                match_score=existing_field.match_score,
                is_important=verification.is_important,
                verification_status=verification.verification_status,
                corrected_value=verification.corrected_value,
            ))
        else:
            updated_fields.append(existing_field)

    # Calculate verified accuracy from important fields only
    important_fields = [f for f in updated_fields if f.is_important]
    if not important_fields:
        important_fields = updated_fields  # fallback
    if important_fields:
        correct_count = sum(
            1 for f in important_fields
            if f.verification_status == VerificationStatus.VERIFIED
        )
        verified_accuracy = correct_count / len(important_fields)
    else:
        verified_accuracy = 0.0

    # Update result in Firestore
    success = await firestore.update_result_verification(
        result_id=result.id,
        extracted_fields=updated_fields,
        verified_accuracy=verified_accuracy,
        verified_by=current_user_id,
        verified_by_name=verified_by_name,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update verification",
        )

    return {
        "message": "Verification submitted successfully",
        "verified_accuracy": verified_accuracy,
        "fields_verified": len(request.fields),
    }


@router.get("/{test_run_id}/summary")
async def get_verification_summary(
    test_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Get verification progress summary for a test run."""
    firestore = FirestoreService()

    test_run = await firestore.get_test_run_by_id(test_run_id)
    if not test_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found",
        )

    results = await firestore.get_results_by_test_run(test_run_id)

    total = len(results)
    verified = 0
    corrected = 0
    unverified = 0

    for result in results:
        # Check if handwritten (no extracted fields, has full_text)
        is_handwritten = (
            not result.extracted_fields
            and result.ocr_results
            and result.ocr_results.get("full_text") is not None
        )

        if is_handwritten:
            if result.verified_by:
                text_regions = result.ocr_results.get("text_regions", [])
                has_corrections = any(
                    r.get("verification_status") == VerificationStatus.CORRECTED.value
                    for r in text_regions
                )
                has_added = any(r.get("user_added") for r in text_regions)
                if has_corrections or has_added:
                    corrected += 1
                else:
                    verified += 1
            else:
                unverified += 1
            continue

        if not result.extracted_fields:
            if result.verified_by:
                verified += 1
            else:
                unverified += 1
            continue

        all_done = all(
            ef.verification_status != VerificationStatus.UNVERIFIED
            for ef in result.extracted_fields
        )
        if all_done:
            has_corrections = any(
                ef.verification_status == VerificationStatus.CORRECTED
                for ef in result.extracted_fields
            )
            if has_corrections:
                corrected += 1
            else:
                verified += 1
        else:
            unverified += 1

    return {
        "test_run_id": test_run_id,
        "total": total,
        "verified": verified,
        "corrected": corrected,
        "unverified": unverified,
        "progress_percent": (
            ((verified + corrected) / total * 100) if total > 0 else 0
        ),
    }
