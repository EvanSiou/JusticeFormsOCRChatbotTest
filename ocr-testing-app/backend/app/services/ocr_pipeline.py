"""
OCR Pipeline service.
Orchestrates layout detection and OCR extraction.
"""
import io
import logging
from typing import List, Dict, Any, Optional
from PIL import Image
from difflib import SequenceMatcher

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

logger = logging.getLogger(__name__)

from app.models.batch import BatchInDB, SyntheticDocument
from app.models.result import ExtractedField
from app.services.storage import StorageService
from app.services.firestore import FirestoreService
from app.processing.layout import get_layout_detector, list_layout_detectors
from app.processing.ocr import get_ocr_engine, list_ocr_engines, VLM_ENGINES


class OCRPipelineService:
    """Service for running the OCR pipeline on documents."""

    def __init__(self):
        self.storage = StorageService()
        self.firestore = FirestoreService()

    @staticmethod
    def _is_pdf(data: bytes) -> bool:
        """Check if bytes represent a PDF file."""
        return data[:5] == b'%PDF-'

    @staticmethod
    def _pdf_bytes_to_images(pdf_bytes: bytes, pages: Optional[List[int]] = None) -> List[Image.Image]:
        """Convert PDF bytes to a list of PIL images, one per page."""
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("PyMuPDF not installed. Install with: pip install pymupdf")
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        page_indices = pages if pages else range(len(pdf_doc))
        for i in page_indices:
            if i >= len(pdf_doc):
                continue
            page = pdf_doc[i]
            mat = fitz.Matrix(2, 2)  # 2x scale for quality
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        pdf_doc.close()
        return images

    async def process_document(
        self,
        document: SyntheticDocument,
        layout_library: str,
        ocr_library: str,
        image_cache: Optional[Dict[str, bytes]] = None,
        template_words: Optional[List[str]] = None,
        ocr_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a single document through the pipeline.

        Args:
            document: The synthetic document to process
            layout_library: Name of layout detector to use
            ocr_library: Name of OCR engine to use

        Returns:
            Dictionary with layout_results, ocr_results, extracted_fields, accuracy
        """
        # Download document image (use cache if provided)
        if image_cache is not None and document.storage_path in image_cache:
            image_bytes = image_cache[document.storage_path]
        else:
            image_bytes = await self.storage.download_file(document.storage_path)
            if image_cache is not None:
                image_cache[document.storage_path] = image_bytes

        # Handle multi-page PDFs: process each page separately
        if self._is_pdf(image_bytes) and PYMUPDF_AVAILABLE:
            page_images = self._pdf_bytes_to_images(image_bytes)
            logger.info(f"Processing {len(page_images)} PDF pages with layout={layout_library}, ocr={ocr_library}")
        else:
            page_images = [Image.open(io.BytesIO(image_bytes)).convert("RGB")]

        # Get layout detector and OCR engine
        layout_detector = get_layout_detector(layout_library)
        ocr_engine = get_ocr_engine(ocr_library)
        from app.processing.layout.base import Region

        all_ocr_results = []
        all_layout_regions = []
        all_full_text_parts = []

        for page_idx, image in enumerate(page_images):
            cache_key = f"{document.storage_path}__page{page_idx}" if len(page_images) > 1 else document.storage_path

            # Check layout cache first
            cached_layout = await self.firestore.get_cached_layout(
                cache_key, layout_library
            )
            if cached_layout is not None:
                regions = [
                    Region(
                        id=r["id"],
                        type=r["type"],
                        confidence=r["confidence"],
                        bbox=r["bbox"],
                    )
                    for r in cached_layout.get("regions", [])
                ]
            else:
                regions = layout_detector.detect(image)
                layout_dict = layout_detector.to_dict(regions)
                await self.firestore.set_cached_layout(
                    cache_key, layout_library, layout_dict
                )

            all_layout_regions.extend(regions)

            # Run OCR on detected regions
            page_ocr_results = ocr_engine.extract_text(image, regions, prompt=ocr_prompt)
            all_ocr_results.extend(page_ocr_results)

            page_text = " ".join([r.full_text for r in page_ocr_results])
            if len(page_images) > 1:
                all_full_text_parts.append(f"--- Page {page_idx + 1} ---\n{page_text}")
            else:
                all_full_text_parts.append(page_text)

        layout_results = layout_detector.to_dict(all_layout_regions)
        ocr_results = ocr_engine.to_dict(all_ocr_results)

        # Add full_text and text_regions (needed by verify page for handwritten docs)
        full_text = "\n\n".join(all_full_text_parts)
        ocr_results["full_text"] = full_text
        text_regions = []
        for r in all_ocr_results:
            for line in r.lines:
                text_regions.append({
                    "text": line.text,
                    "confidence": line.confidence,
                })
        ocr_results["text_regions"] = text_regions

        # Text cleanup: remove template words before field matching
        match_results_list = all_ocr_results
        if template_words:
            from app.processing.text_cleanup import TemplateTextCleaner
            cleaner = TemplateTextCleaner(template_words)
            match_results_list = TemplateTextCleaner.clean_ocr_results(
                all_ocr_results, template_words
            )
            cleaned_text = cleaner.clean(full_text)
            ocr_results["cleaned_text"] = cleaned_text

        # Extract and match fields
        extracted_fields = self._match_fields(
            document.field_values,
            match_results_list
        )

        # Calculate overall accuracy
        overall_accuracy = self._calculate_accuracy(extracted_fields)

        return {
            "layout_results": layout_results,
            "ocr_results": ocr_results,
            "extracted_fields": extracted_fields,
            "overall_accuracy": overall_accuracy,
        }

    def _match_fields(
        self,
        expected_values: Dict[str, str],
        ocr_results: List
    ) -> List[ExtractedField]:
        """
        Match OCR results to expected field values.

        Uses fuzzy string matching to find the best match for each expected field.
        """
        extracted_fields = []

        # Combine all OCR text
        all_text = " ".join([r.full_text for r in ocr_results])

        for field_name, expected_value in expected_values.items():
            # Find the best match in OCR text
            best_match = ""
            best_score = 0.0
            best_confidence = 0.0

            # Search in each OCR result
            for ocr_result in ocr_results:
                for line in ocr_result.lines:
                    # Calculate similarity
                    score = SequenceMatcher(
                        None,
                        expected_value.lower(),
                        line.text.lower()
                    ).ratio()

                    if score > best_score:
                        best_score = score
                        best_match = line.text
                        best_confidence = line.confidence

                # Also check full text
                score = SequenceMatcher(
                    None,
                    expected_value.lower(),
                    ocr_result.full_text.lower()
                ).ratio()

                if score > best_score:
                    best_score = score
                    best_match = ocr_result.full_text
                    best_confidence = sum(
                        [l.confidence for l in ocr_result.lines]
                    ) / max(len(ocr_result.lines), 1)

            extracted_fields.append(ExtractedField(
                field_name=field_name,
                expected_value=expected_value,
                extracted_value=best_match,
                confidence=best_confidence,
                match_score=best_score,
                is_important=True,
            ))

        return extracted_fields

    def _calculate_accuracy(self, extracted_fields: List[ExtractedField]) -> float:
        """Calculate overall accuracy from important extracted fields."""
        if not extracted_fields:
            return 0.0

        important = [f for f in extracted_fields if f.is_important]
        if not important:
            important = extracted_fields  # fallback for legacy data
        total_score = sum(f.match_score for f in important)
        return total_score / len(important)

    async def process_document_full_text(
        self,
        document: SyntheticDocument,
        ocr_library: str,
        match_fields: bool = False,
        image_cache: Optional[Dict[str, bytes]] = None,
        template_words: Optional[List[str]] = None,
        ocr_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a document with full-text OCR (no layout detection).
        Used for handwritten forms and VLM engines that process the full page.

        Args:
            document: The document to process
            ocr_library: Name of OCR engine to use
            match_fields: Whether to match OCR results against expected field values
            image_cache: Optional shared image cache dict

        Returns:
            Dictionary with ocr_results (including full_text and regions)
        """
        # Download document image (use cache if provided)
        if image_cache is not None and document.storage_path in image_cache:
            image_bytes = image_cache[document.storage_path]
        else:
            image_bytes = await self.storage.download_file(document.storage_path)
            if image_cache is not None:
                image_cache[document.storage_path] = image_bytes

        # Get OCR engine
        ocr_engine = get_ocr_engine(ocr_library)
        from app.processing.layout.base import Region

        # Handle multi-page PDFs: process each page separately
        if self._is_pdf(image_bytes) and PYMUPDF_AVAILABLE:
            page_images = self._pdf_bytes_to_images(image_bytes)
            logger.info(f"Processing {len(page_images)} PDF pages with {ocr_library}")
        else:
            page_images = [Image.open(io.BytesIO(image_bytes)).convert("RGB")]

        all_ocr_results = []
        all_full_text_parts = []

        for page_idx, image in enumerate(page_images):
            full_region = Region(
                id=page_idx,
                type="full_page",
                confidence=1.0,
                bbox={"x1": 0, "y1": 0, "x2": image.width, "y2": image.height},
            )

            page_results = ocr_engine.extract_text(image, [full_region], prompt=ocr_prompt)
            all_ocr_results.extend(page_results)

            page_text = " ".join([r.full_text for r in page_results])
            if len(page_images) > 1:
                all_full_text_parts.append(f"--- Page {page_idx + 1} ---\n{page_text}")
            else:
                all_full_text_parts.append(page_text)

        ocr_results = ocr_engine.to_dict(all_ocr_results)

        # Combine all text
        full_text = "\n\n".join(all_full_text_parts)
        ocr_results["full_text"] = full_text

        # Collect individual text regions
        regions = []
        for r in all_ocr_results:
            for line in r.lines:
                regions.append({
                    "text": line.text,
                    "confidence": line.confidence,
                })
        ocr_results["text_regions"] = regions

        # Text cleanup: remove template words before field matching
        match_results_list = all_ocr_results
        if template_words:
            from app.processing.text_cleanup import TemplateTextCleaner
            cleaner = TemplateTextCleaner(template_words)
            match_results_list = TemplateTextCleaner.clean_ocr_results(
                all_ocr_results, template_words
            )
            cleaned_text = cleaner.clean(full_text)
            ocr_results["cleaned_text"] = cleaned_text

        # Match fields if requested and document has expected values
        extracted_fields = []
        overall_accuracy = 0.0
        if match_fields and document.field_values:
            extracted_fields = self._match_fields(
                document.field_values,
                match_results_list
            )
            overall_accuracy = self._calculate_accuracy(extracted_fields)

        return {
            "layout_results": {"regions": [], "method": "none (full-page OCR)"},
            "ocr_results": ocr_results,
            "extracted_fields": extracted_fields,
            "overall_accuracy": overall_accuracy,
        }

    async def process_batch(
        self,
        batch: BatchInDB,
        layout_library: str,
        ocr_library: str,
        test_run_id: str,
        progress_callback: Optional[callable] = None,
        image_cache: Optional[Dict[str, bytes]] = None,
        ocr_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Process all documents in a batch.

        Args:
            batch: The batch to process
            layout_library: Name of layout detector to use
            ocr_library: Name of OCR engine to use
            test_run_id: ID of the test run
            progress_callback: Optional callback for progress updates
            image_cache: Optional shared image cache dict (for batch combo jobs)

        Returns:
            List of results for each document
        """
        results = []

        # Look up form template words for text cleanup
        template_words = None
        if batch.form_id:
            form = await self.firestore.get_form_by_id(batch.form_id)
            if form and form.template_words:
                template_words = form.template_words

        # VLM engines do full-page processing (no layout detection needed)
        vlm_engines = VLM_ENGINES
        is_vlm_engine = ocr_library in vlm_engines
        use_full_text_ocr = is_vlm_engine or layout_library in ("none", "")

        for i, document in enumerate(batch.documents):
            # Process document based on batch type and OCR engine
            if use_full_text_ocr:
                # Match fields if document has expected values
                should_match_fields = bool(document.field_values)
                doc_results = await self.process_document_full_text(
                    document=document,
                    ocr_library=ocr_library,
                    match_fields=should_match_fields,
                    image_cache=image_cache,
                    template_words=template_words,
                    ocr_prompt=ocr_prompt,
                )
            else:
                doc_results = await self.process_document(
                    document=document,
                    layout_library=layout_library,
                    ocr_library=ocr_library,
                    image_cache=image_cache,
                    template_words=template_words,
                    ocr_prompt=ocr_prompt,
                )

            # Store result in Firestore
            await self.firestore.create_result(
                test_run_id=test_run_id,
                document_id=document.id,
                batch_id=batch.id,
                layout_results=doc_results["layout_results"],
                ocr_results=doc_results["ocr_results"],
                extracted_fields=doc_results["extracted_fields"],
                overall_accuracy=doc_results["overall_accuracy"],
            )

            results.append({
                "document_id": document.id,
                **doc_results
            })

            # Call progress callback if provided
            if progress_callback:
                await progress_callback(i + 1, len(batch.documents))

        return results
