"""
Unified OCR + Classification pipeline service.

Combines OCR and classification into a single batch job with optional
single-call optimization when the same model is used for both.
"""
import io
import json
import logging
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from PIL import Image

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from app.models.batch import BatchInDB, SyntheticDocument
from app.models.result import ExtractedField
from app.services.storage import StorageService
from app.services.firestore import FirestoreService
from app.services.ocr_pipeline import OCRPipelineService
from app.processing.ocr import VLM_ENGINES

logger = logging.getLogger(__name__)

# Cache for LLM field mappings: {frozenset(ref_names) + frozenset(cls_names): mapping_dict}
_field_mapping_cache: Dict[str, Dict[str, str]] = {}

# Classifier model sets (mirrored from classification.py)
BEDROCK_CLASSIFIERS = {
    "claude_bedrock", "claude_haiku_bedrock",
    "nova_pro_bedrock", "nova_lite_bedrock",
    "pixtral_large_bedrock",
    "llama4_maverick_bedrock", "llama4_scout_bedrock",
}

# Combined prompt for single-call OCR+Classification
UNIFIED_PROMPT_TEMPLATE = """You are analyzing a document image. Perform TWO tasks:

TASK 1 - OCR: Extract ALL text from the document image exactly as it appears, preserving line breaks. Include both printed template text and handwritten/filled-in values.

TASK 2 - CLASSIFICATION: From the extracted text and the image, identify and extract the following specific data fields:
{field_types_list}

IMPORTANT:
- For OCR, extract EVERY word including template/printed text.
- For classification, extract only the ACTUAL HANDWRITTEN or FILLED-IN values, not template labels.
- Use the image directly to read handwritten text.
- If a field appears multiple times, include each occurrence.

Return ONLY valid JSON (no markdown, no code fences):
{{
  "ocr_text": "the complete extracted text from the document...",
  "form_type": "descriptive name of the form type",
  "classified_fields": [
    {{"field_type": "field_name", "value": "extracted value", "context": "nearby label", "confidence": 0.0, "page": 1, "area": "top|middle|bottom"}}
  ]
}}

{custom_instructions}"""


def _get_classifier(model_name: str):
    """Get a classifier instance by model name."""
    if model_name == "claude":
        from app.processing.classification.claude_classifier import ClaudeFieldClassifier
        return ClaudeFieldClassifier()
    elif model_name in BEDROCK_CLASSIFIERS:
        from app.processing.classification.bedrock_classifier import BedrockFieldClassifier
        return BedrockFieldClassifier(model_name)
    elif model_name in ("gpt5", "gpt5_mini"):
        from app.processing.classification.openai_classifier import OpenAIFieldClassifier
        return OpenAIFieldClassifier(model_name)
    else:
        from app.processing.classification.claude_classifier import ClaudeFieldClassifier
        return ClaudeFieldClassifier()


def _get_ocr_engine_client(model_name: str):
    """Get the API client from an OCR engine (for single-call mode)."""
    from app.processing.ocr import get_ocr_engine
    engine = get_ocr_engine(model_name)
    return engine


