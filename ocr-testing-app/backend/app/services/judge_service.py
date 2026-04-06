"""
LLM-as-a-Judge evaluation service.

Uses a second model to independently evaluate OCR and classification results
against reference data.
"""
import json
import logging
from typing import List, Dict, Any, Optional
from PIL import Image

logger = logging.getLogger(__name__)

JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator assessing the quality of OCR and field classification results on a document.

You are given:
1. The REFERENCE DATA (ground truth field values)
2. The OCR OUTPUT (text extracted by an OCR system)
3. The CLASSIFICATION OUTPUT — a list showing which classifier field was mapped to each reference field, along with the classified value

Your task: For EACH reference field, evaluate:
- ocr_score (0.0-1.0): How well did the OCR capture this field's value in the extracted text?
  1.0 = the expected value appears perfectly in the OCR text
  0.0 = the expected value is completely missing from OCR text
- classification_score (0.0-1.0): How well did the classifier identify and extract this field?
  1.0 = the classified value exactly matches the reference value
  0.0 = the field was not found or is completely wrong
- reasoning: Brief explanation of your score

IMPORTANT: Each reference field has been pre-matched to a specific classifier field. Use the provided mapping — do NOT re-match fields yourself. If a reference field shows "(no match)" it means no classifier field was found for it.

REFERENCE DATA:
{reference_fields}

OCR TEXT:
---
{ocr_text}
---

CLASSIFIED FIELDS (mapped to reference fields):
{classified_fields_json}

