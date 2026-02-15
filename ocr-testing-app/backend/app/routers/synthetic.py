"""
Synthetic data generation routes.
"""
import uuid
from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import Response

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from app.auth.dependencies import get_current_user_id
from app.models.batch import (
    BatchResponse,
    BatchListResponse,
    GenerateBatchRequest,
    MergeBatchesRequest,
    AppendDocumentsRequest,
    RemoveDocumentsRequest,
    SyntheticDocument,
)
from app.services.firestore import FirestoreService
from app.services.synthetic_generator import SyntheticGeneratorService
from app.services.scan_simulator import ScanSimulatorService
from app.services.storage import StorageService

router = APIRouter()


@router.post("/generate", response_model=BatchResponse)
async def generate_batch(
    request: GenerateBatchRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Generate a batch of synthetic filled forms or skewed copies."""
    firestore = FirestoreService()

    # Get the base form
    form = await firestore.get_form_by_id(request.form_id)
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    # Validate count
    if request.count < 1 or request.count > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Count must be between 1 and 100"
        )

    # Look up creator name
    user = await firestore.get_user_by_id(current_user_id)
    created_by_name = user.email if user else ""

    # Branch based on form type
    if form.form_type == "handwritten":
        # Handwritten form: generate skewed copies (no field mapping needed)
        storage = StorageService()
        simulator = ScanSimulatorService()

        # Download original form
        base_image_bytes = await storage.download_file(form.storage_path)

        # Convert PDF pages to individual PNG images
        page_images_bytes = []
        if form.storage_path.lower().endswith('.pdf'):
            if not PYMUPDF_AVAILABLE:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="PyMuPDF is required to process PDF forms"
                )
            pdf_doc = fitz.open(stream=base_image_bytes, filetype="pdf")
            for page_idx in range(len(pdf_doc)):
                page = pdf_doc[page_idx]
                mat = fitz.Matrix(2, 2)  # 2x scale for quality
                pix = page.get_pixmap(matrix=mat)
                page_images_bytes.append(pix.tobytes("png"))
            pdf_doc.close()
        else:
            page_images_bytes = [base_image_bytes]

        preset = request.skew_preset or "medium"
        batch_uuid = str(uuid.uuid4())
        documents = []
        is_multipage = len(page_images_bytes) > 1

        for i in range(request.count):
            doc_id = str(uuid.uuid4())

            if is_multipage:
                # Multi-page: skew each page, reassemble into PDF
                skewed_pages = []
                for pg_bytes in page_images_bytes:
                    skewed_pg = simulator.generate_skewed_copy(pg_bytes, preset=preset)
                    skewed_pages.append(skewed_pg)

                # Reassemble into multi-page PDF
                pdf_out = fitz.open()
                for sp_bytes in skewed_pages:
                    img_pdf = fitz.open(stream=sp_bytes, filetype="png")
                    pdf_out.insert_pdf(img_pdf)
                    img_pdf.close()
                final_bytes = pdf_out.tobytes()
                pdf_out.close()
                ext = "pdf"
            else:
                # Single page: skew directly
                final_bytes = simulator.generate_skewed_copy(
                    page_images_bytes[0], preset=preset
                )
                ext = "png"

            # Upload to storage
            storage_path = await storage.upload_bytes(
                data=final_bytes,
                blob_name=f"batches/{batch_uuid}/{doc_id}.{ext}"
            )

            documents.append(SyntheticDocument(
                id=doc_id,
                storage_path=storage_path,
                field_values={},
                is_skewed=True,
            ))

        # Create batch record
        batch = await firestore.create_batch(
            form_id=form.id,
            form_name=form.name,
            created_by=current_user_id,
            count=request.count,
            documents=documents,
            batch_type="handwritten",
            created_by_name=created_by_name,
            skew_preset=preset,
        )

        return BatchResponse(**batch.model_dump())
    else:
        # Empty form: existing synthetic generation flow
        if not form.field_mappings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Form has no field mappings defined. Please define field mappings first."
            )

        generator = SyntheticGeneratorService()
        documents, batch_uuid = await generator.generate_batch(
            form=form,
            count=request.count,
            field_value_options=request.field_value_options,
            skew_preset=request.skew_preset,
        )

        # Create batch record
        batch = await firestore.create_batch(
            form_id=form.id,
            form_name=form.name,
            created_by=current_user_id,
            count=request.count,
            documents=documents,
            batch_type="synthetic",
            created_by_name=created_by_name,
            skew_preset=request.skew_preset,
        )

        return BatchResponse(**batch.model_dump())


@router.get("/batches", response_model=BatchListResponse)
async def list_batches(current_user_id: str = Depends(get_current_user_id)):
    """List all synthetic data batches."""
    firestore = FirestoreService()
    batches = await firestore.list_batches()

    return BatchListResponse(
        batches=[BatchResponse(**b.model_dump()) for b in batches],
        total=len(batches)
    )


@router.post("/batches/merge", response_model=BatchResponse)
async def merge_batches(
    request: MergeBatchesRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Merge multiple batches into a new batch (copies all documents)."""
    if len(request.source_batch_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 source batches are required for merge",
        )

    firestore = FirestoreService()
    storage = StorageService()

    # Load all source batches and validate
    source_batches = []
    for batch_id in request.source_batch_ids:
        batch = await firestore.get_batch_by_id(batch_id)
        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch {batch_id} not found",
            )
        source_batches.append(batch)

    # Verify all share the same form_id
    form_ids = {b.form_id for b in source_batches}
    if len(form_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All source batches must belong to the same form",
        )

    # Determine batch type
    batch_types = {b.batch_type for b in source_batches}
    if len(batch_types) == 1:
        merged_type = batch_types.pop()
    else:
        merged_type = "mixed"

    # Copy all documents to new batch
    new_batch_id = str(uuid.uuid4())
    new_documents = []

    for batch in source_batches:
        for doc in batch.documents:
            new_doc_id = str(uuid.uuid4())
            dest_blob = f"batches/{new_batch_id}/{new_doc_id}.png"
            await storage.copy_file(doc.storage_path, dest_blob)
            new_documents.append(SyntheticDocument(
                id=new_doc_id,
                storage_path=storage._get_gs_path(dest_blob),
                field_values=doc.field_values,
                is_skewed=doc.is_skewed,
            ))

    # Look up creator name
    user = await firestore.get_user_by_id(current_user_id)
    created_by_name = user.email if user else ""

    # Create the merged batch
    merged_batch = await firestore.create_batch(
        form_id=source_batches[0].form_id,
        form_name=source_batches[0].form_name,
        created_by=current_user_id,
        count=len(new_documents),
        documents=new_documents,
        batch_type=merged_type,
        created_by_name=created_by_name,
        source_batch_ids=request.source_batch_ids,
    )

    return BatchResponse(**merged_batch.model_dump())


