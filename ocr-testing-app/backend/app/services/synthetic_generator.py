"""
Synthetic data generator service.
Generates filled forms by overlaying text on base form templates.
Supports both image (PNG/JPEG) and PDF templates via PyMuPDF.
"""
import io
import uuid
import random
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont

from app.models.form import FormInDB, FieldMapping, FieldType
from app.models.batch import SyntheticDocument
from app.services.storage import StorageService

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Field-type-based synthetic data pools
FIELD_TYPE_DATA = {
    "numeric_short": [
        "123", "456", "789", "012", "345", "678", "901", "234",
        "5678", "9012", "1234", "4567", "8901", "42", "307", "88",
    ],
    "text_short": [
        "TX", "CA", "NY", "FL", "IL", "PA", "OH", "GA",
        "Civil", "Criminal", "Family", "Probate", "Juvenile",
        "Plaintiff", "Defendant", "Appellant", "Respondent",
        "Dallas", "Harris", "Travis", "Bexar", "Tarrant", "El Paso",
    ],
    "sentence": [
        "The defendant failed to appear at the scheduled hearing.",
        "Plaintiff requests summary judgment on all counts.",
        "Motion to dismiss is hereby granted.",
        "The court finds sufficient evidence to proceed.",
        "All parties have been duly notified of the hearing date.",
        "Defendant is ordered to pay restitution to the plaintiff.",
        "The case is hereby continued to the next available date.",
        "Witness testimony corroborates the plaintiff's claims.",
    ],
    "full_name": [
        "John Smith", "Jane Doe", "Robert Johnson", "Maria Garcia",
        "Michael Brown", "Emily Davis", "David Wilson", "Sarah Miller",
        "James Taylor", "Jennifer Anderson", "William Thomas", "Linda Martinez",
        "Charles Jordan", "Patricia Williams", "Daniel Lee", "Angela Robinson",
        "Christopher Harris", "Amanda Clark", "Matthew Wright", "Stephanie King",
    ],
    "day_month": [
        "January 15", "February 20", "March 10", "April 5",
        "May 25", "June 30", "July 4", "August 15",
        "September 1", "October 12", "November 28", "December 25",
        "January 3", "March 22", "June 17", "September 30",
    ],
    "2_digit_year": [
        "20", "21", "22", "23", "24", "25", "26",
    ],
    "4_digit_year": [
        "2020", "2021", "2022", "2023", "2024", "2025", "2026",
    ],
}

# Legacy name-based fallback for backward compatibility
DEFAULT_SYNTHETIC_DATA = {
    "defendant_name": FIELD_TYPE_DATA["full_name"],
    "plaintiff_name": [
        "ABC Corporation", "XYZ Inc.", "State of Texas", "City of Dallas",
        "First National Bank", "Johnson & Associates", "Smith Holdings LLC",
    ],
    "case_number": [
        "2024-CV-001234", "2024-CV-005678", "2023-CV-009012", "2024-CR-003456",
        "DC-2024-0001", "DC-2024-0042", "CC-2024-1234", "JP-2024-5678",
    ],
    "date": [
        "January 15, 2024", "February 20, 2024", "March 10, 2024",
        "April 5, 2024", "May 25, 2024", "June 30, 2024",
    ],
    "default": FIELD_TYPE_DATA["text_short"],
}