Return ONLY valid JSON (no markdown, no code fences):
{{
  "field_evaluations": [
    {{
      "field_name": "...",
      "reference_value": "...",
      "ocr_value_found": "closest matching text in OCR output or empty",
      "classified_value": "value from classifier or empty",
      "ocr_score": 0.0,
      "classification_score": 0.0,
      "reasoning": "brief explanation"
    }}
  ],
  "overall_ocr_score": 0.0,
  "overall_classification_score": 0.0,
  "summary": "1-2 sentence overall assessment"
}}"""


class JudgeService:
    """Service for LLM-as-a-Judge evaluation."""

    def _get_classifier(self, model_name: str):
        """Get a classifier instance to use as judge."""
        from app.services.unified_pipeline import _get_classifier
        return _get_classifier(model_name)

    def evaluate_document(
        self,
        judge_model: str,
        document_images: List[Image.Image],
        reference_data: Dict[str, str],
        ocr_text: str,
        classified_fields: List[Dict],
        judge_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Have the judge model evaluate OCR + classification results.

        Args:
            judge_model: Model name to use as judge
            document_images: List of page images
            reference_data: {field_name: expected_value}
            ocr_text: Full OCR extracted text
            classified_fields: List of classified field dicts
            judge_prompt: Optional custom judge prompt

        Returns:
            Judge evaluation dict with field_evaluations and overall scores
        """
        if not reference_data:
            return {
                "field_evaluations": [],
                "overall_ocr_score": 0.0,
                "overall_classification_score": 0.0,
                "summary": "No reference data available for evaluation.",
            }

        # Format reference data
        ref_lines = []
        for field_name, expected_value in reference_data.items():
            if expected_value:
                ref_lines.append(f"- {field_name}: {expected_value}")
        reference_fields_str = "\n".join(ref_lines)

        # Format classified fields
        classified_fields_json = json.dumps(classified_fields, indent=2, default=str)

        # Build the judge prompt
        if judge_prompt:
            prompt = judge_prompt.replace("{reference_fields}", reference_fields_str)
            prompt = prompt.replace("{ocr_text}", ocr_text)
            prompt = prompt.replace("{classified_fields_json}", classified_fields_json)
        else:
            prompt = JUDGE_PROMPT_TEMPLATE.format(
                reference_fields=reference_fields_str,
                ocr_text=ocr_text[:10000],  # Truncate to avoid token limits
                classified_fields_json=classified_fields_json,
            )

        # Use the classifier interface to make the API call
        classifier = self._get_classifier(judge_model)

        logger.info(
            f"Running judge evaluation with {judge_model}: "
            f"{len(reference_data)} reference fields, "
            f"{len(ocr_text)} chars OCR text, "
            f"{len(classified_fields)} classified fields"
        )

        result = classifier.classify_fields(
            ocr_text="",
            image=None,  # No image needed — judge compares text against ground truth
            field_types=[],  # Not used; prompt has everything
            prompt_template=prompt,
            images=None,
        )

        # Parse the judge response
        return self._parse_judge_response(result, judge_model)

    def _parse_judge_response(
        self, result: Dict[str, Any], judge_model: str
    ) -> Dict[str, Any]:
        """Parse the judge model's response into structured evaluation."""
        default_response = {
            "judge_model": judge_model,
            "field_evaluations": [],
            "overall_ocr_score": 0.0,
            "overall_classification_score": 0.0,
            "summary": "",
        }

        if not result or "error" in result:
            default_response["error"] = result.get("error", "Unknown error")
            logger.error(f"Judge returned error: {result}")
            return default_response

        logger.info(f"Judge raw result keys: {list(result.keys())}")

        # Try to extract field_evaluations from the result directly
        if "field_evaluations" in result:
            logger.info(f"Judge: found field_evaluations directly ({len(result['field_evaluations'])} fields)")
            return self._build_judge_result(result, judge_model)

        # Try parsing from raw_response (the classifier may wrap the response)
        raw = result.get("raw_response", "")
        if raw:
            # Try JSON parsing
            try:
                parsed = json.loads(raw)
                if "field_evaluations" in parsed:
                    logger.info(f"Judge: found field_evaluations in raw_response JSON ({len(parsed['field_evaluations'])} fields)")
                    return self._build_judge_result(parsed, judge_model)
            except (json.JSONDecodeError, TypeError):
                pass

            # Try extracting JSON from text (model may include markdown fences)
            import re
            json_match = re.search(r'\{[\s\S]*"field_evaluations"[\s\S]*\}', raw)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    if "field_evaluations" in parsed:
                        logger.info(f"Judge: extracted field_evaluations from raw text ({len(parsed['field_evaluations'])} fields)")
                        return self._build_judge_result(parsed, judge_model)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Check if classified_fields contain judge evaluation data
        # (the classifier normalizer may have moved field_evaluations into classified_fields)
        classified = result.get("classified_fields", [])
        if classified:
            # Check if these look like judge evaluations (have ocr_score/classification_score)
            first = classified[0] if classified else {}
            if "ocr_score" in first or "classification_score" in first:
                logger.info(f"Judge: found evaluation data in classified_fields ({len(classified)} fields)")
                evaluations = []
                for cf in classified:
                    evaluations.append({
                        "field_name": cf.get("field_type", cf.get("field_name", "")),
                        "reference_value": cf.get("reference_value", ""),
                        "ocr_score": float(cf.get("ocr_score", 0) or 0),
                        "classification_score": float(cf.get("classification_score", 0) or 0),
                        "reasoning": cf.get("reasoning", cf.get("context", "")),
                    })
                return self._build_judge_result({"field_evaluations": evaluations}, judge_model)

            # Fallback: treat as generic classified fields
            logger.info(f"Judge: falling back to classified_fields as evaluations ({len(classified)} fields)")
            evaluations = []
            for cf in classified:
                evaluations.append({
                    "field_name": cf.get("field_type", ""),
                    "reference_value": "",
                    "ocr_score": float(cf.get("confidence", 0) or 0),
                    "classification_score": float(cf.get("confidence", 0) or 0),
                    "reasoning": cf.get("context", ""),
                })
            if evaluations:
                return self._build_judge_result({"field_evaluations": evaluations}, judge_model)

        logger.warning(f"Judge: could not parse response. Result keys: {list(result.keys())}, raw[:200]: {str(raw)[:200]}")
        default_response["raw_response"] = str(result)[:500]
        return default_response

    def _build_judge_result(self, parsed: Dict, judge_model: str) -> Dict[str, Any]:
        """Build a standardized judge result from parsed evaluation data."""
        evaluations = parsed.get("field_evaluations", [])

        # Compute overall scores from field evaluations if not provided
        overall_ocr = parsed.get("overall_ocr_score")
        overall_cls = parsed.get("overall_classification_score")

        if (overall_ocr is None or overall_cls is None) and evaluations:
            ocr_scores = [float(e.get("ocr_score", 0) or 0) for e in evaluations]
            cls_scores = [float(e.get("classification_score", 0) or 0) for e in evaluations]
            if overall_ocr is None and ocr_scores:
                overall_ocr = sum(ocr_scores) / len(ocr_scores)
            if overall_cls is None and cls_scores:
                overall_cls = sum(cls_scores) / len(cls_scores)

        overall_ocr = float(overall_ocr or 0)
        overall_cls = float(overall_cls or 0)

        logger.info(f"Judge result: {len(evaluations)} field evals, "
                     f"overall_ocr={overall_ocr:.2f}, overall_cls={overall_cls:.2f}")

        return {
            "judge_model": judge_model,
            "field_evaluations": evaluations,
            "overall_ocr_score": overall_ocr,
            "overall_classification_score": overall_cls,
            "summary": parsed.get("summary", ""),
        }