@router.post("/batches/{batch_id}/remove-documents", response_model=BatchResponse)
async def remove_documents(
    batch_id: str,
    request: RemoveDocumentsRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Remove specific documents from a batch."""
    firestore = FirestoreService()
    storage = StorageService()

    batch = await firestore.get_batch_by_id(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found",
        )

    # Delete GCS files for the removed documents
    for doc in batch.documents:
        if doc.id in request.document_ids:
            await storage.delete_file(doc.storage_path)

    # Update Firestore
    updated_batch = await firestore.remove_documents_from_batch(
        batch_id, request.document_ids
    )
    if not updated_batch:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove documents",
        )

    return BatchResponse(**updated_batch.model_dump())


@router.post("/batches/{batch_id}/append", response_model=BatchResponse)
async def append_documents(
    batch_id: str,
    request: AppendDocumentsRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """Copy documents from a source batch and append them to this batch."""
    firestore = FirestoreService()
    storage = StorageService()

    # Load target and source batches
    target_batch = await firestore.get_batch_by_id(batch_id)
    if not target_batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target batch not found",
        )

    source_batch = await firestore.get_batch_by_id(request.source_batch_id)
    if not source_batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source batch not found",
        )

    # Validate same form
    if target_batch.form_id != source_batch.form_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and target batches must belong to the same form",
        )

    # Find and copy the requested documents
    source_doc_map = {doc.id: doc for doc in source_batch.documents}
    new_documents = []

    for doc_id in request.document_ids:
        source_doc = source_doc_map.get(doc_id)
        if not source_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {doc_id} not found in source batch",
            )

        new_doc_id = str(uuid.uuid4())
        dest_blob = f"batches/{batch_id}/{new_doc_id}.png"
        await storage.copy_file(source_doc.storage_path, dest_blob)
        new_documents.append(SyntheticDocument(
            id=new_doc_id,
            storage_path=storage._get_gs_path(dest_blob),
            field_values=source_doc.field_values,
            is_skewed=source_doc.is_skewed,
        ))

    # Append to target batch
    updated_batch = await firestore.append_documents_to_batch(
        batch_id, new_documents
    )
    if not updated_batch:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to append documents",
        )

    return BatchResponse(**updated_batch.model_dump())


@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """Delete a batch and all its documents from storage."""
    firestore = FirestoreService()
    storage = StorageService()

    batch = await firestore.get_batch_by_id(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found",
        )

    # Delete all document files from GCS
    for doc in batch.documents:
        await storage.delete_file(doc.storage_path)

    # Delete batch from Firestore
    success = await firestore.delete_batch(batch_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete batch",
        )

    return {"message": "Batch deleted", "batch_id": batch_id}


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get batch details by ID."""
    firestore = FirestoreService()
    batch = await firestore.get_batch_by_id(batch_id)

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )

    return BatchResponse(**batch.model_dump())


@router.get("/batches/{batch_id}/documents/{document_id}/image")
async def get_document_image(
    batch_id: str,
    document_id: str,
    page: int = Query(0, ge=0, description="Page number (0-indexed) for multi-page documents"),
    current_user_id: str = Depends(get_current_user_id)
):
    """Proxy the document image bytes (avoids signed URL issues on Cloud Run).
    For multi-page PDF documents, converts the requested page to PNG."""
    firestore = FirestoreService()
    batch = await firestore.get_batch_by_id(batch_id)

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )

    # Find the document
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

    storage = StorageService()
    file_bytes = await storage.download_file(document.storage_path)

    # If it's a PDF, convert the requested page to PNG
    if document.storage_path.lower().endswith('.pdf') and PYMUPDF_AVAILABLE:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
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

    return Response(content=file_bytes, media_type="image/png")