class SyntheticGeneratorService:
    """Service for generating synthetic filled forms."""

    def __init__(self):
        self.storage = StorageService()
        self.render_scale = 2  # Match notebook RENDER_SCALE

    def _pdf_to_image(self, pdf_bytes: bytes, page_num: int = 0) -> Image.Image:
        """Convert a PDF page to a PIL Image using PyMuPDF."""
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("PyMuPDF not installed. Install with: pip install pymupdf")
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_doc[page_num]
        mat = fitz.Matrix(self.render_scale, self.render_scale)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pdf_doc.close()
        return img

    def _is_pdf(self, data: bytes) -> bool:
        """Check if bytes represent a PDF file."""
        return data[:5] == b'%PDF-'

    def _get_font(self, size: int = 12) -> ImageFont.FreeTypeFont:
        """Get a font for text rendering."""
        try:
            # Try to load a common font
            return ImageFont.truetype("arial.ttf", size)
        except (OSError, IOError):
            try:
                # Try another common font
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except (OSError, IOError):
                # Fall back to default font
                return ImageFont.load_default()

    def _get_synthetic_value(
        self,
        field_name: str,
        custom_options: Optional[List[str]] = None,
        field_type: Optional[str] = None
    ) -> str:
        """Get a synthetic value for a field based on its type."""
        if custom_options:
            return random.choice(custom_options)

        # Use field_type if provided (new behavior)
        if field_type and field_type in FIELD_TYPE_DATA:
            return random.choice(FIELD_TYPE_DATA[field_type])

        # Legacy fallback: try to match field name to default data
        field_lower = field_name.lower()
        for key, values in DEFAULT_SYNTHETIC_DATA.items():
            if key in field_lower:
                return random.choice(values)

        # Default fallback
        return random.choice(DEFAULT_SYNTHETIC_DATA["default"])

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    async def generate_filled_form(
        self,
        base_image_bytes: bytes,
        field_mappings: List[FieldMapping],
        field_value_options: Optional[Dict[str, List[str]]] = None
    ) -> tuple[bytes, Dict[str, str]]:
        """
        Generate a single filled form.
        Supports both image (PNG/JPEG) and multi-page PDF templates.

        Args:
            base_image_bytes: The base form image or PDF as bytes
            field_mappings: List of field mappings with coordinates
            field_value_options: Optional custom values for each field

        Returns:
            Tuple of (filled_image_bytes, field_values_dict)
        """
        field_values = {}

        # Generate all field values first
        for field in field_mappings:
            custom_options = None
            if field_value_options and field.name in field_value_options:
                custom_options = field_value_options[field.name]
            value = self._get_synthetic_value(
                field.name, custom_options, field_type=field.field_type.value
            )
            field_values[field.name] = value

        is_pdf = self._is_pdf(base_image_bytes)

        if is_pdf and PYMUPDF_AVAILABLE:
            # Multi-page PDF: render fields grouped by page
            pdf_doc = fitz.open(stream=base_image_bytes, filetype="pdf")
            page_count = len(pdf_doc)
            pdf_doc.close()

            # Group fields by page
            fields_by_page = {}
            for field in field_mappings:
                pg = field.page if field.page < page_count else 0
                fields_by_page.setdefault(pg, []).append(field)

            page_images = []
            for page_idx in range(page_count):
                image = self._pdf_to_image(base_image_bytes, page_num=page_idx)
                page_fields = fields_by_page.get(page_idx, [])
                if page_fields:
                    draw = ImageDraw.Draw(image)
                    for field in page_fields:
                        font = self._get_font(field.font_size)
                        color = self._hex_to_rgb(field.font_color)
                        draw.text(
                            (field.x, field.y),
                            field_values[field.name],
                            font=font,
                            fill=color,
                        )
                page_images.append(image)

            # If single page, save as PNG; if multi-page, save as multi-page PDF
            if len(page_images) == 1:
                output = io.BytesIO()
                page_images[0].save(output, format="PNG")
                output.seek(0)
                return output.getvalue(), field_values
            else:
                # Save as PNG of first page (OCR pipeline handles multi-page via PDF)
                # Re-assemble into a multi-page PDF
                pdf_out = fitz.open()
                for img in page_images:
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format="PNG")
                    img_bytes.seek(0)
                    img_pdf = fitz.open(stream=img_bytes.getvalue(), filetype="png")
                    pdf_out.insert_pdf(img_pdf)
                    img_pdf.close()
                pdf_bytes = pdf_out.tobytes()
                pdf_out.close()
                return pdf_bytes, field_values
        else:
            # Single image
            image = Image.open(io.BytesIO(base_image_bytes)).convert("RGB")
            draw = ImageDraw.Draw(image)

            for field in field_mappings:
                font = self._get_font(field.font_size)
                color = self._hex_to_rgb(field.font_color)
                draw.text(
                    (field.x, field.y),
                    field_values[field.name],
                    font=font,
                    fill=color,
                )

            output = io.BytesIO()
            image.save(output, format="PNG")
            output.seek(0)
            return output.getvalue(), field_values

    async def generate_batch(
        self,
        form: FormInDB,
        count: int,
        field_value_options: Optional[Dict[str, List[str]]] = None,
        skew_preset: Optional[str] = None
    ) -> List[SyntheticDocument]:
        """
        Generate a batch of synthetic filled forms.

        Args:
            form: The base form template
            count: Number of documents to generate
            field_value_options: Optional custom values for each field
            skew_preset: Optional scan simulation preset ("light", "medium", "heavy")

        Returns:
            List of SyntheticDocument objects
        """
        # Download base form image
        base_image_bytes = await self.storage.download_file(form.storage_path)

        # Lazy-import scan simulator only when needed
        simulator = None
        if skew_preset:
            from app.services.scan_simulator import ScanSimulatorService
            simulator = ScanSimulatorService()

        documents = []
        batch_id = str(uuid.uuid4())

        # Detect if base form is a multi-page PDF
        is_multipage_pdf = (
            self._is_pdf(base_image_bytes)
            and PYMUPDF_AVAILABLE
            and fitz.open(stream=base_image_bytes, filetype="pdf").page_count > 1
        )

        for i in range(count):
            doc_id = str(uuid.uuid4())

            # Generate filled form
            filled_image_bytes, field_values = await self.generate_filled_form(
                base_image_bytes=base_image_bytes,
                field_mappings=form.field_mappings,
                field_value_options=field_value_options
            )

            # Apply scan simulation if skew preset is provided
            if simulator:
                filled_image_bytes = simulator.generate_skewed_copy(
                    filled_image_bytes, preset=skew_preset
                )

            # Upload to storage (use .pdf extension for multi-page documents)
            ext = "pdf" if is_multipage_pdf else "png"
            storage_path = await self.storage.upload_bytes(
                data=filled_image_bytes,
                blob_name=f"batches/{batch_id}/{doc_id}.{ext}"
            )

            documents.append(SyntheticDocument(
                id=doc_id,
                storage_path=storage_path,
                field_values=field_values,
                is_skewed=bool(skew_preset),
            ))

        return documents, batch_id