class UnifiedPipelineService:
    """Service for running combined OCR + Classification pipeline."""

    def __init__(self):
        self.storage = StorageService()
        self.firestore = FirestoreService()
        self.ocr_pipeline = OCRPipelineService()

    def _llm_map_fields(
        self, reference_names: List[str], classified_names: List[str]
    ) -> Dict[str, str]:
        """Use an LLM to map reference field names to classifier field names.

        Returns: {reference_name: classifier_field_name} mapping.
        Unmatched fields map to empty string.
        Results are cached to avoid repeated LLM calls.

        Both lists preserve document order to help disambiguate fields with
        the same short name (e.g., "Description" in different form sections).
        """
        # Create a cache key from field names in order (order matters for disambiguation)
        cache_key = (
            "|".join(reference_names[:100]) + "||" +
            "|".join(classified_names[:100])
        )
        if cache_key in _field_mapping_cache:
            logger.info("Using cached LLM field mapping")
            return _field_mapping_cache[cache_key]

        # Number both lists so the LLM can use position to disambiguate
        ref_numbered = [f"{i+1}. {name}" for i, name in enumerate(reference_names[:100])]
        cls_numbered = [f"{i+1}. {name}" for i, name in enumerate(classified_names[:100])]

        prompt = f"""You are mapping field names between two ordered lists. Both lists are in document order (top to bottom of the form).

REFERENCE COLUMNS (from a spreadsheet, in document order):
{chr(10).join(ref_numbered)}

CLASSIFIER FIELDS (from an AI model, in document order):
{chr(10).join(cls_numbered)}

RULES:
1. Map each reference column to the BEST matching classifier field.
2. Use BOTH the field name similarity AND the position/ordering to disambiguate.
   - Example: If "Description" appears as reference #45 and the classifier has "smt_1_description" (#30) and "clothing_property" (#80), use position to pick the right one.
3. Classifier fields often have section prefixes that indicate form sections:
   - "smt_" = Scars/Marks/Tattoos section
   - "arr_officer_" = Arresting Officer section
   - "trans_officer_" = Transporting Officer section
   - "employer_" = Employer section
   - "emergency_" = Emergency Contact section
   - "address_" = Address section
   - "phone_" = Phone section
4. Each classifier field should be mapped to AT MOST one reference field. Do NOT reuse classifier fields.
5. If no match exists, map to "".

Return ONLY valid JSON (no markdown, no code fences): a dict mapping reference name -> classifier field name.

Example: {{"Officer First Name": "officer_first_name", "SSN": "ssn", "Description": "smt_1_description", "Unknown Field": ""}}"""

        try:
            classifier = _get_classifier("claude_haiku_bedrock")
            result = classifier.classify_fields(
                ocr_text="",
                image=None,
                field_types=[],
                prompt_template=prompt,
            )

            # The result should have the mapping in classified_fields or as raw JSON
            mapping = {}
            if isinstance(result, dict):
                # Try to find the mapping in the result
                # After normalization, non-meta keys might be the mapping
                for key in reference_names:
                    if key in result:
                        val = result[key]
                        mapping[key] = str(val) if val else ""

                # If we didn't get direct keys, try classified_fields
                if not mapping:
                    for cf in result.get("classified_fields", []):
                        ft = cf.get("field_type", "")
                        val = cf.get("value", "")
                        if ft and val:
                            mapping[ft] = str(val)

            if mapping:
                logger.info(
                    f"LLM field mapping: {len(mapping)} mappings "
                    f"(sample: {dict(list(mapping.items())[:5])})"
                )
                _field_mapping_cache[cache_key] = mapping
                return mapping
            else:
                logger.warning("LLM field mapping returned empty mapping")
                return {}

        except Exception as e:
            logger.error(f"LLM field mapping failed: {e}")
            return {}

    @staticmethod
    def _is_pdf(data: bytes) -> bool:
        return data[:5] == b'%PDF-'

    @staticmethod
    def _pdf_bytes_to_images(pdf_bytes: bytes) -> List[Image.Image]:
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("PyMuPDF not installed")
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        for i in range(len(pdf_doc)):
            page = pdf_doc[i]
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        pdf_doc.close()
        return images

    def _is_same_model(self, ocr_library: str, classifier_model: str) -> bool:
        """Check if OCR engine and classifier use the same underlying model."""
        return ocr_library == classifier_model

    def _fuzzy_search_in_text(self, expected: str, full_text: str) -> tuple:
        """Find best fuzzy match of expected value anywhere in the OCR text.

        Returns:
            (best_score, best_snippet): score 0.0-1.0 and the matching text
        """
        if not expected or not full_text:
            return 0.0, ""

        expected_lower = expected.lower()
        best_score = 0.0
        best_snippet = ""

        # Check line by line
        for line in full_text.split("\n"):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            score = SequenceMatcher(None, expected_lower, line_stripped.lower()).ratio()
            if score > best_score:
                best_score = score
                best_snippet = line_stripped

            # Sliding window for substring matching
            if len(expected_lower) < len(line_stripped.lower()):
                words = line_stripped.split()
                for j in range(len(words)):
                    for k in range(j + 1, min(j + len(expected_lower.split()) + 2, len(words) + 1)):
                        snippet = " ".join(words[j:k])
                        score = SequenceMatcher(None, expected_lower, snippet.lower()).ratio()
                        if score > best_score:
                            best_score = score
                            best_snippet = snippet

        return best_score, best_snippet

    # Common abbreviation mappings for field name matching
    _ABBREVIATIONS = {
        "ssn": "social security number",
        "dob": "date of birth",
        "dl": "drivers license",
        "id": "identification",
        "num": "number",
        "no": "number",
        "addr": "address",
        "ph": "phone",
        "tel": "telephone",
        "dept": "department",
        "hcso": "harris county sheriff office",
        "spn": "state prisoner number",
        "sid": "state identification",
        "afis": "automated fingerprint identification system",
        "fbi": "federal bureau investigation",
        "da": "district attorney",
        "ccq": "computerized criminal query",
    }

    def _find_classified_field(
        self, field_name: str, classified_fields: List[Dict]
    ) -> Optional[Dict]:
        """Find the best matching classified field by reference field name.

        Uses aggressive normalization to directly map reference names like
        "Officer First Name" to classifier field_types like "officer_first_name".
        """
        if not classified_fields:
            return None

        # Normalize: lowercase, strip all separators and punctuation
        def normalize(name: str) -> str:
            n = name.lower().replace("_", " ").replace("-", " ").replace(".", " ")
            n = n.replace("?", "").replace(":", "").replace("#", "").replace("'", "")
            return n.strip()

        # Collapse all whitespace to single spaces
        def collapse(name: str) -> str:
            return " ".join(normalize(name).split())

        # Expand abbreviations in a name
        def expand_abbrevs(name: str) -> str:
            words = name.split()
            expanded = []
            for w in words:
                expanded.append(self._ABBREVIATIONS.get(w, w))
            return " ".join(expanded)

        field_norm = collapse(field_name)
        field_expanded = expand_abbrevs(field_norm)

        # 1. Try exact match after normalization
        for cf in classified_fields:
            cf_type = collapse(cf.get("field_type", ""))
            if cf_type == field_norm:
                return cf

        # 2. Try with abbreviation expansion on both sides
        for cf in classified_fields:
            cf_type = collapse(cf.get("field_type", ""))
            cf_expanded = expand_abbrevs(cf_type)
            if cf_expanded == field_expanded:
                return cf
            if cf_expanded == field_norm or cf_type == field_expanded:
                return cf

        # 3. Try field_name key (some formats use field_name instead of field_type)
        for cf in classified_fields:
            cf_name = collapse(cf.get("field_name", ""))
            if cf_name and cf_name == field_norm:
                return cf

        # 4. Word-boundary containment — only for multi-word names (>= 2 words)
        # Prevents "date" from matching "date_of_birth" or "city" from matching random fields
        field_words = set(field_expanded.split())
        if len(field_words) >= 2:
            for cf in classified_fields:
                cf_type = collapse(cf.get("field_type", ""))
                cf_expanded = expand_abbrevs(cf_type)
                cf_words = set(cf_expanded.split())
                # All words in the shorter name must appear in the longer name
                if len(field_words) <= len(cf_words) and field_words.issubset(cf_words):
                    return cf
                if len(cf_words) <= len(field_words) and len(cf_words) >= 2 and cf_words.issubset(field_words):
                    return cf

        # 5. Fuzzy match with 0.8 threshold (stricter to prevent wrong matches)
        best_match = None
        best_score = 0.0

        for cf in classified_fields:
            cf_type = collapse(cf.get("field_type", ""))
            cf_expanded = expand_abbrevs(cf_type)
            # Try both raw and expanded forms
            score = max(
                SequenceMatcher(None, field_norm, cf_type).ratio(),
                SequenceMatcher(None, field_expanded, cf_expanded).ratio(),
            )
            if score > best_score:
                best_score = score
                best_match = cf

        if best_score >= 0.8:
            return best_match
        return None

    def compute_dual_accuracy(
        self,
        field_values: Dict[str, str],
        ocr_text: str,
        classified_fields: List[Dict],
        judge_evaluations: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Compute separate OCR and classification accuracy against reference data.

        Args:
            field_values: {field_name: expected_value} from reference data
            ocr_text: Raw OCR extracted text
            classified_fields: List of classified field dicts from the model
            judge_evaluations: Optional list of judge field_evaluations
        """
        if not field_values:
            return {
                "extracted_fields": [],
                "ocr_accuracy": 0.0,
                "classification_accuracy": 0.0,
            }

        # Build a lookup for judge evaluations by normalized field name
        # Use aggressive normalization: lowercase, strip separators and punctuation
        def _norm_judge(name: str) -> str:
            n = name.lower().replace("_", " ").replace("-", " ").replace(".", " ")
            n = n.replace("?", "").replace(":", "").replace("#", "")
            return " ".join(n.split())

        judge_lookup = {}
        if judge_evaluations:
            for ev in judge_evaluations:
                jname = ev.get("field_name", "")
                if jname:
                    judge_lookup[_norm_judge(jname)] = ev
            logger.info(f"Judge lookup keys ({len(judge_lookup)}): {list(judge_lookup.keys())[:10]}")

        # Log classified fields for debugging
        if classified_fields:
            cf_names = [cf.get("field_type", "?") for cf in classified_fields[:20]]
            logger.info(f"Classified field names: {cf_names}")
        else:
            logger.warning("No classified_fields to match against reference data")

        ref_names = list(field_values.keys())
        logger.info(f"Reference field names: {ref_names[:20]}")

        # Build a quick lookup: classifier field_type -> classified field dict
        cls_by_type = {}
        for cf in classified_fields:
            ft = cf.get("field_type", "")
            if ft and ft not in cls_by_type:
                cls_by_type[ft] = cf

        # Check if reference names already match classifier field_types exactly
        # (e.g., when using the new 5-column template with prompt-matching field names)
        cls_type_set = set(cls_by_type.keys())
        exact_match_count = sum(1 for rn in ref_names if rn in cls_type_set)
        use_exact_match = exact_match_count >= len(ref_names) * 0.5  # >50% match = exact mode

        # Use LLM to build field name mapping only when field names DON'T match
        llm_mapping = {}
        if classified_fields and not use_exact_match:
            cls_names = [cf.get("field_type", "") for cf in classified_fields if cf.get("field_type")]
            cls_names = list(dict.fromkeys(cls_names))  # deduplicate preserving order
            if cls_names:
                llm_mapping = self._llm_map_fields(ref_names, cls_names)
                logger.info(f"Using LLM field mapping ({len(llm_mapping)} mappings)")
        elif use_exact_match:
            logger.info(
                f"Using exact field name matching ({exact_match_count}/{len(ref_names)} "
                f"reference names match classifier field_types directly)"
            )

        extracted_fields = []
        ocr_scores = []
        cls_scores = []
        used_classified_ids = set()  # Track matched classified fields to prevent duplicates

        has_ocr = bool(ocr_text and ocr_text.strip())

        for field_name, expected_value in field_values.items():
            if not expected_value:
                continue

            # OCR accuracy: fuzzy match of expected value in raw OCR text
            # Skip if no OCR text (classification-only mode)
            if has_ocr:
                ocr_match_score, ocr_snippet = self._fuzzy_search_in_text(
                    expected_value, ocr_text
                )
            else:
                ocr_match_score, ocr_snippet = 0.0, ""
            ocr_scores.append(ocr_match_score)

            # Classification accuracy: find matching classified field
            classified = None

            # Strategy 0: Direct exact match (when reference field names match prompt field names)
            if use_exact_match and field_name in cls_by_type:
                cf = cls_by_type[field_name]
                cf_idx = classified_fields.index(cf)
                if cf_idx not in used_classified_ids:
                    classified = cf
                    used_classified_ids.add(cf_idx)

            # Strategy 1: Use LLM mapping (when field names don't match)
            mapped_name = llm_mapping.get(field_name, "")
            if mapped_name and mapped_name in cls_by_type:
                cf = cls_by_type[mapped_name]
                cf_idx = classified_fields.index(cf)
                if cf_idx not in used_classified_ids:
                    classified = cf
                    used_classified_ids.add(cf_idx)

            # Strategy 2: Fall back to rule-based matching
            if not classified:
                available_fields = [
                    cf for i, cf in enumerate(classified_fields)
                    if i not in used_classified_ids
                ]
                classified = self._find_classified_field(field_name, available_fields)
                if classified:
                    cf_idx = classified_fields.index(classified)
                    used_classified_ids.add(cf_idx)
            classified_value = ""
            classified_field_type = None
            classification_match_score = 0.0
            classification_confidence = 0.0

            if classified:
                logger.info(
                    f"Field match: ref '{field_name}' -> cls '{classified.get('field_type')}' "
                    f"value='{str(classified.get('value'))[:50]}'"
                )
            else:
                logger.info(f"No classification match for ref field '{field_name}'")

            if classified:
                classified_field_type = classified.get("field_type", "")
                raw_value = classified.get("value")
                classification_confidence = classified.get("confidence", 0.0)
                if isinstance(classification_confidence, str):
                    try:
                        classification_confidence = float(classification_confidence)
                    except (ValueError, TypeError):
                        classification_confidence = 0.0
                # Handle null/None values — treat as field-not-found
                if raw_value is not None and raw_value != "null":
                    # Stringify objects/lists for display and comparison
                    if isinstance(raw_value, (dict, list)):
                        import json as _json
                        classified_value = _json.dumps(raw_value, default=str)
                    else:
                        classified_value = str(raw_value)
                    if classified_value and expected_value:
                        classification_match_score = SequenceMatcher(
                            None, expected_value.lower(), classified_value.lower()
                        ).ratio()
            cls_scores.append(classification_match_score)

            # Judge score for this field (if available)
            judge_score = None
            judge_reasoning = None
            norm_key = _norm_judge(field_name)
            judge_ev = judge_lookup.get(norm_key)
            # Fuzzy fallback: try containment or SequenceMatcher
            if not judge_ev and judge_lookup:
                best_jscore = 0.0
                for jk, jev in judge_lookup.items():
                    if jk in norm_key or norm_key in jk:
                        judge_ev = jev
                        break
                    js = SequenceMatcher(None, norm_key, jk).ratio()
                    if js > best_jscore:
                        best_jscore = js
                        if js >= 0.7:
                            judge_ev = jev
            if judge_ev:
                # Use classification_score from judge if available, else ocr_score
                judge_score = judge_ev.get("classification_score",
                              judge_ev.get("ocr_score"))
                judge_reasoning = judge_ev.get("reasoning")

            extracted_fields.append(ExtractedField(
                field_name=field_name,
                expected_value=expected_value,
                extracted_value=ocr_snippet,  # Actual best-matching OCR text
                confidence=ocr_match_score,  # OCR match confidence
                match_score=ocr_match_score,
                is_important=True,
                classified_field_type=classified_field_type,
                classified_value=classified_value,
                classification_match_score=classification_match_score,
                classification_confidence=classification_confidence,
                judge_score=judge_score,
                judge_reasoning=judge_reasoning,
            ))

        ocr_accuracy = sum(ocr_scores) / max(len(ocr_scores), 1) if ocr_scores else 0.0
        classification_accuracy = sum(cls_scores) / max(len(cls_scores), 1) if cls_scores else 0.0

        return {
            "extracted_fields": extracted_fields,
            "ocr_accuracy": ocr_accuracy,
            "classification_accuracy": classification_accuracy,
        }

    async def _process_single_call(
        self,
        document: SyntheticDocument,
        model_name: str,
        field_types: List[str],
        page_images: List[Image.Image],
        ocr_prompt: Optional[str] = None,
        classification_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Single API call: combined OCR + Classification."""
        field_types_list = "\n".join(f"- {ft}" for ft in field_types)
        custom_instructions = ocr_prompt or ""
        if classification_prompt:
            custom_instructions += "\n\n" + classification_prompt

        prompt = UNIFIED_PROMPT_TEMPLATE.format(
            field_types_list=field_types_list,
            custom_instructions=custom_instructions,
        )

        # Use the classifier to make the API call (it handles image formatting)
        # Pass the unified prompt as prompt_template so it replaces the classifier's
        # default prompt. Pass empty ocr_text since the prompt already has instructions.
        classifier = _get_classifier(model_name)
        result = classifier.classify_fields(
            ocr_text="",
            image=page_images[0] if page_images else None,
            field_types=field_types,
            prompt_template=prompt,
            images=page_images if len(page_images) > 1 else None,
        )

        # Check for classifier errors
        if isinstance(result, dict) and result.get("error"):
            logger.error(f"Single-call classifier error: {result['error']}")

        # Parse the combined response
        ocr_text = ""
        classified_fields = []
        classification_results = {}

        if isinstance(result, dict):
            # The classifier may return JSON with ocr_text + classified_fields
            if "ocr_text" in result:
                ocr_text = result.get("ocr_text", "")
                classified_fields = result.get("classified_fields", [])
                classification_results = result
            elif "classified_fields" in result:
                classified_fields = result.get("classified_fields", [])
                classification_results = result
                # If raw_response has the combined JSON, try to extract ocr_text
                raw = result.get("raw_response", "")
                if raw:
                    try:
                        parsed = json.loads(raw)
                        ocr_text = parsed.get("ocr_text", "")
                    except (json.JSONDecodeError, TypeError):
                        pass

        ocr_results = {
            "full_text": ocr_text,
            "text_regions": [
                {"text": line.strip(), "confidence": 0.9}
                for line in ocr_text.split("\n")
                if line.strip()
            ],
        }

        layout_results = {"regions": [], "method": "none (unified OCR+classification)"}

        return {
            "layout_results": layout_results,
            "ocr_results": ocr_results,
            "classification_results": classification_results,
            "classified_fields": classified_fields,
            "ocr_text": ocr_text,
        }

    async def _process_two_calls(
        self,
        document: SyntheticDocument,
        layout_library: str,
        ocr_library: str,
        classifier_model: str,
        field_types: List[str],
        page_images: List[Image.Image],
        image_cache: Optional[Dict[str, bytes]] = None,
        template_words: Optional[List[str]] = None,
        ocr_prompt: Optional[str] = None,
        classification_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Two separate calls: OCR first, then Classification."""
        ocr_text = ""
        layout_results = {"regions": [], "method": "none"}
        ocr_results = {"full_text": "", "text_regions": []}

        # Classification-only mode: skip OCR when no OCR engine is selected
        skip_ocr = ocr_library in ("none", "")
        if not skip_ocr:
            vlm_engines = VLM_ENGINES
            is_vlm = ocr_library in vlm_engines
            use_full_text = is_vlm or layout_library in ("none", "")

            # Call 1: OCR
            if use_full_text:
                ocr_result = await self.ocr_pipeline.process_document_full_text(
                    document=document,
                    ocr_library=ocr_library,
                    match_fields=bool(document.field_values),
                    image_cache=image_cache,
                    template_words=template_words,
                    ocr_prompt=ocr_prompt,
                )
            else:
                ocr_result = await self.ocr_pipeline.process_document(
                    document=document,
                    layout_library=layout_library,
                    ocr_library=ocr_library,
                    image_cache=image_cache,
                    template_words=template_words,
                    ocr_prompt=ocr_prompt,
                )

            ocr_text = ocr_result["ocr_results"].get("full_text", "")
            layout_results = ocr_result["layout_results"]
            ocr_results = ocr_result["ocr_results"]
        else:
            logger.info(
                f"Classification-only mode (no OCR engine) for doc {document.id}"
            )

        # Call 2 (or only call): Classification
        classifier = _get_classifier(classifier_model)
        classification_result = classifier.classify_fields(
            ocr_text=ocr_text,
            image=page_images[0] if page_images else None,
            field_types=field_types,
            prompt_template=classification_prompt,
            images=page_images if len(page_images) > 1 else None,
        )

        classified_fields = classification_result.get("classified_fields", [])

        return {
            "layout_results": layout_results,
            "ocr_results": ocr_results,
            "classification_results": classification_result,
            "classified_fields": classified_fields,
            "ocr_text": ocr_text,
        }

    async def process_document_unified(
        self,
        document: SyntheticDocument,
        layout_library: str,
        ocr_library: str,
        classifier_model: str,
        field_types: List[str],
        image_cache: Optional[Dict[str, bytes]] = None,
        template_words: Optional[List[str]] = None,
        ocr_prompt: Optional[str] = None,
        classification_prompt: Optional[str] = None,
        judge_model: Optional[str] = None,
        judge_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a document through OCR + Classification + optional Judge."""
        # Download image
        if image_cache is not None and document.storage_path in image_cache:
            image_bytes = image_cache[document.storage_path]
        else:
            image_bytes = await self.storage.download_file(document.storage_path)
            if image_cache is not None:
                image_cache[document.storage_path] = image_bytes

        # Convert to page images
        if self._is_pdf(image_bytes) and PYMUPDF_AVAILABLE:
            page_images = self._pdf_bytes_to_images(image_bytes)
        else:
            page_images = [Image.open(io.BytesIO(image_bytes)).convert("RGB")]

        # Determine routing: single-call (same model), two-call, or classification-only
        # Always use two-call when a custom classification prompt is provided,
        # because the custom prompt overrides the unified format and drops OCR text.
        skip_ocr = ocr_library in ("none", "")
        same_model = not skip_ocr and self._is_same_model(ocr_library, classifier_model)
        has_custom_prompt = bool(classification_prompt)
        use_single_call = same_model and not has_custom_prompt

        if use_single_call:
            logger.info(
                f"Unified single-call: {ocr_library} for doc {document.id}"
            )
            results = await self._process_single_call(
                document, ocr_library, field_types, page_images,
                ocr_prompt, classification_prompt,
            )
        else:
            mode = "classification-only" if skip_ocr else f"OCR={ocr_library}"
            logger.info(
                f"Unified two-call: {mode}, classifier={classifier_model} "
                f"for doc {document.id}"
            )
            results = await self._process_two_calls(
                document, layout_library, ocr_library, classifier_model,
                field_types, page_images, image_cache, template_words,
                ocr_prompt, classification_prompt,
            )

        # Run judge evaluation BEFORE computing accuracy (so judge scores go into fields)
        ocr_text = results.get("ocr_text", "")
        classified_fields = results.get("classified_fields", [])
        judge_eval = None
        judge_overall_score = None

        if judge_model and document.field_values:
            try:
                from app.services.judge_service import JudgeService
                judge_svc = JudgeService()

                # Build mapped classified fields for the judge so it evaluates
                # the CORRECT pairings (not re-guessing from the full dump)
                mapped_classified_for_judge = classified_fields  # default: full list
                if classified_fields:
                    ref_names = list(document.field_values.keys())
                    # Index classifier fields by field_type for lookup
                    cls_by_type = {}
                    for cf in classified_fields:
                        ft = cf.get("field_type", "")
                        if ft and ft not in cls_by_type:
                            cls_by_type[ft] = cf

                    # Also build a normalized lookup (lowercase, no spaces/underscores)
                    # to handle mismatches like "Home ZIP Code" vs "zip_code"
                    cls_by_normalized = {}
                    for ft, cf in cls_by_type.items():
                        norm_key = ft.lower().replace(" ", "_").replace("-", "_")
                        cls_by_normalized[norm_key] = cf
                        # Also index by common short forms
                        # e.g., "Home ZIP Code" -> "home_zip_code"
                        # Strip common prefixes for additional matching
                        for prefix in ("home_", "prisoner_", "officer_"):
                            if norm_key.startswith(prefix):
                                cls_by_normalized[norm_key[len(prefix):]] = cf

                    def _find_classifier_field(mapped_name):
                        """Look up a classifier field by name, with fuzzy matching."""
                        if not mapped_name:
                            return None
                        # Exact match first
                        if mapped_name in cls_by_type:
                            return cls_by_type[mapped_name]
                        # Normalized match
                        norm = mapped_name.lower().replace(" ", "_").replace("-", "_")
                        if norm in cls_by_normalized:
                            return cls_by_normalized[norm]
                        # Try partial match: find any cls key that contains the mapped name or vice versa
                        for ft, cf in cls_by_type.items():
                            ft_norm = ft.lower().replace(" ", "_").replace("-", "_")
                            if norm in ft_norm or ft_norm in norm:
                                return cf
                        return None

                    # Check if exact matching is possible
                    cls_type_set = set(cls_by_type.keys())
                    exact_count = sum(1 for rn in ref_names if rn in cls_type_set)
                    use_exact = exact_count >= len(ref_names) * 0.5

                    # Build field name mapping (exact or LLM)
                    field_mapping = {}
                    if use_exact:
                        field_mapping = {rn: rn for rn in ref_names if rn in cls_type_set}
                    else:
                        cls_names = list(dict.fromkeys(
                            cf.get("field_type", "") for cf in classified_fields if cf.get("field_type")
                        ))
                        if cls_names:
                            field_mapping = self._llm_map_fields(ref_names, cls_names)

                    if field_mapping:
                        mapped_list = []
                        for ref_name, expected in document.field_values.items():
                            if not expected:
                                continue
                            mapped_cls_name = field_mapping.get(ref_name, "")
                            cf = _find_classifier_field(mapped_cls_name) if mapped_cls_name else None
                            mapped_list.append({
                                "reference_field": ref_name,
                                "classifier_field": mapped_cls_name or "(no match)",
                                "classifier_value": cf.get("value") if cf else None,
                                "classifier_confidence": cf.get("confidence", 0.0) if cf else 0.0,
                            })
                        mapped_classified_for_judge = mapped_list

                judge_eval = judge_svc.evaluate_document(
                    judge_model=judge_model,
                    document_images=page_images,
                    reference_data=document.field_values,
                    ocr_text=ocr_text,
                    classified_fields=mapped_classified_for_judge,
                    judge_prompt=judge_prompt,
                )
                # Use the best overall score from judge (OCR or classification)
                ocr_judge = judge_eval.get("overall_ocr_score", 0.0) or 0.0
                cls_judge = judge_eval.get("overall_classification_score", 0.0) or 0.0
                judge_overall_score = max(ocr_judge, cls_judge)
                # If both are 0, compute from field evaluations
                if judge_overall_score == 0 and judge_eval.get("field_evaluations"):
                    evals = judge_eval["field_evaluations"]
                    scores = []
                    for ev in evals:
                        s = ev.get("classification_score", ev.get("ocr_score", 0)) or 0
                        scores.append(float(s))
                    if scores:
                        judge_overall_score = sum(scores) / len(scores)
            except Exception as e:
                logger.error(f"Judge evaluation failed for doc {document.id}: {e}")
                judge_eval = {"error": str(e)}

        # Get judge field evaluations to integrate into extracted fields
        judge_evaluations = None
        if judge_eval and "field_evaluations" in judge_eval:
            judge_evaluations = judge_eval["field_evaluations"]

        # Compute dual accuracy against reference data (with judge scores inline)
        accuracy = self.compute_dual_accuracy(
            document.field_values, ocr_text, classified_fields,
            judge_evaluations=judge_evaluations,
        )

        results["extracted_fields"] = accuracy["extracted_fields"]
        results["overall_accuracy"] = accuracy["ocr_accuracy"]
        results["ocr_accuracy"] = accuracy["ocr_accuracy"]
        results["classification_accuracy"] = accuracy["classification_accuracy"]
        results["judge_eval"] = judge_eval
        results["judge_overall_score"] = judge_overall_score

        return results

    async def process_batch_unified(
        self,
        batch: BatchInDB,
        layout_library: str,
        ocr_library: str,
        classifier_model: str,
        field_types: Optional[List[str]],
        test_run_id: str,
        ocr_prompt: Optional[str] = None,
        classification_prompt: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        image_cache: Optional[Dict[str, bytes]] = None,
        judge_model: Optional[str] = None,
        judge_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Process all documents in a batch through unified pipeline."""
        # Default field_types to empty list if None
        if field_types is None:
            field_types = []
        results = []

        # Look up form template words
        template_words = None
        if batch.form_id:
            form = await self.firestore.get_form_by_id(batch.form_id)
            if form and form.template_words:
                template_words = form.template_words

        for i, document in enumerate(batch.documents):
            doc_results = await self.process_document_unified(
                document=document,
                layout_library=layout_library,
                ocr_library=ocr_library,
                classifier_model=classifier_model,
                field_types=field_types,
                image_cache=image_cache,
                template_words=template_words,
                ocr_prompt=ocr_prompt,
                classification_prompt=classification_prompt,
                judge_model=judge_model,
                judge_prompt=judge_prompt,
            )

            # Judge results are now computed inside process_document_unified
            judge_eval = doc_results.get("judge_eval")
            judge_overall_score = doc_results.get("judge_overall_score")

            # Ensure classification_results has classifier_model for metrics tracking
            cls_results = doc_results.get("classification_results")
            if cls_results is not None and isinstance(cls_results, dict):
                if not cls_results:
                    # Empty dict from single-call mode — populate with basic info
                    cls_results = {"classifier_model": classifier_model}
                elif "classifier_model" not in cls_results:
                    cls_results["classifier_model"] = classifier_model

            # Store result
            await self.firestore.create_result(
                test_run_id=test_run_id,
                document_id=document.id,
                batch_id=batch.id,
                layout_results=doc_results["layout_results"],
                ocr_results=doc_results["ocr_results"],
                extracted_fields=doc_results["extracted_fields"],
                overall_accuracy=doc_results["overall_accuracy"],
                classification_results=cls_results,
                ocr_accuracy=doc_results.get("ocr_accuracy"),
                classification_accuracy=doc_results.get("classification_accuracy"),
                judge_results=judge_eval,
                judge_model=judge_model,
                judge_overall_score=judge_overall_score,
            )

            results.append({
                "document_id": document.id,
                **doc_results,
            })

            if progress_callback:
                await progress_callback(i + 1, len(batch.documents))

        return results
