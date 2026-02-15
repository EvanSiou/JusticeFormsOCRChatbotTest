"""
Forms management routes.
Supports both image (PNG/JPEG) and PDF form templates.
"""
import io
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form, Query
from fastapi.responses import Response
from typing import List

from app.auth.dependencies import get_current_user_id
from app.models.form import (
    FormResponse,
    FormListResponse,
    UpdateFieldMappingsRequest,
    UpdateFieldMappingsWithConfigRequest,
    UpdateTemplateWordsRequest,
    FieldMapping,
)
from app.services.firestore import FirestoreService
from app.services.storage import StorageService

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

router = APIRouter()


@router.get("", response_model=FormListResponse)
async def list_forms(current_user_id: str = Depends(get_current_user_id)):
    """List all form templates."""
    firestore = FirestoreService()
    forms = await firestore.list_forms()

    return FormListResponse(
        forms=[FormResponse(**f.model_dump()) for f in forms],
        total=len(forms)
    )


@router.post("", response_model=FormResponse)
async def upload_form(
    file: UploadFile = File(...),
    name: str = Form(...),
    form_type: str = Form("empty"),
    current_user_id: str = Depends(get_current_user_id)
):
    """Upload a new form template."""
    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {allowed_types}"
        )

    # Validate form_type
    if form_type not in ("empty", "handwritten"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="form_type must be 'empty' or 'handwritten'"
        )

    # Upload to storage
    storage = StorageService()
    storage_path = await storage.upload_form(
        file=file.file,
        filename=file.filename,
        content_type=file.content_type
    )

    # Detect page count for PDF forms
    page_count = 1
    if file.content_type == "application/pdf" and PYMUPDF_AVAILABLE:
        file.file.seek(0)
        pdf_bytes = file.file.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(pdf_doc)
        pdf_doc.close()

    # Create form record in Firestore
    firestore = FirestoreService()
    user = await firestore.get_user_by_id(current_user_id)
    uploaded_by_name = user.email if user else ""

    form = await firestore.create_form(
        name=name,
        storage_path=storage_path,
        uploaded_by=current_user_id,
        form_type=form_type,
        uploaded_by_name=uploaded_by_name,
        page_count=page_count,
    )

    return FormResponse(**form.model_dump())


@router.get("/{form_id}", response_model=FormResponse)
async def get_form(
    form_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get form details by ID."""
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    return FormResponse(**form.model_dump())


@router.get("/{form_id}/image")
async def get_form_image(
    form_id: str,
    page: int = Query(0, ge=0, description="Page number (0-indexed) for PDF forms"),
    current_user_id: str = Depends(get_current_user_id)
):
    """Get a form page as an image.
    For PDF templates, converts the specified page to PNG and returns it directly.
    """
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    # Check if this is a PDF - if so, convert to image
    if form.storage_path.lower().endswith('.pdf') and PYMUPDF_AVAILABLE:
        storage = StorageService()
        pdf_bytes = await storage.download_file(form.storage_path)
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if page >= len(pdf_doc):
            pdf_doc.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Page {page} out of range (0-{len(pdf_doc)-1})"
            )
        page_obj = pdf_doc[page]
        mat = fitz.Matrix(2, 2)  # 2x scale
        pix = page_obj.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        pdf_doc.close()
        return Response(content=png_bytes, media_type="image/png")

    storage = StorageService()
    signed_url = await storage.get_signed_url(form.storage_path)
    return {"url": signed_url}


@router.get("/{form_id}/download")
async def download_form(
    form_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Download the original form file."""
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    storage = StorageService()
    file_bytes = await storage.download_file(form.storage_path)

    # Determine content type and filename from storage path
    path_lower = form.storage_path.lower()
    if path_lower.endswith('.pdf'):
        media_type = "application/pdf"
        ext = ".pdf"
    elif path_lower.endswith('.png'):
        media_type = "image/png"
        ext = ".png"
    else:
        media_type = "image/jpeg"
        ext = ".jpg"

    filename = f"{form.name}{ext}"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{form_id}/config")
async def export_field_config(
    form_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Export field config as JSON (compatible with notebook field_configs format)."""
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    config = {
        "template": form.name,
        "render_scale": 2,
        "fields": [
            {
                "name": f.name,
                "x": f.x,
                "y": f.y,
                "width": f.width,
                "height": f.height,
                "font_size": f.font_size,
                "font_color": f.font_color,
            }
            for f in form.field_mappings
        ]
    }
    return config


@router.put("/{form_id}/config")
async def import_field_config(
    form_id: str,
    request: UpdateFieldMappingsWithConfigRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Import field config from notebook JSON format."""
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    # Convert notebook config to FieldMapping objects
    field_mappings = [
        FieldMapping(
            name=f.get("name", f"field_{i+1}"),
            x=f["x"],
            y=f["y"],
            width=f.get("width", 200),
            height=f.get("height", 30),
            font_size=f.get("font_size", 12),
            font_color=f.get("font_color", "#000000"),
        )
        for i, f in enumerate(request.fields)
    ]

    success = await firestore.update_form_field_mappings(
        form_id=form_id,
        field_mappings=field_mappings
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import field config"
        )

    updated_form = await firestore.get_form_by_id(form_id)
    return FormResponse(**updated_form.model_dump())


@router.put("/{form_id}/fields", response_model=FormResponse)
async def update_field_mappings(
    form_id: str,
    request: UpdateFieldMappingsRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Update field mappings for a form."""
    firestore = FirestoreService()

    # Check if form exists
    form = await firestore.get_form_by_id(form_id)
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    # Update field mappings
    success = await firestore.update_form_field_mappings(
        form_id=form_id,
        field_mappings=request.field_mappings
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update field mappings"
        )

    # Return updated form
    updated_form = await firestore.get_form_by_id(form_id)
    return FormResponse(**updated_form.model_dump())


@router.get("/{form_id}/template-words")
async def get_template_words(
    form_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Get template words for a form (used for text cleanup)."""
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    return {"template_words": form.template_words or []}


@router.put("/{form_id}/template-words")
async def update_template_words(
    form_id: str,
    request: UpdateTemplateWordsRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """Update template words for a form (used for text cleanup)."""
    firestore = FirestoreService()
    form = await firestore.get_form_by_id(form_id)

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    success = await firestore.update_form_template_words(
        form_id=form_id,
        template_words=request.template_words
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update template words"
        )

    return {"template_words": request.template_words}


@router.delete("/{form_id}")
async def delete_form(
    form_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """Delete a form template."""
    firestore = FirestoreService()

    # Get form to get storage path
    form = await firestore.get_form_by_id(form_id)
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found"
        )

    # Delete from storage
    storage = StorageService()
    await storage.delete_file(form.storage_path)

    # Delete from Firestore
    success = await firestore.delete_form(form_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete form"
        )

    return {"message": "Form deleted successfully"}
